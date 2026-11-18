import sqlite3
from datetime import datetime
from typing import Any

from app.db import write_transaction
from app.deps import PageParams
from app.errors import Conflict, NotFound
from app.rules import to_utc_text
from app.schemas import CompanyCreate


def get_company(conn: sqlite3.Connection, company_id: int) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()
    if row is None:
        raise NotFound("company_not_found", f"Организация {company_id} не найдена", {"company_id": company_id})
    return dict(row)


def create_company(conn: sqlite3.Connection, data: CompanyCreate, now: datetime) -> dict[str, Any]:
    with write_transaction(conn):
        # Checked explicitly for a clear message; UNIQUE(bin) is the second line of defence.
        if conn.execute("SELECT 1 FROM companies WHERE bin = ?", (data.bin,)).fetchone():
            raise Conflict("duplicate_bin", f"Организация с БИН {data.bin} уже существует", {"bin": data.bin})
        cursor = conn.execute(
            "INSERT INTO companies (name, bin, phone, created_at) VALUES (?, ?, ?, ?)",
            (data.name, data.bin, data.phone, to_utc_text(now)),
        )
    return get_company(conn, cursor.lastrowid)


def list_companies(
    conn: sqlite3.Connection, status: str | None, page: PageParams
) -> dict[str, Any]:
    # "? IS NULL OR status = ?" makes the filter optional without building SQL strings.
    total = conn.execute(
        "SELECT COUNT(*) FROM companies WHERE (? IS NULL OR status = ?)", (status, status)
    ).fetchone()[0]
    rows = conn.execute(
        "SELECT * FROM companies WHERE (? IS NULL OR status = ?) ORDER BY id LIMIT ? OFFSET ?",
        (status, status, page.limit, page.offset),
    ).fetchall()
    return {"items": [dict(r) for r in rows], "total": total, "limit": page.limit, "offset": page.offset}
