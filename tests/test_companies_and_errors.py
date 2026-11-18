"""Companies, managers, pagination and the unified error format (no 500 for client errors)."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services import companies
from tests.conftest import assert_error, make_company


def test_create_company(client, db):
    response = client.post("/companies", json={"name": "  ТОО Пример  ", "bin": "990140000001", "phone": "+77001234567"})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "ТОО Пример"
    assert body["status"] == "new"
    assert db.execute("SELECT COUNT(*) FROM companies").fetchone()[0] == 1


def test_duplicate_bin_is_409(client, db):
    client.post("/companies", json={"name": "Первая", "bin": "990140000001"})
    response = client.post("/companies", json={"name": "Вторая", "bin": "990140000001"})
    assert_error(response, 409, "duplicate_bin")
    assert db.execute("SELECT COUNT(*) FROM companies").fetchone()[0] == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "Х", "bin": "12345"},  # too short
        {"name": "Х", "bin": "12345678901a"},  # not digits
        {"name": "Х", "bin": "1234567890123"},  # too long
        {"name": "   ", "bin": "990140000001"},  # blank name
        {"bin": "990140000001"},  # missing name
        {"name": "Х", "bin": "990140000001", "extra": 1},  # unknown field
    ],
)
def test_invalid_company_is_422(client, db, payload):
    assert_error(client.post("/companies", json=payload), 422, "validation_error")
    assert db.execute("SELECT COUNT(*) FROM companies").fetchone()[0] == 0


def test_pagination(client):
    ids = [make_company(client, f"Компания {i}") for i in range(5)]
    page = client.get("/companies", params={"limit": 2, "offset": 2}).json()
    assert page["total"] == 5
    assert (page["limit"], page["offset"]) == (2, 2)
    assert [c["id"] for c in page["items"]] == ids[2:4]


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"status": "unknown"}])
def test_invalid_pagination_is_422(client, params):
    assert_error(client.get("/companies", params=params), 422, "validation_error")


def test_managers(client):
    created = client.post("/managers", json={"name": "Айгерим"})
    assert created.status_code == 201
    assert client.get("/managers").json()["total"] == 1
    assert_error(client.post("/managers", json={"name": ""}), 422, "validation_error")


def test_not_found_formats(client):
    assert_error(client.get("/companies/999"), 404, "company_not_found")
    assert_error(client.get("/meetings/999"), 404, "meeting_not_found")
    assert_error(client.get("/no-such-route"), 404, "not_found")
    assert_error(client.delete("/companies"), 405, "method_not_allowed")


def test_malformed_json_is_422(client):
    response = client.post("/companies", content=b"{not json", headers={"content-type": "application/json"})
    assert_error(response, 422, "validation_error")


def test_unexpected_error_is_generic_500_without_internals(db_path, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("secret internal detail: /var/lib/db")

    monkeypatch.setattr(companies, "list_companies", broken)
    with TestClient(create_app(db_path), raise_server_exceptions=False) as client:
        response = client.get("/companies")

    error = assert_error(response, 500, "internal_error")
    assert "secret" not in response.text
    assert error["details"] == {}
