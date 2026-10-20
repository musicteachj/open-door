"""Today at a location. The expected dates were worked out by hand from the UTC offsets.

On 2026-10-16 daylight saving time is in effect everywhere here: Pacific is UTC-7, Mountain
UTC-6, Central UTC-5, Eastern UTC-4.
"""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfoNotFoundError

import pytest

from app.domain.timeoff.today import today_at

ZONES = ["America/Los_Angeles", "America/Denver", "America/Chicago", "America/New_York"]


@pytest.mark.parametrize("zone", ZONES)
def test_at_three_in_the_morning_utc_every_location_is_still_on_the_15th(zone: str) -> None:
    # 03:00 UTC on the 16th: Los Angeles 20:00, Denver 21:00, Chicago 22:00, New York 23:00,
    # all on the 15th.
    assert today_at(zone, datetime(2026, 10, 16, 3, 0, tzinfo=UTC)) == date(2026, 10, 15)


@pytest.mark.parametrize("zone", ZONES)
def test_at_eight_in_the_morning_utc_every_location_is_on_the_16th(zone: str) -> None:
    # 08:00 UTC on the 16th: Los Angeles 01:00, Denver 02:00, Chicago 03:00, New York 04:00.
    assert today_at(zone, datetime(2026, 10, 16, 8, 0, tzinfo=UTC)) == date(2026, 10, 16)


def test_a_naive_now_is_refused() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        today_at("America/Chicago", datetime(2026, 10, 16, 3, 0))  # noqa: DTZ001 (naive on purpose)


def test_an_unknown_zone_is_refused() -> None:
    with pytest.raises(ZoneInfoNotFoundError):
        today_at("Nowhere/Land", datetime(2026, 10, 16, 3, 0, tzinfo=UTC))


@pytest.mark.parametrize("zone", ["", "../etc", "/etc/localtime"])
def test_a_malformed_zone_key_is_a_value_error(zone: str) -> None:
    # An empty, parent-relative, or absolute key is not a zone name at all.
    with pytest.raises(ValueError, match=r"."):
        today_at(zone, datetime(2026, 10, 16, 8, 0, tzinfo=UTC))
