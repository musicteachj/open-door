"""The window of `unreported_outcomes`: a change counts when `changed_at <= now`."""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from app.ai.proposals import OUTCOME_PREFIX, shown_ending, unreported_outcomes

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
    id: UUID = field(default_factory=uuid4)


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
    assert unreported_outcomes([confirmed(NOW + timedelta(seconds=1))], NOW)[0] == ()


def test_a_change_at_exactly_now_is_included() -> None:
    (line,), entries = unreported_outcomes([confirmed(NOW)], NOW)
    assert line.startswith(OUTCOME_PREFIX)
    assert len(entries) == 1


def test_a_canceled_reason_that_is_not_text_is_not_shown() -> None:
    row = Row("timeoff.request", "canceled", NOW, NOW, {"reason": 5}, {})
    assert shown_ending(row, NOW) == ("canceled", None)
    assert (
        shown_ending(
            Row("timeoff.request", "canceled", NOW, NOW, {"reason": "dismissed"}, {}), NOW
        )[1]
        == "dismissed"
    )
