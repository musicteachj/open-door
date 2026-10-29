"""Which escalation the page shows for a turn, by how it ended."""

from app.ai.guard import escalation_for_verdict
from app.modules.assistant.display import escalation_kind, is_not_found

SENSITIVE = {"category": "sensitive", "kind": "harassment_discrimination"}
ROUTINE = {"category": "policy", "kind": None}


def test_a_stopped_sensitive_turn_shows_the_hr_panel() -> None:
    assert escalation_kind("stopped", None, SENSITIVE) == "sensitive"


def test_a_stopped_turn_without_a_sensitive_verdict_shows_none() -> None:
    assert escalation_kind("stopped", None, ROUTINE) is None
    assert escalation_kind("stopped", None, None) is None


def test_an_abandoned_turn_shows_none_even_with_a_sensitive_verdict() -> None:
    assert escalation_kind("failed", "abandoned", SENSITIVE) is None


def test_an_ordinary_verdict_with_a_topic_shows_no_panel_on_reload() -> None:
    ordinary_with_kind = {"category": "ordinary", "kind": "pay"}
    assert escalation_kind("completed", None, ordinary_with_kind) is None
    assert escalation_kind("stopped", None, ordinary_with_kind) is None


def test_a_sensitive_verdict_with_no_topic_shows_the_panel_on_reload() -> None:
    assert (
        escalation_kind("completed", None, {"category": "sensitive", "kind": None}) == "sensitive"
    )


def test_the_reload_and_the_stream_share_one_predicate() -> None:
    for category in ("ordinary", "sensitive"):
        for kind in (None, "pay", "other", "safety"):
            verdict = {"category": category, "kind": kind}
            assert (escalation_kind("completed", None, verdict) == "sensitive") is (
                escalation_for_verdict(category, kind) == "sensitive"
            )


def test_an_ordinary_turn_with_a_topic_can_still_be_not_found() -> None:
    # No panel from the guard, so the "not found" offer applies as for any ordinary turn.
    assert is_not_found(
        status="completed",
        error_code=None,
        guard_verdict={"category": "ordinary", "kind": "pay"},
        citations=[],
        tool_calls=[{"name": "search_handbook"}],
    )
