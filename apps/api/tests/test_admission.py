"""The room a turn needs and the size of a history, which the 429 and the banner share."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.ai.admission import (
    HISTORY_OFFER_TOKENS,
    HISTORY_REFUSE_TOKENS,
    SMALLEST_QUESTION,
    WIDEST_CHARACTER,
    history_tokens,
    room_needed_usd,
    scope_without_room,
    short_scopes,
)
from app.ai.budget import BudgetState
from app.ai.context import ActorView, turn_context
from app.ai.conversations import CURRENT_PINS, Pins
from app.ai.guard import (
    INJECTION_NOTE,
    SENSITIVE_NOTE,
    build_guard_request,
    guard_reservation_usd,
)
from app.ai.pricing import reservation_usd
from app.ai.prompts.versions import PROMPT_VERSION, TOOLSET_VERSION
from app.ai.turn import MAX_TOKENS, first_call_input_tokens, model_request

VIEW = ActorView(
    given_name="Priya",
    role="employee",
    location_name="Denver HQ",
    city="Denver",
    state="CO",
    location_code="DEN",
    timezone="America/Denver",
    employment_type="salaried",
)
NOW = datetime(2026, 10, 15, 17, 0, tzinfo=UTC)


def needed(question: str = "How much sick leave do I get?", history: list | None = None) -> Decimal:  # type: ignore[type-arg]
    return room_needed_usd(
        model=CURRENT_PINS.model,
        guard_model=CURRENT_PINS.guard_model,
        effort=CURRENT_PINS.effort,
        history=history or [],
        question=question,
        actor_view=VIEW,
        handbook_label="2026.1",
        now=NOW,
    )


def test_a_turn_needs_more_than_the_guard_alone_and_more_than_one_call_alone() -> None:
    question = "How much sick leave do I get?"
    guard = guard_reservation_usd(build_guard_request(question, None, CURRENT_PINS.guard_model))
    bare = model_request(
        model=CURRENT_PINS.model,
        effort=CURRENT_PINS.effort,
        messages=({"role": "user", "content": [{"type": "text", "text": question}]},),
    )
    call = reservation_usd(
        CURRENT_PINS.model,
        estimated_input_tokens=first_call_input_tokens(bare),
        max_tokens=MAX_TOKENS,
    )

    assert needed(question) > guard + call


def test_the_need_is_the_guard_with_a_full_slot_plus_the_first_call_with_both_notes() -> None:
    question = "How much sick leave do I get?"
    guard = guard_reservation_usd(
        build_guard_request(question, WIDEST_CHARACTER * 1000, CURRENT_PINS.guard_model)
    )
    context = turn_context(
        VIEW,
        now=NOW,
        handbook_label="2026.1",
        operator_notes=(SENSITIVE_NOTE, INJECTION_NOTE),
    )
    request = model_request(
        model=CURRENT_PINS.model,
        effort=CURRENT_PINS.effort,
        messages=(
            {"role": "user", "content": [{"type": "text", "text": question}]},
            {"role": "system", "content": [{"type": "text", "text": context}]},
        ),
    )
    call = reservation_usd(
        CURRENT_PINS.model,
        estimated_input_tokens=first_call_input_tokens(request),
        max_tokens=MAX_TOKENS,
    )

    assert needed(question) == guard + call


def test_a_longer_question_needs_more_room() -> None:
    assert needed("x" * 2000) > needed("x")


def test_a_longer_history_needs_more_room() -> None:
    history = [{"role": "user", "content": [{"type": "text", "text": "y" * 40_000}]}]

    assert needed(history=history) > needed()


def test_the_smallest_question_is_one_character() -> None:
    assert len(SMALLEST_QUESTION) == 1


def test_the_sandbox_is_named_first_when_both_caps_are_short() -> None:
    state = BudgetState(Decimal("0.10"), Decimal("0.10"))

    assert scope_without_room(state, Decimal("0.25")) == "sandbox"


def test_the_day_is_named_when_only_it_is_short() -> None:
    state = BudgetState(Decimal("5"), Decimal("0.10"))

    assert scope_without_room(state, Decimal("0.25")) == "daily"


def test_room_exactly_equal_to_the_need_is_enough() -> None:
    # `reserve` refuses only when spent + amount is over the cap, so equal fits.
    state = BudgetState(Decimal("0.25"), Decimal("0.25"))

    assert scope_without_room(state, Decimal("0.25")) is None


def test_a_cap_with_money_left_but_less_than_a_turn_needs_has_no_room() -> None:
    # Not zero, so `BudgetState.sandbox_reached` is False, which is why a threshold is needed.
    state = BudgetState(Decimal("0.01"), Decimal("3"))

    assert not state.sandbox_reached
    assert scope_without_room(state, needed()) == "sandbox"


def test_history_tokens_grow_with_the_history_and_use_two_bytes_a_token() -> None:
    small = [{"role": "user", "content": [{"type": "text", "text": "a" * 1000}]}]
    large = [{"role": "user", "content": [{"type": "text", "text": "a" * 100_000}]}]

    assert history_tokens([]) == 1
    assert history_tokens(small) < history_tokens(large)
    assert 50_000 < history_tokens(large) < 51_000


def test_the_thresholds_are_the_specs() -> None:
    assert (HISTORY_OFFER_TOKENS, HISTORY_REFUSE_TOKENS) == (60_000, 80_000)


def test_the_banner_flags_each_cap_on_its_own() -> None:
    assert short_scopes(BudgetState(Decimal("0.10"), Decimal("5")), Decimal("0.25")) == (
        True,
        False,
    )
    assert short_scopes(BudgetState(Decimal("5"), Decimal("0.10")), Decimal("0.25")) == (
        False,
        True,
    )
    assert short_scopes(BudgetState(Decimal("0.10"), Decimal("0.10")), Decimal("0.25")) == (
        True,
        True,
    )
    assert short_scopes(BudgetState(Decimal("0.25"), Decimal("0.25")), Decimal("0.25")) == (
        False,
        False,
    )


def test_a_new_conversation_is_pinned_to_opus_with_haiku_guarding_at_low_effort() -> None:
    assert (
        Pins(
            model="claude-opus-5-5",
            guard_model="claude-haiku-5-5",
            effort="low",
            prompt_version=PROMPT_VERSION,
            toolset_version=TOOLSET_VERSION,
        )
        == CURRENT_PINS
    )


def first_call_usd(question: str) -> Decimal:
    context = turn_context(
        VIEW,
        now=NOW,
        handbook_label="2026.1",
        operator_notes=(SENSITIVE_NOTE, INJECTION_NOTE),
    )
    request = model_request(
        model=CURRENT_PINS.model,
        effort=CURRENT_PINS.effort,
        messages=(
            {"role": "user", "content": [{"type": "text", "text": question}]},
            {"role": "system", "content": [{"type": "text", "text": context}]},
        ),
    )
    return reservation_usd(
        CURRENT_PINS.model,
        estimated_input_tokens=first_call_input_tokens(request),
        max_tokens=MAX_TOKENS,
    )


@pytest.mark.parametrize("filler", ["x", "\u00e9", "\u4e2d", "\U0001f600"])
def test_the_guards_share_of_the_need_covers_any_possible_previous_answer(filler: str) -> None:
    question = "How much sick leave do I get?"
    possible = guard_reservation_usd(
        build_guard_request(question, filler * 1000, CURRENT_PINS.guard_model)
    )

    assert needed(question) - first_call_usd(question) >= possible
