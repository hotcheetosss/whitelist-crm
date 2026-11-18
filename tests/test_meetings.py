"""Meetings over HTTP: time handling, overlap, one active meeting per company, schedule."""

from datetime import timedelta

import pytest

from tests.conftest import (
    MONDAY_09_00,
    MONDAY_10_00,
    MONDAY_11_00,
    TUESDAY_10_00,
    assert_error,
    book,
    make_company,
    make_manager,
)


def meetings_count(db) -> int:
    return db.execute("SELECT COUNT(*) FROM meetings").fetchone()[0]


# --- Creation and time format -------------------------------------------------


def test_create_meeting_computes_end_and_normalizes_to_utc(client, db):
    company, manager = make_company(client), make_manager(client)

    response = book(client, company, manager, "2026-11-23T10:00:00+05:00")

    assert response.status_code == 201, response.text
    meeting = response.json()
    assert meeting["starts_at"] == MONDAY_10_00
    assert meeting["ends_at"] == MONDAY_11_00
    assert meeting["original_starts_at"] == MONDAY_10_00
    assert meeting["status"] == "scheduled"
    assert [e["action"] for e in meeting["history"]] == ["created"]
    stored = db.execute("SELECT starts_at, ends_at FROM meetings WHERE id = ?", (meeting["id"],)).fetchone()
    assert tuple(stored) == (MONDAY_10_00, MONDAY_11_00)


@pytest.mark.parametrize(
    "starts_at",
    [
        "2026-11-23T10:00:00",  # no timezone
        "2026-11-23T10:00:30Z",  # not a whole minute
        "not-a-date",
    ],
)
def test_invalid_start_time_is_422(client, db, starts_at):
    company, manager = make_company(client), make_manager(client)
    assert_error(book(client, company, manager, starts_at), 422, "validation_error")
    assert meetings_count(db) == 0


def test_client_cannot_send_ends_at(client, db):
    company, manager = make_company(client), make_manager(client)
    response = client.post(
        "/meetings",
        json={"company_id": company, "manager_id": manager, "starts_at": MONDAY_10_00, "ends_at": MONDAY_11_00},
    )
    assert_error(response, 422, "validation_error")


def test_meeting_in_the_past_is_rejected(client, clock, db):
    company, manager = make_company(client), make_manager(client)
    clock.now = clock.now.replace(year=2026, month=11, day=23, hour=6)  # Monday 11:00 Almaty
    assert_error(book(client, company, manager, MONDAY_10_00), 422, "meeting_in_past")
    assert meetings_count(db) == 0


def test_unknown_company_or_manager_is_404(client):
    company, manager = make_company(client), make_manager(client)
    assert_error(book(client, 999, manager, MONDAY_10_00), 404, "company_not_found")
    assert_error(book(client, company, 999, MONDAY_10_00), 404, "manager_not_found")


# --- Working hours via the API --------------------------------------------------


@pytest.mark.parametrize("starts_at", ["2026-11-23T09:00:00+05:00", "2026-11-23T17:00:00+05:00"])
def test_working_day_boundaries_allowed(client, starts_at):
    company, manager = make_company(client), make_manager(client)
    assert book(client, company, manager, starts_at).status_code == 201


@pytest.mark.parametrize(
    "starts_at",
    [
        "2026-11-23T08:59:00+05:00",
        "2026-11-23T17:01:00+05:00",
        "2026-11-23T17:30:00+05:00",
        "2026-11-21T10:00:00+05:00",  # Saturday
    ],
)
def test_outside_working_hours_rejected(client, db, starts_at):
    company, manager = make_company(client), make_manager(client)
    assert_error(book(client, company, manager, starts_at), 422, "outside_working_hours")
    assert meetings_count(db) == 0


def test_working_hours_are_checked_in_almaty_not_utc(client):
    company, manager = make_company(client), make_manager(client)
    # 07:00Z = 12:00 Almaty -> allowed.
    assert book(client, company, manager, "2026-11-23T07:00:00Z").status_code == 201
    # 14:00Z = 19:00 Almaty -> rejected, although 14:00 is a "working" hour in UTC.
    other = make_company(client)
    assert_error(book(client, other, manager, "2026-11-23T14:00:00Z"), 422, "outside_working_hours")


# --- Manager overlap ------------------------------------------------------------


def test_back_to_back_meetings_do_not_overlap(client):
    manager = make_manager(client)
    assert book(client, make_company(client), manager, MONDAY_10_00).status_code == 201
    # 11:00–12:00 starts exactly when 10:00–11:00 ends: half-open intervals, no conflict.
    assert book(client, make_company(client), manager, MONDAY_11_00).status_code == 201
    # And 09:00–10:00 ends exactly when 10:00 starts.
    assert book(client, make_company(client), manager, MONDAY_09_00).status_code == 201


