"""SQLite connection, write transactions and the migration runner."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from app.config import DB_BUSY_TIMEOUT_SECONDS

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def connect(path: str) -> sqlite3.Connection:
    # isolation_level=None: the sqlite3 module must not open implicit transactions,
    # we open them explicitly with BEGIN IMMEDIATE (see write_transaction).
    # check_same_thread=False: FastAPI may run dependency setup/teardown and the
    # endpoint in different threadpool threads; one connection is still used by
    # one request at a time.
    # timeout: SQLite's busy timeout — wait this long for the write lock instead of
    # failing immediately with "database is locked" (that error becomes a 503, see main.py).
    conn = sqlite3.connect(
        path, timeout=DB_BUSY_TIMEOUT_SECONDS, isolation_level=None, check_same_thread=False
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def write_transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Run business-rule checks and writes atomically.

    BEGIN IMMEDIATE takes the database write lock *before* the checks run.
    Two concurrent requests for the same slot are therefore serialised: the second
    one waits on busy_timeout, then sees the first one's meeting and gets a conflict.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def apply_migrations(path: str) -> None:
    """Apply migrations/NNN_*.sql in name order, each one exactly once. Safe to rerun."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = connect(path)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        applied = {row["name"] for row in conn.execute("SELECT name FROM schema_migrations")}
        for migration in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if migration.name in applied:
                continue
            # executescript cannot be parameterised; the script is our own file, not
            # user input. The leading BEGIN leaves the transaction open, so the schema
            # change and its schema_migrations row are committed together.
            try:
                conn.executescript("BEGIN;\n" + migration.read_text(encoding="utf-8"))
                conn.execute(
                    "INSERT INTO schema_migrations (name, applied_at) VALUES (?, ?)",
                    (migration.name, datetime.now(timezone.utc).isoformat()),
                )
                conn.execute("COMMIT")
            except BaseException:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
    finally:
        conn.close()
