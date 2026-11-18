"""Pure working-hours rule, including UTC -> Almaty conversion."""

from datetime import datetime, timezone

import pytest

from app.config import MEETING_DURATION
from app.rules import business_day_bounds, is_within_working_hours


def utc(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)


@pytest.mark.parametrize(
    ("starts_at", "expected", "why"),
    [
        ("2026-11-23T04:00:00Z", True, "Mon 09:00 Almaty — first allowed slot"),
        ("2026-11-23T12:00:00Z", True, "Mon 17:00 Almaty — ends exactly at 18:00"),
        ("2026-11-23T03:59:00Z", False, "Mon 08:59 Almaty — starts before 09:00"),
        ("2026-11-23T12:01:00Z", False, "Mon 17:01 Almaty — ends at 18:01"),
        ("2026-11-23T12:30:00Z", False, "Mon 17:30 Almaty — ends at 18:30"),
        ("2026-11-23T13:00:00Z", False, "Mon 18:00 Almaty — after work"),
        ("2026-11-21T05:00:00Z", False, "Saturday"),
        ("2026-11-22T05:00:00Z", False, "Sunday"),
        # 10:00 UTC on Monday looks like a working hour in UTC, but it is 15:00 in Almaty — allowed;
        # 20:00 UTC Monday is 01:00 Tuesday in Almaty — not allowed.
        ("2026-11-23T10:00:00Z", True, "Mon 15:00 Almaty"),
        ("2026-11-23T20:00:00Z", False, "Tue 01:00 Almaty"),
        # Friday 23:00 UTC is already Saturday 04:00 in Almaty.
        ("2026-11-27T23:00:00Z", False, "Sat 04:00 Almaty"),
    ],
)
def test_working_hours(starts_at: str, expected: bool, why: str) -> None:
    start = utc(starts_at)
    assert is_within_working_hours(start, start + MEETING_DURATION) is expected, why


def test_offset_is_taken_from_tz_database_not_hardcoded() -> None:
    # Before 2024-03-01 Almaty was UTC+6: 03:00Z was 09:00 local -> allowed.
    before = utc("2024-02-26T03:00:00Z")  # Monday
    assert is_within_working_hours(before, before + MEETING_DURATION)
    # After the switch to UTC+5 the same UTC time is 08:00 local -> not allowed.
    after = utc("2024-03-04T03:00:00Z")  # Monday
    assert not is_within_working_hours(after, after + MEETING_DURATION)


def test_business_day_bounds_are_almaty_midnights() -> None:
    start, end = business_day_bounds(datetime(2026, 11, 23).date())
    assert start == utc("2026-11-22T19:00:00Z")
    assert end == utc("2026-11-23T19:00:00Z")