@pytest.mark.parametrize(
    "starts_at",
    [
        MONDAY_10_00,  # same slot (fully nested)
        "2026-11-23T05:30:00Z",  # 10:30 — starts inside the existing meeting
        "2026-11-23T04:30:00Z",  # 09:30 — ends inside the existing meeting
        "2026-11-23T05:59:00Z",  # 10:59 — one minute of overlap
    ],
)
def test_overlapping_meeting_for_same_manager_is_409(client, db, starts_at):
    manager = make_manager(client)
    existing = book(client, make_company(client), manager, MONDAY_10_00).json()

    error = assert_error(book(client, make_company(client), manager, starts_at), 409, "manager_busy")

    assert error["details"]["meeting_id"] == existing["id"]
    assert meetings_count(db) == 1


def test_other_manager_can_take_the_same_slot(client):
    assert book(client, make_company(client), make_manager(client), MONDAY_10_00).status_code == 201
    assert book(client, make_company(client), make_manager(client), MONDAY_10_00).status_code == 201


def test_cancelled_meeting_frees_the_manager_slot(client):
    manager = make_manager(client)
    meeting = book(client, make_company(client), manager, MONDAY_10_00).json()
    assert client.patch(f"/meetings/{meeting['id']}", json={"status": "cancelled"}).status_code == 200
    assert book(client, make_company(client), manager, MONDAY_10_00).status_code == 201


# --- One active meeting per company ---------------------------------------------


def test_company_cannot_have_two_active_meetings_even_with_different_managers(client, db):
    company = make_company(client)
    assert book(client, company, make_manager(client), MONDAY_10_00).status_code == 201

    response = book(client, company, make_manager(client), TUESDAY_10_00)

    assert_error(response, 409, "company_has_active_meeting")
    assert meetings_count(db) == 1


def test_company_can_book_again_after_cancel(client):
    company, manager = make_company(client), make_manager(client)
    meeting = book(client, company, manager, MONDAY_10_00).json()
    client.patch(f"/meetings/{meeting['id']}", json={"status": "cancelled"})
    assert book(client, company, manager, TUESDAY_10_00).status_code == 201


def test_company_can_book_again_after_previous_meeting_has_ended(client, clock):
    company, manager = make_company(client), make_manager(client)
    assert book(client, company, manager, MONDAY_10_00).status_code == 201
    clock.now = clock.now.replace(day=23, hour=6)  # Monday 11:00 Almaty — the meeting just ended
    assert book(client, company, manager, TUESDAY_10_00).status_code == 201


# --- Reschedule and history -----------------------------------------------------


def test_reschedule_keeps_original_time_and_appends_history(client, db):
    meeting = book(client, make_company(client), make_manager(client), MONDAY_10_00).json()

    first = client.patch(f"/meetings/{meeting['id']}", json={"starts_at": TUESDAY_10_00})
    second = client.patch(f"/meetings/{meeting['id']}", json={"starts_at": "2026-11-25T05:00:00Z"})

    assert first.status_code == 200 and second.status_code == 200, second.text
    body = second.json()
    assert body["starts_at"] == "2026-11-25T05:00:00Z"
    assert body["ends_at"] == "2026-11-25T06:00:00Z"
    assert body["original_starts_at"] == MONDAY_10_00
    assert [(e["action"], e["old_starts_at"], e["new_starts_at"]) for e in body["history"]] == [
        ("created", None, MONDAY_10_00),
        ("rescheduled", MONDAY_10_00, TUESDAY_10_00),
        ("rescheduled", TUESDAY_10_00, "2026-11-25T05:00:00Z"),
    ]
    stored = db.execute("SELECT original_starts_at FROM meetings WHERE id = ?", (meeting["id"],)).fetchone()
    assert stored[0] == MONDAY_10_00
    assert db.execute("SELECT COUNT(*) FROM meeting_events").fetchone()[0] == 3


def test_reschedule_into_conflict_is_rejected_and_meeting_unchanged(client, db):
    manager = make_manager(client)
    book(client, make_company(client), manager, MONDAY_10_00)
    meeting = book(client, make_company(client), manager, TUESDAY_10_00).json()

    response = client.patch(f"/meetings/{meeting['id']}", json={"starts_at": "2026-11-23T05:30:00Z"})

    assert_error(response, 409, "manager_busy")
    after = client.get(f"/meetings/{meeting['id']}").json()
    assert after["starts_at"] == TUESDAY_10_00
    assert len(after["history"]) == 1


