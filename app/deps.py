"""FastAPI dependencies: DB connection per request, "now" and pagination params."""

import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import Query, Request

from app.config import DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT
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


@dataclass(frozen=True)
class PageParams:
    limit: int
    offset: int


def get_page_params(
    limit: int = Query(DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    offset: int = Query(0, ge=0),
) -> PageParams:
    return PageParams(limit=limit, offset=offset)
