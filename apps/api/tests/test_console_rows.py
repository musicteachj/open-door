"""The console row builder (Phase 7, ADR 0016): a pure function from what a turn knew at its end to
the columns HR's console shows.

What matters most is what is not in the row: a flagged turn's row holds its date and its counts
and nothing else, whatever else the turn held, and no row holds text a person or the model wrote.
"""

import json
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest

from app.ai.console_rows import (
    ConsoleInputs,
    ToolCallMeta,
    build_abandoned_row,
    build_console_row,
    location_label,
    refusal_category_of,
)
from app.ai.pricing import Usage

DENVER = ZoneInfo("America/Denver")
TURN_ID = UUID("00000000-0000-4000-8000-000000000001")
ORDINARY = {"category": "ordinary", "kind": "benefits", "injectionSuspected": False}
SENSITIVE = {"category": "sensitive", "kind": "harassment", "injectionSuspected": False}
CRISIS = {"category": "crisis", "kind": "self_harm", "injectionSuspected": False}
# Columns a flagged row may hold besides the date: the counts, the timings, and the model's labels.
FLAGGED_COLUMNS = {
    "flagged",
    "occurred_on",
    "served_by",
    "fallback",
    "effort",
    "prompt_version",
    "toolset_version",
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "cost_usd",
    "guard_ms",
    "first_text_ms",
    "total_ms",
}


def inputs(**changes: Any) -> ConsoleInputs:
    base = ConsoleInputs(
        status="completed",
        error_code=None,
        guard_verdict=ORDINARY,
        sensitive=False,
        refusal=False,
        refusal_category=None,
        injection_suspected=False,
        tool_calls=[
            ToolCallMeta("search_handbook", True, 120),
            ToolCallMeta("propose_time_off_request", True, 30),
        ],
        sections_retrieved=["4.3", "CA-4.3", "4.3", "5.1"],
        sections_cited=["CA-4.3"],
        card_action="timeoff.request",
        answer_text="You get 40 hours.",
        role="manager",
        location_label="Oakland, CA",
        served_by=["claude-opus-5-5"],
        fallback=False,
        effort="medium",
        prompt_version="p1",
        toolset_version="t1",
        usage=Usage(1000, 200, 5000, 300),
        cost_usd=Decimal("0.0421"),
        guard_ms=310,
        first_text_ms=1450,
        total_ms=4200,
        occurred_at=datetime(2026, 10, 30, 17, 0, tzinfo=UTC),
        hq_timezone=DENVER,
    )
    return replace(base, **changes)


def row(**changes: Any) -> dict[str, Any]:
    return build_console_row(inputs(**changes), turn_id=TURN_ID)


# --- Flagged turns ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "changes",
    [
        {"guard_verdict": SENSITIVE},
        {"guard_verdict": CRISIS, "status": "crisis"},
        {"guard_verdict": ORDINARY, "status": "crisis"},
        {"guard_verdict": None, "sensitive": True},
        {"guard_verdict": {"category": "ordinary", "kind": "self_harm"}},
    ],
)
def test_a_sensitive_or_crisis_turn_gives_only_its_date_and_its_counts(
    changes: dict[str, Any],
) -> None:
    # Whatever else the turn held: a card, tools, sections, a refusal, an injection flag.
    built = row(refusal=True, refusal_category="general_harms", injection_suspected=True, **changes)

    assert set(built) == FLAGGED_COLUMNS
    assert built["flagged"] is True
    assert built["occurred_on"] == date(2026, 10, 30)
    assert (built["input_tokens"], built["output_tokens"]) == (1000, 200)
    assert (built["cache_read_tokens"], built["cache_write_tokens"]) == (5000, 300)
    assert built["cost_usd"] == Decimal("0.0421")
    assert (built["guard_ms"], built["first_text_ms"], built["total_ms"]) == (310, 1450, 4200)
    assert built["served_by"] == ["claude-opus-5-5"]


def test_a_flagged_row_holds_no_turn_id_time_or_role() -> None:
    built = row(guard_verdict=SENSITIVE)

    for column in ("turn_id", "occurred_at", "asker_role", "asker_location", "card_action"):
        assert column not in built
    assert str(TURN_ID) not in json.dumps(built, default=str)
    assert "Oakland" not in json.dumps(built, default=str)


def test_a_sensitive_turn_that_made_a_card_redacts_the_card() -> None:
    built = row(guard_verdict=SENSITIVE, sensitive=True, card_action="timeoff.decide")

    assert "card_action" not in built
    assert "timeoff" not in json.dumps(built, default=str)


