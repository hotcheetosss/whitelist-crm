"""Pure business-rule helpers: time format conversions and working hours.

No database and no clock here, so every function is trivially unit-testable.
"""

from datetime import date, datetime, time, timedelta, timezone

from app.config import BUSINESS_TZ, WORKDAY_END, WORKDAY_START, WORKDAYS

# The only time format stored in the DB and returned by the API.
UTC_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def to_utc_text(moment: datetime) -> str:
    """Aware datetime -> '2026-11-23T05:00:00Z'."""
    return moment.astimezone(timezone.utc).strftime(UTC_FORMAT)


def from_utc_text(text: str) -> datetime:
    return datetime.strptime(text, UTC_FORMAT).replace(tzinfo=timezone.utc)


def is_within_working_hours(starts_at: datetime, ends_at: datetime) -> bool:
    """Mon-Fri, start >= 09:00 and end <= 18:00 in Almaty local time.

    Both ends are converted with zoneinfo rather than a fixed +5 offset,
    so historical dates (UTC+6 before March 2024) are handled correctly too.
    """
    local_start = starts_at.astimezone(BUSINESS_TZ)
    local_end = ends_at.astimezone(BUSINESS_TZ)
    if local_start.weekday() not in WORKDAYS:
        return False
    if local_start.date() != local_end.date():
        return False
    return local_start.time() >= WORKDAY_START and local_end.time() <= WORKDAY_END


def business_day_bounds(day: date) -> tuple[datetime, datetime]:
    """[start, end) of a calendar day in Almaty, as UTC datetimes."""
    local_start = datetime.combine(day, time(0, 0), tzinfo=BUSINESS_TZ)
    local_end = datetime.combine(day + timedelta(days=1), time(0, 0), tzinfo=BUSINESS_TZ)
    return local_start.astimezone(timezone.utc), local_end.astimezone(timezone.utc)


def format_local_range(starts_at: datetime, ends_at: datetime) -> str:
    """'23.11.2026 10:00–11:00' in Almaty time — for human-readable error messages."""
    local_start = starts_at.astimezone(BUSINESS_TZ)
    local_end = ends_at.astimezone(BUSINESS_TZ)
    return f"{local_start:%d.%m.%Y %H:%M}–{local_end:%H:%M}"
