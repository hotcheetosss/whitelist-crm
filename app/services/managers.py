import sqlite3
from datetime import datetime
from typing import Any

from app.db import write_transaction
from app.deps import PageParams
from app.errors import NotFound
from app.rules import to_utc_text
from app.schemas import ManagerCreate


def get_manager(conn: sqlite3.Connection, manager_id: int) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM managers WHERE id = ?", (manager_id,)).fetchone()
    if row is None:
        raise NotFound("manager_not_found", f"Менеджер {manager_id} не найден", {"manager_id": manager_id})
    return dict(row)


def create_manager(conn: sqlite3.Connection, data: ManagerCreate, now: datetime) -> dict[str, Any]:
    with write_transaction(conn):
        cursor = conn.execute(
            "INSERT INTO managers (name, created_at) VALUES (?, ?)", (data.name, to_utc_text(now))
        )
    return get_manager(conn, cursor.lastrowid)


def list_managers(conn: sqlite3.Connection, page: PageParams) -> dict[str, Any]:
    total = conn.execute("SELECT COUNT(*) FROM managers").fetchone()[0]
    rows = conn.execute(
        "SELECT * FROM managers ORDER BY id LIMIT ? OFFSET ?", (page.limit, page.offset)
    ).fetchall()
    return {"items": [dict(r) for r in rows], "total": total, "limit": page.limit, "offset": page.offset}
