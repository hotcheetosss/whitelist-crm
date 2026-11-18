import sqlite3
from datetime import datetime
from typing import Any

from app.db import write_transaction
from app.deps import PageParams
from app.errors import NotFound, ValidationFailed
from app.rules import from_utc_text, to_utc_text
from app.schemas import CallCreate
from app.services.companies import get_company


def _check_meeting_reference(conn: sqlite3.Connection, data: CallCreate, now: datetime) -> None:
    """meeting_set must point to an existing active meeting of the same company;
    other results must not point to any meeting."""
    if data.result != "meeting_set":
        if data.meeting_id is not None:
            raise ValidationFailed(
                "meeting_not_allowed",
                "meeting_id передаётся только для результата meeting_set",
                {"result": data.result, "meeting_id": data.meeting_id},
            )
        return

    if data.meeting_id is None:
        raise ValidationFailed(
            "meeting_required",
            "Для результата meeting_set нужно указать meeting_id назначенной встречи",
        )
    meeting = conn.execute("SELECT * FROM meetings WHERE id = ?", (data.meeting_id,)).fetchone()
    if meeting is None:
        # 422, not 404: the call itself is invalid because it references nothing.
        raise ValidationFailed(
            "meeting_not_found", f"Встреча {data.meeting_id} не найдена", {"meeting_id": data.meeting_id}
        )
    if meeting["company_id"] != data.company_id:
        raise ValidationFailed(
            "meeting_of_another_company",
            "Указанная встреча назначена другой организации",
            {"meeting_id": data.meeting_id, "meeting_company_id": meeting["company_id"]},
        )
    if meeting["status"] != "scheduled" or from_utc_text(meeting["ends_at"]) <= now:
        raise ValidationFailed(
            "meeting_not_active",
            "Указанная встреча отменена или уже прошла",
            {"meeting_id": data.meeting_id, "status": meeting["status"]},
        )


def create_call(conn: sqlite3.Connection, data: CallCreate, now: datetime) -> dict[str, Any]:
    with write_transaction(conn):
        get_company(conn, data.company_id)
        _check_meeting_reference(conn, data, now)
        cursor = conn.execute(
            "INSERT INTO calls (company_id, result, meeting_id, comment, called_at) VALUES (?, ?, ?, ?, ?)",
            (data.company_id, data.result, data.meeting_id, data.comment, to_utc_text(now)),
        )
        # Company status = result of its latest call; updated in the same transaction.
        conn.execute("UPDATE companies SET status = ? WHERE id = ?", (data.result, data.company_id))
    return dict(conn.execute("SELECT * FROM calls WHERE id = ?", (cursor.lastrowid,)).fetchone())


def list_calls(conn: sqlite3.Connection, company_id: int | None, page: PageParams) -> dict[str, Any]:
    if company_id is not None:
        get_company(conn, company_id)
    total = conn.execute(
        "SELECT COUNT(*) FROM calls WHERE (? IS NULL OR company_id = ?)", (company_id, company_id)
    ).fetchone()[0]
    rows = conn.execute(
        "SELECT * FROM calls WHERE (? IS NULL OR company_id = ?)"
        " ORDER BY called_at DESC, id DESC LIMIT ? OFFSET ?",
        (company_id, company_id, page.limit, page.offset),
    ).fetchall()
    return {"items": [dict(r) for r in rows], "total": total, "limit": page.limit, "offset": page.offset}
