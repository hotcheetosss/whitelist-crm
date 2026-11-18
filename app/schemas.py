"""Pydantic models for request bodies and responses.

Request models forbid unknown fields: e.g. a client cannot send `ends_at`,
it is always calculated by the server.
"""

from datetime import date, datetime, timezone
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import AwareDatetime, BaseModel, ConfigDict, StringConstraints, field_validator

CompanyStatus = Literal["new", "no_answer", "refused", "meeting_set"]
CallResult = Literal["no_answer", "refused", "meeting_set"]
MeetingStatus = Literal["scheduled", "cancelled"]
MeetingAction = Literal["created", "rescheduled", "cancelled"]

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
# BIN: exactly 12 digits. The checksum is intentionally not verified (see README).
Bin = Annotated[str, StringConstraints(pattern=r"^\d{12}$")]
Phone = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=32)]
Comment = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]

T = TypeVar("T")


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


# --- Managers ----------------------------------------------------------------


class ManagerCreate(RequestModel):
    name: NonEmptyStr


class ManagerOut(BaseModel):
    id: int
    name: str
    created_at: str


# --- Companies ---------------------------------------------------------------


class CompanyCreate(RequestModel):
    name: NonEmptyStr
    bin: Bin
    phone: Phone | None = None


class CompanyOut(BaseModel):
    id: int
    name: str
    bin: str
    phone: str | None
    status: CompanyStatus
    created_at: str


# --- Meetings ----------------------------------------------------------------


class MeetingTime(RequestModel):
    # AwareDatetime: a time without a timezone is rejected with 422.
    starts_at: AwareDatetime

    @field_validator("starts_at")
    @classmethod
    def normalize_start(cls, value: datetime) -> datetime:
        if value.second != 0 or value.microsecond != 0:
            raise ValueError("время начала должно быть целой минутой (секунды = 0)")
        return value.astimezone(timezone.utc)


class MeetingCreate(MeetingTime):
    company_id: int
    manager_id: int


class MeetingReschedule(MeetingTime):
    pass


class MeetingEventOut(BaseModel):
    action: MeetingAction
    old_starts_at: str | None
    new_starts_at: str | None
    created_at: str


class MeetingOut(BaseModel):
    id: int
    company_id: int
    manager_id: int
    starts_at: str
    ends_at: str
    original_starts_at: str
    status: MeetingStatus
    created_at: str
    history: list[MeetingEventOut]


class ManagerSchedule(BaseModel):
    manager_id: int
    date: date
    timezone: str
    meetings: list[MeetingOut]


# --- Calls -------------------------------------------------------------------


class CallCreate(RequestModel):
    company_id: int
    result: CallResult
    meeting_id: int | None = None
    comment: Comment | None = None


class CallOut(BaseModel):
    id: int
    company_id: int
    result: CallResult
    meeting_id: int | None
    comment: str | None
    called_at: str
