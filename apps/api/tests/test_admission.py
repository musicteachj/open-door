"""The room a turn needs and the size of a history, which the 429 and the banner share."""

from datetime import UTC, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.ai.admission import (
    HISTORY_OFFER_TOKENS,
    HISTORY_REFUSE_TOKENS,
    SMALLEST_QUESTION,
    WIDEST_CHARACTER,
    history_tokens,
    refusal_scope,
    room_needed_usd,
    room_scopes,
    scope_without_room,
    seconds_until_next_utc_day,
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


@pytest.mark.parametrize(
    ("now", "seconds"),
    [
        (datetime(2026, 11, 9, 0, 0, 0, tzinfo=UTC), 86_400),
        (datetime(2026, 11, 9, 12, 0, 0, tzinfo=UTC), 43_200),
        (datetime(2026, 11, 9, 23, 59, 30, 400_000, tzinfo=UTC), 30),
        (datetime(2026, 11, 9, 23, 59, 59, 999_999, tzinfo=UTC), 1),
        (datetime(2026, 12, 31, 18, 0, 0, tzinfo=UTC), 21_600),
        # Another zone's clock is still read as the instant it is: 20:00 in New York is 01:00 UTC.
        (datetime(2026, 11, 9, 20, 0, 0, tzinfo=ZoneInfo("America/New_York")), 82_800),
    ],
)
def test_retry_after_counts_whole_seconds_to_the_next_utc_midnight(
    now: datetime, seconds: int
) -> None:
    assert seconds_until_next_utc_day(now) == seconds


def test_a_sandbox_short_only_because_of_the_history_is_the_conversations_problem() -> None:
    state = BudgetState(Decimal("0.30"), Decimal("5"))
    big = Decimal("0.55")
    empty = Decimal("0.21")

    assert refusal_scope(state, big, lambda: empty) == "conversation"
    # Not even an empty conversation fits: the sandbox's own limit, as before.
    assert (
        refusal_scope(BudgetState(Decimal("0.10"), Decimal("5")), big, lambda: empty) == "sandbox"
    )
    # Room for the turn with its history: nothing refuses.
    assert refusal_scope(BudgetState(Decimal("0.60"), Decimal("5")), big, lambda: empty) is None


def test_the_day_wins_over_the_conversations_size() -> None:
    state = BudgetState(Decimal("0.30"), Decimal("0.10"))

    assert refusal_scope(state, Decimal("0.55"), lambda: Decimal("0.21")) == "daily"
    # The day alone is short for the turn: still the day.
    assert (
        refusal_scope(
            BudgetState(Decimal("5"), Decimal("0.10")), Decimal("0.55"), lambda: Decimal("0.21")
        )
        == "daily"
    )


def test_the_banner_and_the_refusal_share_one_rule() -> None:
    """`room_scopes` (the banner) and `refusal_scope` (the 429) agree on every combination."""
    cases = [
        (BudgetState(Decimal(s), Decimal(d)), Decimal("0.55"), Decimal("0.21"))
        for s in ("0.10", "0.30", "0.60")
        for d in ("0.10", "0.30", "0.60")
    ]
    for state, big, empty in cases:

        def sized(value: Decimal = empty) -> Decimal:
            return value

        sandbox_short, daily_short = room_scopes(state, big, sized)
        scope = refusal_scope(state, big, sized)
        expected = "sandbox" if sandbox_short else "daily" if daily_short else None
        if scope == "conversation":
            assert (sandbox_short, daily_short) == (False, False), state
        else:
            assert scope == expected, state
