"""FastAPI dependencies: DB connection per request and the single source of "now"."""

import sqlite3
from collections.abc import Iterator
from datetime import datetime, timezone

from fastapi import Request

from app.db import connect


def get_conn(request: Request) -> Iterator[sqlite3.Connection]:
    conn = connect(request.app.state.db_path)
    try:
        yield conn
    finally:
        conn.close()


def get_now() -> datetime:
    """The only place that reads the clock. Tests override it to a fixed moment."""
    return datetime.now(timezone.utc)
