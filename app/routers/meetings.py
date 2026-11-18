import sqlite3
from datetime import date, datetime

from fastapi import APIRouter, Depends, Query

from app.deps import get_conn, get_now
from app.schemas import ManagerSchedule, MeetingCreate, MeetingOut, MeetingReschedule
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


@router.post("/meetings/{meeting_id}/reschedule", response_model=MeetingOut)
def reschedule_meeting(
    meeting_id: int,
    data: MeetingReschedule,
    conn: sqlite3.Connection = Depends(get_conn),
    now: datetime = Depends(get_now),
) -> dict:
    return meetings.reschedule_meeting(conn, meeting_id, data, now)


@router.post("/meetings/{meeting_id}/cancel", response_model=MeetingOut)
def cancel_meeting(
    meeting_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
    now: datetime = Depends(get_now),
) -> dict:
    return meetings.cancel_meeting(conn, meeting_id, now)


@router.get("/managers/{manager_id}/schedule", response_model=ManagerSchedule)
def get_manager_schedule(
    manager_id: int,
    day: date = Query(alias="date", description="Календарный день по Алматы, YYYY-MM-DD"),
    conn: sqlite3.Connection = Depends(get_conn),
) -> dict:
    return meetings.get_manager_schedule(conn, manager_id, day)
