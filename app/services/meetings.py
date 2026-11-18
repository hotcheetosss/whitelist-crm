"""Meetings: create, reschedule, cancel, read, manager's schedule.

Create and reschedule go through the same `_check_slot`, so the rules
(future time, working hours, manager overlap, one active meeting per company)
are implemented exactly once.
"""

import sqlite3
from datetime import date, datetime
from typing import Any

from app.config import BUSINESS_TZ, MEETING_DURATION
from app.db import write_transaction
from app.errors import Conflict, NotFound, ValidationFailed
from app.rules import business_day_bounds, format_local_range, from_utc_text, is_within_working_hours, to_utc_text
from app.schemas import MeetingCreate, MeetingUpdate
from app.services.companies import get_company
from app.services.managers import get_manager


def _get_meeting_row(conn: sqlite3.Connection, meeting_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM meetings WHERE id = ?", (meeting_id,)).fetchone()
    if row is None:
        raise NotFound("meeting_not_found", f"Встреча {meeting_id} не найдена", {"meeting_id": meeting_id})
    return row


def _with_history(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    events = conn.execute(
        "SELECT action, old_starts_at, new_starts_at, created_at"
        " FROM meeting_events WHERE meeting_id = ? ORDER BY id",
        (row["id"],),
    ).fetchall()
    return {**dict(row), "history": [dict(e) for e in events]}


def get_meeting(conn: sqlite3.Connection, meeting_id: int) -> dict[str, Any]:
    return _with_history(conn, _get_meeting_row(conn, meeting_id))


def _add_event(
    conn: sqlite3.Connection,
    meeting_id: int,
    action: str,
    old_starts_at: str | None,
    new_starts_at: str | None,
    now: datetime,
) -> None:
    # meeting_events is append-only: only INSERT, never UPDATE/DELETE (enforced by triggers).
    conn.execute(
        "INSERT INTO meeting_events (meeting_id, action, old_starts_at, new_starts_at, created_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (meeting_id, action, old_starts_at, new_starts_at, to_utc_text(now)),
    )


def _check_slot(
    conn: sqlite3.Connection,
    *,
    company_id: int,
    manager_id: int,
    starts_at: datetime,
    ends_at: datetime,
    now: datetime,
    exclude_meeting_id: int | None = None,
) -> None:
    """Rules shared by create and reschedule. Must run inside write_transaction.

    exclude_meeting_id: the meeting being rescheduled must not conflict with itself.
    In SQL, `id IS NOT ?` with NULL is true for every row, so on create nothing is excluded.
    """
    if starts_at <= now:
        raise ValidationFailed(
            "meeting_in_past",
            "Нельзя назначить встречу на прошедшее время",
            {"starts_at": to_utc_text(starts_at), "now": to_utc_text(now)},
        )

    if not is_within_working_hours(starts_at, ends_at):
        raise ValidationFailed(
            "outside_working_hours",
            "Встреча возможна только пн–пт с 09:00 до 18:00 по времени Алматы "
            f"(запрошено {format_local_range(starts_at, ends_at)})",
            {"starts_at": to_utc_text(starts_at), "ends_at": to_utc_text(ends_at)},
        )

    # Half-open intervals [start, end): two meetings overlap iff a.start < b.end AND b.start < a.end.
    # So 10:00–11:00 and 11:00–12:00 do NOT overlap: one ends exactly when the other starts.
    # Cancelled meetings free the slot; past scheduled ones are kept (a meeting can be in progress).
    busy = conn.execute(
        "SELECT id, starts_at, ends_at FROM meetings"
        " WHERE manager_id = ? AND status = 'scheduled' AND id IS NOT ?"
        " AND starts_at < ? AND ? < ends_at"
        " ORDER BY starts_at LIMIT 1",
        (manager_id, exclude_meeting_id, to_utc_text(ends_at), to_utc_text(starts_at)),
    ).fetchone()
    if busy is not None:
        busy_range = format_local_range(from_utc_text(busy["starts_at"]), from_utc_text(busy["ends_at"]))
        raise Conflict(
            "manager_busy",
            f"У менеджера уже есть встреча {busy_range} (Алматы) в это время",
            {"meeting_id": busy["id"], "starts_at": busy["starts_at"], "ends_at": busy["ends_at"]},
        )

    # "Active" = scheduled and not finished yet. A company may have at most one,
    # even with different managers (see README, "Принятые решения").
    active = conn.execute(
        "SELECT id, starts_at, ends_at FROM meetings"
        " WHERE company_id = ? AND status = 'scheduled' AND ends_at > ? AND id IS NOT ?"
        " LIMIT 1",
        (company_id, to_utc_text(now), exclude_meeting_id),
    ).fetchone()
    if active is not None:
        active_range = format_local_range(from_utc_text(active["starts_at"]), from_utc_text(active["ends_at"]))
        raise Conflict(
            "company_has_active_meeting",
            f"У организации уже есть активная встреча {active_range} (Алматы)",
            {"meeting_id": active["id"], "starts_at": active["starts_at"], "ends_at": active["ends_at"]},
        )


def _ensure_changeable(row: sqlite3.Row, now: datetime) -> None:
    """Only a scheduled meeting that has not started yet can be rescheduled or cancelled."""
    if row["status"] == "cancelled":
        raise Conflict("meeting_cancelled", "Встреча отменена, её нельзя изменить", {"meeting_id": row["id"]})
    if from_utc_text(row["starts_at"]) <= now:
        raise Conflict(
            "meeting_already_started",
            "Встреча уже началась или прошла, её нельзя изменить",
            {"meeting_id": row["id"], "starts_at": row["starts_at"]},
        )


def create_meeting(conn: sqlite3.Connection, data: MeetingCreate, now: datetime) -> dict[str, Any]:
    starts_at = data.starts_at
    ends_at = starts_at + MEETING_DURATION  # computed by the server, never sent by the client
    with write_transaction(conn):
        get_company(conn, data.company_id)
        get_manager(conn, data.manager_id)
        _check_slot(
            conn,
            company_id=data.company_id,
            manager_id=data.manager_id,
            starts_at=starts_at,
            ends_at=ends_at,
            now=now,
        )
        start_text = to_utc_text(starts_at)
        cursor = conn.execute(
            "INSERT INTO meetings"
            " (company_id, manager_id, starts_at, ends_at, original_starts_at, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (data.company_id, data.manager_id, start_text, to_utc_text(ends_at), start_text, to_utc_text(now)),
        )
        meeting_id = cursor.lastrowid
        _add_event(conn, meeting_id, "created", None, start_text, now)
    return get_meeting(conn, meeting_id)


def update_meeting(
    conn: sqlite3.Connection, meeting_id: int, data: MeetingUpdate, now: datetime
) -> dict[str, Any]:
    """PATCH /meetings/{id}: the schema guarantees exactly one of status / starts_at."""
    if data.status == "cancelled":
        return cancel_meeting(conn, meeting_id, now)
    return reschedule_meeting(conn, meeting_id, data.starts_at, now)


def reschedule_meeting(
    conn: sqlite3.Connection, meeting_id: int, starts_at: datetime, now: datetime
) -> dict[str, Any]:
    ends_at = starts_at + MEETING_DURATION
    with write_transaction(conn):
        row = _get_meeting_row(conn, meeting_id)
        _ensure_changeable(row, now)
        new_start_text = to_utc_text(starts_at)
        if new_start_text == row["starts_at"]:
            raise ValidationFailed(
                "same_start_time", "Встреча уже назначена на это время", {"starts_at": new_start_text}
            )
        _check_slot(
            conn,
            company_id=row["company_id"],
            manager_id=row["manager_id"],
            starts_at=starts_at,
            ends_at=ends_at,
            now=now,
            exclude_meeting_id=meeting_id,
        )
        # original_starts_at is intentionally not touched here.
        conn.execute(
            "UPDATE meetings SET starts_at = ?, ends_at = ? WHERE id = ?",
            (new_start_text, to_utc_text(ends_at), meeting_id),
        )
        _add_event(conn, meeting_id, "rescheduled", row["starts_at"], new_start_text, now)
    return get_meeting(conn, meeting_id)


def cancel_meeting(conn: sqlite3.Connection, meeting_id: int, now: datetime) -> dict[str, Any]:
    with write_transaction(conn):
        row = _get_meeting_row(conn, meeting_id)
        _ensure_changeable(row, now)
        conn.execute("UPDATE meetings SET status = 'cancelled' WHERE id = ?", (meeting_id,))
        _add_event(conn, meeting_id, "cancelled", row["starts_at"], None, now)
    return get_meeting(conn, meeting_id)


def get_manager_schedule(conn: sqlite3.Connection, manager_id: int, day: date) -> dict[str, Any]:
    """Scheduled meetings of a manager for a calendar day in Almaty. Cancelled ones are excluded."""
    get_manager(conn, manager_id)
    day_start, day_end = business_day_bounds(day)
    rows = conn.execute(
        "SELECT * FROM meetings"
        " WHERE manager_id = ? AND status = 'scheduled' AND starts_at >= ? AND starts_at < ?"
        " ORDER BY starts_at",
        (manager_id, to_utc_text(day_start), to_utc_text(day_end)),
    ).fetchall()
    return {
        "manager_id": manager_id,
        "date": day,
        "timezone": str(BUSINESS_TZ),
        "meetings": [_with_history(conn, row) for row in rows],
    }
