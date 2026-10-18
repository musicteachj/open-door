"""When an answer counts as "not found": a rule over stored facts, never over the model's words.

A turn is not found when it completed (not cut off, no error), cited nothing, has no escalation,
was judged ordinary by the guard, and searched the handbook. Each test flips one condition.
"""

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast

import pytest

from app.modules.assistant.display import is_not_found, needs_hr_contact, shown

SEARCH: list[dict[str, Any]] = [
    {"name": "search_handbook", "inputSummary": "parking", "ok": True, "durationMs": 9}
]
ORDINARY: dict[str, Any] = {"category": "ordinary", "kind": None}
CITATION: dict[str, Any] = {"marker": 1}


def check(**changes: Any) -> bool:
    fields: dict[str, Any] = {
        "status": "completed",
        "error_code": None,
        "guard_verdict": ORDINARY,
        "citations": [],
        "tool_calls": SEARCH,
    }
    fields.update(changes)
    return is_not_found(**fields)


def test_a_completed_uncited_ordinary_answer_after_a_search_is_not_found() -> None:
    assert check() is True


@pytest.mark.parametrize(
    "changes",
    [
        pytest.param({"status": "stopped"}, id="stopped"),
        pytest.param({"status": "failed", "error_code": "model-unavailable"}, id="failed"),
        pytest.param({"status": "running"}, id="running"),
        pytest.param({"status": "crisis"}, id="crisis"),
        pytest.param({"status": "guard_unavailable"}, id="guard unavailable"),
        pytest.param({"error_code": "max-tokens"}, id="cut off"),
        pytest.param({"error_code": "guard-error"}, id="unscreened"),
        pytest.param({"citations": [CITATION]}, id="cited"),
        pytest.param({"guard_verdict": {"category": "sensitive", "kind": "pay"}}, id="sensitive"),
        pytest.param({"guard_verdict": {"category": "crisis", "kind": "self_harm"}}, id="crisis"),
        pytest.param({"guard_verdict": None}, id="no verdict"),
        pytest.param({"tool_calls": []}, id="never searched"),
        pytest.param(
            {"tool_calls": [{**SEARCH[0], "name": "find_people"}]}, id="searched only the directory"
        ),
    ],
)
def test_each_condition_flipped_once_is_not_a_not_found(changes: dict[str, Any]) -> None:
    assert check(**changes) is False


def test_a_search_that_failed_still_counts_as_a_search() -> None:
    assert check(tool_calls=[{**SEARCH[0], "ok": False}]) is True


def test_a_search_among_other_calls_counts() -> None:
    people = {**SEARCH[0], "name": "find_people"}
    assert check(tool_calls=[people, *SEARCH]) is True


NOW = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)


def stored_turn(**changes: Any) -> Any:
    fields: dict[str, Any] = {
        "status": "completed",
        "error_code": None,
        "guard_verdict": ORDINARY,
        "citations": [],
        "tool_calls": SEARCH,
        "started_at": NOW,
    }
    fields.update(changes)
    return cast(Any, SimpleNamespace(**fields))


def test_the_contacts_load_when_a_turn_is_not_found() -> None:
    assert needs_hr_contact([shown(stored_turn(), NOW)]) is True


def test_the_contacts_do_not_load_for_a_cited_answer() -> None:
    assert needs_hr_contact([shown(stored_turn(citations=[CITATION]), NOW)]) is False


def test_the_contacts_load_when_any_one_turn_needs_them() -> None:
    cited = stored_turn(citations=[CITATION])
    assert needs_hr_contact([shown(cited, NOW), shown(stored_turn(), NOW)]) is True
