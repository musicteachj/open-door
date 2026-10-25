"""The window of `outcomes_since`: a change counts when `since < changed_at <= now`."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from app.ai.proposals import OUTCOME_PREFIX, outcomes_since

SINCE = datetime(2026, 10, 21, 18, 0, tzinfo=UTC)
NOW = SINCE + timedelta(hours=1)


@dataclass(frozen=True)
class Row:
    action: str
    status: str
    expires_at: datetime
    ended_at: datetime | None
    outcome: dict[str, Any] | None
    card: dict[str, Any]


def confirmed(ended: datetime) -> Row:
    return Row(
        "timeoff.request",
        "confirmed",
        SINCE + timedelta(hours=3),
        ended,
        {"code": "ok"},
        {
            "type": "pto",
            "startDate": "2026-10-23",
            "endDate": "2026-10-23",
            "approver": {"name": "Marcus Bell"},
        },
    )


def test_a_change_after_now_is_left_for_the_next_turn() -> None:
    assert outcomes_since([confirmed(NOW + timedelta(seconds=1))], SINCE, NOW) == ()


def test_a_change_at_exactly_now_is_included() -> None:
    (line,) = outcomes_since([confirmed(NOW)], SINCE, NOW)
    assert line.startswith(OUTCOME_PREFIX)


def test_a_change_at_since_is_excluded_and_one_just_after_is_included() -> None:
    assert outcomes_since([confirmed(SINCE)], SINCE, NOW) == ()
    assert len(outcomes_since([confirmed(SINCE + timedelta(seconds=1))], SINCE, NOW)) == 1