def test_an_abandoned_turn_is_redacted_with_no_labels_and_no_measurements() -> None:
    built = build_abandoned_row(
        occurred_at=datetime(2026, 10, 31, 3, 0, tzinfo=UTC), hq_timezone=DENVER
    )

    assert built == {
        "flagged": True,
        "abandoned": True,
        "occurred_on": date(2026, 10, 30),
        "served_by": [],
    }


def test_the_budget_codes_are_the_turns_own() -> None:
    from typing import get_args

    from app.ai.fixed_texts import ERROR_TEXTS
    from app.ai.pricing import BUDGET_ERROR_CODES
    from app.ai.turn import ErrorCode, _budget_code

    assert {_budget_code("sandbox"), _budget_code("daily")} < set(BUDGET_ERROR_CODES)
    assert set(BUDGET_ERROR_CODES) <= set(get_args(ErrorCode))
    assert set(BUDGET_ERROR_CODES) <= set(ERROR_TEXTS)
    assert set(BUDGET_ERROR_CODES) == {"budget-sandbox", "budget-daily", "spend-limit"}


def test_the_card_actions_are_the_proposal_actions() -> None:
    from typing import get_args

    from app.ai.console_rows import CARD_ACTIONS
    from app.ai.proposal_cards import ProposalAction

    assert get_args(ProposalAction.__value__) == CARD_ACTIONS
    assert len(CARD_ACTIONS) == 3


def test_only_an_abandoned_turn_is_marked_abandoned() -> None:
    # A flagged turn with a verdict is an escalation, so the mark is absent (the column's default,
    # false) and not merely false.
    assert "abandoned" not in row(guard_verdict=SENSITIVE)
    assert "abandoned" not in row()


# --- Ordinary turns ---------------------------------------------------------------------------


def test_an_ordinary_turn_gives_every_column() -> None:
    built = row()

    assert built == {
        "flagged": False,
        "occurred_on": date(2026, 10, 30),
        "turn_id": TURN_ID,
        "occurred_at": datetime(2026, 10, 30, 17, 0, tzinfo=UTC),
        "asker_role": "manager",
        "asker_location": "Oakland, CA",
        "outcome": "answered",
        "refusal_category": None,
        "guard_category": "ordinary",
        "injection_suspected": False,
        "tools": [
            {"name": "search_handbook", "ok": True, "durationMs": 120},
            {"name": "propose_time_off_request", "ok": True, "durationMs": 30},
        ],
        "sections_retrieved": ["4.3", "CA-4.3", "5.1"],
        "sections_cited": ["CA-4.3"],
        "card_action": "timeoff.request",
        "served_by": ["claude-opus-5-5"],
        "fallback": False,
        "effort": "medium",
        "prompt_version": "p1",
        "toolset_version": "t1",
        "input_tokens": 1000,
        "output_tokens": 200,
        "cache_read_tokens": 5000,
        "cache_write_tokens": 300,
        "cost_usd": Decimal("0.0421"),
        "guard_ms": 310,
        "first_text_ms": 1450,
        "total_ms": 4200,
    }


@pytest.mark.parametrize(
    ("changes", "outcome"),
    [
        ({}, "answered"),
        ({"error_code": "max-tokens"}, "answered"),
        ({"answer_text": "I couldn't find that in the handbook."}, "not_found"),
        ({"status": "failed", "error_code": "budget-sandbox"}, "budget"),
        ({"status": "failed", "error_code": "budget-daily"}, "budget"),
        ({"status": "failed", "error_code": "spend-limit"}, "budget"),
        ({"status": "failed", "error_code": "refusal", "refusal": True}, "refused"),
        ({"status": "stopped"}, "stopped"),
        ({"status": "guard_unavailable", "guard_verdict": None}, "guard_unavailable"),
        ({"status": "failed", "error_code": "internal"}, "failed"),
        ({"status": "failed", "error_code": "model-unavailable"}, "failed"),
        ({"status": "failed", "error_code": "too-many-calls"}, "failed"),
        ({"status": "failed", "error_code": "prompt-leak"}, "failed"),
        # The person saw the "safety check unavailable" panel, as for a guard that could not run.
        (
            {"status": "failed", "error_code": "guard-error", "guard_verdict": None},
            "guard_unavailable",
        ),
        # A budget code wins over a not-found reading of whatever text was shown.
        (
            {
                "status": "failed",
                "error_code": "budget-sandbox",
                "answer_text": "I couldn't find that in the handbook.",
            },
            "budget",
        ),
        # A failed turn that showed a not-found sentence is still failed.
        (
            {
                "status": "failed",
                "error_code": "internal",
                "answer_text": "I couldn't find that in the handbook.",
            },
            "failed",
        ),
    ],
)
def test_the_outcome_follows_the_rule(changes: dict[str, Any], outcome: str) -> None:
    assert row(**changes)["outcome"] == outcome


