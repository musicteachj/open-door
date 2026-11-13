"""What the guard is shown of the turn before: its answer, or the fixed text the person was sent."""

import uuid
from typing import Any

import pytest

from app.ai.conversations import ConversationCipher
from app.ai.fixed_texts import CRISIS_TEXT, ERROR_TEXTS, UNAVAILABLE_TEXT
from app.ai.turn import _previous_answer
from app.core.encryption import new_data_key

TENANT = uuid.uuid4()
CRISIS_VERDICT = {"category": "crisis", "kind": "self_harm", "injectionSuspected": False}


def cipher() -> ConversationCipher:
    return ConversationCipher(TENANT, uuid.uuid4(), new_data_key())


def previous(
    status: str,
    error_code: str | None = None,
    verdict: dict[str, Any] | None = None,
    *,
    answer: bytes | None = None,
) -> tuple[Any, ...]:
    return (uuid.uuid4(), answer, status, error_code, verdict)


@pytest.mark.parametrize(
    ("status", "error_code"),
    [("failed", "abandoned"), ("failed", "internal"), ("running", None), ("stopped", None)],
)
def test_an_unfinished_turn_with_a_crisis_verdict_gives_the_crisis_text(
    status: str, error_code: str | None
) -> None:
    assert _previous_answer(previous(status, error_code, CRISIS_VERDICT), cipher()) == CRISIS_TEXT


def test_a_crisis_kind_under_another_category_routes_to_crisis_too() -> None:
    verdict = {"category": "ordinary", "kind": "self_harm"}

    assert _previous_answer(previous("failed", "abandoned", verdict), cipher()) == CRISIS_TEXT


@pytest.mark.parametrize(
    "verdict",
    [
        {"category": "sensitive", "kind": "harassment"},
        {"category": "ordinary", "kind": None},
        None,
    ],
)
def test_a_sensitive_or_ordinary_verdict_does_not_give_the_crisis_text(
    verdict: dict[str, Any] | None,
) -> None:
    assert _previous_answer(previous("failed", "abandoned", verdict), cipher()) is None


def test_an_old_crisis_row_without_a_verdict_still_gives_the_crisis_text() -> None:
    assert _previous_answer(previous("crisis"), cipher()) == CRISIS_TEXT


def test_an_answer_text_wins_over_a_crisis_verdict() -> None:
    c = cipher()
    turn_id = uuid.uuid4()
    sealed = c.seal_text(
        "Here is what the handbook says.", "ai_turns", "answer_ciphertext", turn_id
    )

    row = (turn_id, sealed, "failed", "abandoned", CRISIS_VERDICT)

    assert _previous_answer(row, c) == "Here is what the handbook says."


def test_the_other_fixed_texts_are_unchanged() -> None:
    c = cipher()
    assert _previous_answer(previous("guard_unavailable"), c) == UNAVAILABLE_TEXT
    assert _previous_answer(previous("failed", "refusal"), c) == ERROR_TEXTS["refusal"]
    assert (
        _previous_answer(previous("failed", "budget-sandbox"), c) == ERROR_TEXTS["budget-sandbox"]
    )
    assert _previous_answer(None, c) is None
