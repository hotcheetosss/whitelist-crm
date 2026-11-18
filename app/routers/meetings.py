import sqlite3
from datetime import date, datetime

from fastapi import APIRouter, Depends, Query

from app.deps import get_conn, get_now
from app.schemas import ManagerSchedule, MeetingCreate, MeetingOut, MeetingUpdate
from app.services import meetings

router = APIRouter(tags=["meetings"])


@router.post("/meetings", status_code=201, response_model=MeetingOut)
def create_meeting(
    data: MeetingCreate,
    conn: sqlite3.Connection = Depends(get_conn),
    now: datetime = Depends(get_now),
) -> dict:
    return meetings.create_meeting(conn, data, now)


@router.get("/meetings/{meeting_id}", response_model=MeetingOut)
def get_meeting(meeting_id: int, conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    return meetings.get_meeting(conn, meeting_id)


@router.patch("/meetings/{meeting_id}", response_model=MeetingOut)
def update_meeting(
    meeting_id: int,
    data: MeetingUpdate,
    conn: sqlite3.Connection = Depends(get_conn),
    now: datetime = Depends(get_now),
) -> dict:
    """Reschedule ({"starts_at": ...}) or cancel ({"status": "cancelled"}) a meeting."""
    return meetings.update_meeting(conn, meeting_id, data, now)


@router.get("/managers/{manager_id}/schedule", response_model=ManagerSchedule)
def get_manager_schedule(
    manager_id: int,
    day: date = Query(alias="date", description="Календарный день по Алматы, YYYY-MM-DD"),
    conn: sqlite3.Connection = Depends(get_conn),
) -> dict:
    return meetings.get_manager_schedule(conn, manager_id, day)
