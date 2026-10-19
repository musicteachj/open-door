"""Which escalation the page shows for a turn, by how it ended."""

from app.modules.assistant.display import escalation_kind

SENSITIVE = {"category": "sensitive", "kind": "harassment_discrimination"}
ROUTINE = {"category": "policy", "kind": None}


def test_a_stopped_sensitive_turn_shows_the_hr_panel() -> None:
    assert escalation_kind("stopped", None, SENSITIVE) == "sensitive"


def test_a_stopped_turn_without_a_sensitive_verdict_shows_none() -> None:
    assert escalation_kind("stopped", None, ROUTINE) is None
    assert escalation_kind("stopped", None, None) is None


def test_an_abandoned_turn_shows_none_even_with_a_sensitive_verdict() -> None:
    assert escalation_kind("failed", "abandoned", SENSITIVE) is None
