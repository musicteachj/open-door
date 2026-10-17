"""A turn exactly at the abandoned limit is still running, for the page and for the POST."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast

from app.ai.conversations import ABANDONED_AFTER, is_abandoned
from app.modules.assistant.display import ending

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)


def test_the_limit_is_strict() -> None:
    assert not is_abandoned(NOW - ABANDONED_AFTER, NOW)
    assert is_abandoned(NOW - ABANDONED_AFTER - timedelta(microseconds=1), NOW)
    assert not is_abandoned(NOW - ABANDONED_AFTER + timedelta(microseconds=1), NOW)


def test_the_page_agrees_at_the_limit() -> None:
    def turn(age: timedelta) -> Any:
        return cast(
            Any,
            SimpleNamespace(status="running", error_code=None, started_at=NOW - age),
        )

    assert ending(turn(ABANDONED_AFTER), NOW) == ("running", None)
    assert ending(turn(ABANDONED_AFTER + timedelta(microseconds=1)), NOW) == (
        "failed",
        "abandoned",
    )
