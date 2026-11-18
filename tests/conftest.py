"""Shared fixtures: every test gets a fresh DB in a temp folder and a fixed "now"."""

import sqlite3
from collections.abc import Iterator
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.db import connect
from app.deps import get_now
from app.main import create_app

# Wednesday 2026-11-18 05:00 Almaty. All test meetings are in the following days.
FIXED_NOW = datetime(2026, 11, 18, 0, 0, tzinfo=timezone.utc)

# Monday 2026-11-23. Almaty is UTC+5, so 09:00 local = 04:00Z, 17:00 local = 12:00Z.
MONDAY_09_00 = "2026-11-23T04:00:00Z"
MONDAY_10_00 = "2026-11-23T05:00:00Z"
MONDAY_11_00 = "2026-11-23T06:00:00Z"
TUESDAY_10_00 = "2026-11-24T05:00:00Z"


class Clock:
    """A controllable "now": tests can move time forward."""

    def __init__(self, now: datetime) -> None:
        self.now = now


@pytest.fixture
def clock() -> Clock:
    return Clock(FIXED_NOW)


@pytest.fixture
def db_path(tmp_path) -> str:
    return str(tmp_path / "test.db")


@pytest.fixture
def client(db_path: str, clock: Clock) -> Iterator[TestClient]:
    app = create_app(db_path)
    app.dependency_overrides[get_now] = lambda: clock.now
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db(db_path: str, client: TestClient) -> Iterator[sqlite3.Connection]:
    """Direct DB access to assert on stored state, not only on HTTP responses."""
    conn = connect(db_path)
    yield conn
    conn.close()


_bin_counter = iter(range(100000000000, 999999999999))


def make_company(client: TestClient, name: str = "ТОО Тестовая") -> int:
    response = client.post("/companies", json={"name": name, "bin": str(next(_bin_counter))})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def make_manager(client: TestClient, name: str = "Менеджер") -> int:
    response = client.post("/managers", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def book(client: TestClient, company_id: int, manager_id: int, starts_at: str):
    return client.post(
        "/meetings", json={"company_id": company_id, "manager_id": manager_id, "starts_at": starts_at}
    )


def assert_error(response, status: int, code: str) -> dict:
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == code
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]
    assert isinstance(body["error"]["details"], dict)
    return body["error"]