def test_reschedule_outside_working_hours_is_rejected(client):
    meeting = book(client, make_company(client), make_manager(client), MONDAY_10_00).json()
    response = client.patch(f"/meetings/{meeting['id']}", json={"starts_at": "2026-11-23T12:30:00Z"})
    assert_error(response, 422, "outside_working_hours")


def test_reschedule_may_overlap_its_own_old_slot(client):
    # Moving 10:00 -> 10:30 overlaps only the meeting itself, which must be excluded.
    meeting = book(client, make_company(client), make_manager(client), MONDAY_10_00).json()
    response = client.patch(f"/meetings/{meeting['id']}", json={"starts_at": "2026-11-23T05:30:00Z"})
    assert response.status_code == 200, response.text


def test_cancelled_meeting_cannot_be_rescheduled_or_cancelled_again(client, db):
    meeting = book(client, make_company(client), make_manager(client), MONDAY_10_00).json()
    cancelled = client.patch(f"/meetings/{meeting['id']}", json={"status": "cancelled"}).json()
    assert cancelled["status"] == "cancelled"
    assert cancelled["history"][-1] == {
        "action": "cancelled",
        "old_starts_at": MONDAY_10_00,
        "new_starts_at": None,
        "created_at": "2026-11-18T00:00:00Z",
    }

    assert_error(
        client.patch(f"/meetings/{meeting['id']}", json={"starts_at": TUESDAY_10_00}),
        409,
        "meeting_cancelled",
    )
    assert_error(client.patch(f"/meetings/{meeting['id']}", json={"status": "cancelled"}), 409, "meeting_cancelled")
    assert db.execute("SELECT COUNT(*) FROM meeting_events").fetchone()[0] == 2


def test_started_meeting_cannot_be_changed(client, clock):
    meeting = book(client, make_company(client), make_manager(client), MONDAY_10_00).json()
    clock.now = clock.now.replace(day=23, hour=5) + timedelta(minutes=10)  # 10:10 Almaty
    assert_error(
        client.patch(f"/meetings/{meeting['id']}", json={"starts_at": TUESDAY_10_00}),
        409,
        "meeting_already_started",
    )
    assert_error(client.patch(f"/meetings/{meeting['id']}", json={"status": "cancelled"}), 409, "meeting_already_started")


def test_meeting_events_table_is_append_only(client, db):
    book(client, make_company(client), make_manager(client), MONDAY_10_00)
    with pytest.raises(Exception, match="append-only"):
        db.execute("UPDATE meeting_events SET new_starts_at = NULL")
    with pytest.raises(Exception, match="append-only"):
        db.execute("DELETE FROM meeting_events")


# --- Schedule -------------------------------------------------------------------


def test_manager_schedule_for_almaty_day(client):
    manager, other_manager = make_manager(client), make_manager(client)
    late = book(client, make_company(client), manager, "2026-11-23T11:00:00Z").json()
    early = book(client, make_company(client), manager, MONDAY_09_00).json()
    cancelled = book(client, make_company(client), manager, MONDAY_10_00).json()
    client.patch(f"/meetings/{cancelled['id']}", json={"status": "cancelled"})
    book(client, make_company(client), manager, TUESDAY_10_00)  # another day
    book(client, make_company(client), other_manager, MONDAY_10_00)  # another manager

    response = client.get(f"/managers/{manager}/schedule", params={"date": "2026-11-23"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["timezone"] == "Asia/Almaty"
    assert [m["id"] for m in body["meetings"]] == [early["id"], late["id"]]


def test_schedule_errors(client):
    manager = make_manager(client)
    assert_error(client.get("/managers/999/schedule", params={"date": "2026-11-23"}), 404, "manager_not_found")
    assert_error(client.get(f"/managers/{manager}/schedule", params={"date": "23.11.2026"}), 422, "validation_error")
    assert_error(client.get(f"/managers/{manager}/schedule"), 422, "validation_error")


@pytest.mark.parametrize(
    "payload",
    [
        {},  # no action
        {"starts_at": TUESDAY_10_00, "status": "cancelled"},  # two actions at once
        {"status": "scheduled"},  # only cancelling via status is allowed
        {"starts_at": TUESDAY_10_00, "manager_id": 2},  # manager cannot be changed
    ],
)
def test_patch_requires_exactly_one_valid_action(client, payload):
    meeting = book(client, make_company(client), make_manager(client), MONDAY_10_00).json()
    assert_error(client.patch(f"/meetings/{meeting['id']}", json=payload), 422, "validation_error")
    after = client.get(f"/meetings/{meeting['id']}").json()
    assert (after["starts_at"], after["status"], len(after["history"])) == (MONDAY_10_00, "scheduled", 1)


def test_patch_unknown_meeting_is_404(client):
    assert_error(client.patch("/meetings/999", json={"status": "cancelled"}), 404, "meeting_not_found")
