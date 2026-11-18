"""Calls: meeting_set must reference an active meeting of the same company."""

import pytest

from tests.conftest import MONDAY_10_00, assert_error, book, make_company, make_manager


def calls_count(db) -> int:
    return db.execute("SELECT COUNT(*) FROM calls").fetchone()[0]


def company_status(db, company_id: int) -> str:
    return db.execute("SELECT status FROM companies WHERE id = ?", (company_id,)).fetchone()[0]


def test_meeting_set_with_own_active_meeting(client, db):
    company = make_company(client)
    meeting = book(client, company, make_manager(client), MONDAY_10_00).json()

    response = client.post("/calls", json={"company_id": company, "result": "meeting_set", "meeting_id": meeting["id"]})

    assert response.status_code == 201, response.text
    assert response.json()["meeting_id"] == meeting["id"]
    assert response.json()["called_at"] == "2026-11-18T00:00:00Z"
    assert company_status(db, company) == "meeting_set"


def test_meeting_set_without_meeting_is_422(client, db):
    company = make_company(client)
    response = client.post("/calls", json={"company_id": company, "result": "meeting_set"})
    assert_error(response, 422, "meeting_required")
    assert calls_count(db) == 0
    assert company_status(db, company) == "new"


def test_meeting_set_with_nonexistent_meeting_is_422(client, db):
    company = make_company(client)
    response = client.post("/calls", json={"company_id": company, "result": "meeting_set", "meeting_id": 999})
    assert_error(response, 422, "meeting_not_found")
    assert calls_count(db) == 0


def test_meeting_set_with_another_company_meeting_is_422(client, db):
    company, other = make_company(client), make_company(client)
    foreign = book(client, other, make_manager(client), MONDAY_10_00).json()

    response = client.post("/calls", json={"company_id": company, "result": "meeting_set", "meeting_id": foreign["id"]})

    assert_error(response, 422, "meeting_of_another_company")
    assert calls_count(db) == 0


def test_meeting_set_with_cancelled_meeting_is_422(client, db):
    company = make_company(client)
    meeting = book(client, company, make_manager(client), MONDAY_10_00).json()
    client.post(f"/meetings/{meeting['id']}/cancel")

    response = client.post("/calls", json={"company_id": company, "result": "meeting_set", "meeting_id": meeting["id"]})

    assert_error(response, 422, "meeting_not_active")
    assert calls_count(db) == 0


@pytest.mark.parametrize("result", ["no_answer", "refused"])
def test_other_results_must_not_reference_a_meeting(client, db, result):
    company = make_company(client)
    meeting = book(client, company, make_manager(client), MONDAY_10_00).json()

    response = client.post("/calls", json={"company_id": company, "result": result, "meeting_id": meeting["id"]})

    assert_error(response, 422, "meeting_not_allowed")
    assert calls_count(db) == 0


def test_company_status_follows_latest_call_and_filters(client, db):
    company, untouched = make_company(client), make_company(client)
    client.post("/calls", json={"company_id": company, "result": "no_answer"})
    response = client.post("/calls", json={"company_id": company, "result": "refused", "comment": "Не интересно"})
    assert response.status_code == 201

    assert company_status(db, company) == "refused"
    refused = client.get("/companies", params={"status": "refused"}).json()
    assert [c["id"] for c in refused["items"]] == [company]
    new = client.get("/companies", params={"status": "new"}).json()
    assert [c["id"] for c in new["items"]] == [untouched]

    history = client.get("/calls", params={"company_id": company}).json()
    assert history["total"] == 2
    assert [c["result"] for c in history["items"]] == ["refused", "no_answer"]


def test_call_errors(client):
    assert_error(client.post("/calls", json={"company_id": 999, "result": "no_answer"}), 404, "company_not_found")
    company = make_company(client)
    assert_error(client.post("/calls", json={"company_id": company, "result": "maybe"}), 422, "validation_error")
    assert_error(client.get("/calls", params={"company_id": 999}), 404, "company_not_found")