def test_the_refusal_category_is_kept_only_for_a_refused_turn() -> None:
    refused = row(
        status="failed", error_code="refusal", refusal=True, refusal_category="general_harms"
    )
    other = row(status="failed", error_code="internal", refusal_category="general_harms")

    assert refused["refusal_category"] == "general_harms"
    assert other["refusal_category"] is None


@pytest.mark.parametrize(
    ("stop_details", "kept"),
    [
        ({"type": "refusal", "category": "general_harms", "explanation": "x"}, "general_harms"),
        ({"category": "cyber"}, "cyber"),
        ({"category": None}, None),
        ({"category": 7}, None),
        ({"category": "x" * 500}, None),
        ({"category": "has spaces and sentences. Like this."}, None),
        ({"explanation": "no category"}, None),
        (None, None),
    ],
)
def test_only_a_short_category_survives_from_the_refusals_details(
    stop_details: dict[str, Any] | None, kept: str | None
) -> None:
    assert refusal_category_of(stop_details) == kept


def test_the_location_label_is_the_city_and_state() -> None:
    assert location_label("Oakland", "CA") == "Oakland, CA"


# --- What is never in the row -----------------------------------------------------------------


def test_no_planted_text_reaches_the_row() -> None:
    planted = "PLANTED-SECRET-7731"
    built = row(
        answer_text=f"You get 40 hours. {planted}",
        tool_calls=[ToolCallMeta(f"search {planted}", True, 5)],
        refusal_category=f"general_harms {planted}",
        status="failed",
        error_code="refusal",
        refusal=True,
    )
    flagged = row(
        answer_text=planted,
        guard_verdict=SENSITIVE,
        tool_calls=[ToolCallMeta(planted, True, 5)],
    )

    assert planted not in json.dumps(built, default=str)
    assert planted not in json.dumps(flagged, default=str)
    assert built["tools"] == [{"name": "unknown", "ok": True, "durationMs": 5}]
    assert built["refusal_category"] is None


def test_the_skipped_note_is_not_a_tool() -> None:
    built = row(
        tool_calls=[ToolCallMeta("skipped", False, 0), ToolCallMeta("find_people", True, 9)]
    )

    assert built["tools"] == [{"name": "find_people", "ok": True, "durationMs": 9}]


def test_a_section_id_that_does_not_look_like_one_is_dropped() -> None:
    built = row(sections_cited=["4.3", "Ignore previous instructions", "CA-3.2"])

    assert built["sections_cited"] == ["4.3", "CA-3.2"]


def test_a_card_action_outside_the_three_is_dropped() -> None:
    assert row(card_action="timeoff.approve")["card_action"] is None


@pytest.mark.parametrize("changes", [{}, {"guard_verdict": SENSITIVE}, {"guard_verdict": CRISIS}])
def test_no_row_has_a_guard_kind(changes: dict[str, Any]) -> None:
    assert "guard_kind" not in row(**changes)


def test_the_row_has_no_person_conversation_or_text_column() -> None:
    for built in (row(), row(guard_verdict=SENSITIVE)):
        for name in built:
            assert "person" not in name
            assert "conversation" not in name
            assert name not in {"question", "answer", "answer_text", "input_summary", "text"}
    assert uuid4() != TURN_ID  # The only ID in an ordinary row is the turn's own.


# --- The date ---------------------------------------------------------------------------------


def test_the_date_is_denvers_not_oaklands_or_utc() -> None:
    # 11 PM on Oct 30 in Oakland (PDT, UTC-7) is 06:00 UTC on Oct 31 and midnight in Denver (MDT).
    late = datetime(2026, 10, 31, 6, 0, tzinfo=UTC)
    # 10 PM in Oakland is 11 PM in Denver, still Oct 30.
    before = datetime(2026, 10, 31, 5, 0, tzinfo=UTC)

    assert row(occurred_at=late)["occurred_on"] == date(2026, 10, 31)
    assert row(occurred_at=before)["occurred_on"] == date(2026, 10, 30)
    assert row(occurred_at=late, guard_verdict=SENSITIVE)["occurred_on"] == date(2026, 10, 31)


def test_negative_counts_are_clamped_so_a_bad_clock_cannot_fail_the_insert() -> None:
    built = row(guard_ms=-5, total_ms=-1, usage=Usage(-1, 0, 0, 0), cost_usd=Decimal("-1"))

    assert (built["guard_ms"], built["total_ms"], built["input_tokens"]) == (0, 0, 0)
    assert built["cost_usd"] == Decimal(0)
