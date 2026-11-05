"""The console's tiles on plain values, with every figure worked out by hand.

`HAND_WORKED` is thirteen console rows. The comment beside each figure shows its working, so it can
be checked without running the code. `tests/integration/test_console_routes.py` writes the same rows
to the database and expects the same figures from the route.
"""

from dataclasses import fields
from decimal import Decimal

import pytest
from pydantic import BaseModel

from app.modules.console import metrics as metrics_module
from app.modules.console import schemas
from app.modules.console.metrics import (
    ConsoleMetrics,
    TurnFacts,
    compute_metrics,
    is_small_sample,
    percentile,
)

D = Decimal


def facts(
    outcome: str | None = "answered",
    *,
    flagged: bool = False,
    abandoned: bool = False,
    fallback: bool = False,
    injection: bool | None = False,
    first_text_ms: int | None = None,
    guard_ms: int | None = None,
    cost: str = "0",
    sections: tuple[str, ...] | None = (),
) -> TurnFacts:
    return TurnFacts(
        flagged=flagged,
        abandoned=abandoned,
        outcome=outcome,
        fallback=fallback,
        injection_suspected=injection,
        first_text_ms=first_text_ms,
        guard_ms=guard_ms,
        cost_usd=D(cost),
        sections_retrieved=sections,
    )


# Row:   outcome, first token ms, safety ms, cost, and what is special
HAND_WORKED = [
    facts("answered", first_text_ms=1000, guard_ms=200, cost="0.010", sections=("9.9",)),  # 1
    facts("answered", first_text_ms=1200, guard_ms=300, cost="0.020"),  # 2
    facts("answered", first_text_ms=1400, guard_ms=400, cost="0.030"),  # 3
    facts("answered", first_text_ms=1600, guard_ms=500, cost="0.040"),  # 4
    facts("answered", first_text_ms=2000, guard_ms=600, cost="0.050", injection=True),  # 5
    facts("answered", first_text_ms=2400, guard_ms=700, cost="0.060", fallback=True),  # 6
    facts(
        "not_found", first_text_ms=1800, guard_ms=250, cost="0.015", sections=("4.1", "4.3")
    ),  # 7
    facts(
        "not_found", first_text_ms=2600, guard_ms=350, cost="0.025", sections=("4.3", "CA-1.2")
    ),  # 8
    facts("refused", guard_ms=800, cost="0.005", fallback=True),  # 9: no first word
    facts("failed", cost="0.002"),  # 10: no timings at all
    facts(  # 11: flagged (sensitive), keeps its timings
        None,
        flagged=True,
        injection=None,
        first_text_ms=900,
        guard_ms=450,
        cost="0.012",
        sections=None,
    ),
    facts(  # 12: flagged (crisis), no first word
        None, flagged=True, injection=None, guard_ms=150, cost="0.003", sections=None
    ),
    # 13: abandoned (a worker died): a turn, but not an escalation. Flagged (redacted), and it
    # has no timings, no cost, and no outcome.
    facts(None, flagged=True, abandoned=True, injection=None, sections=None),
]
SPEND = D("0.40")
CAP = D("1.00")
CONFIRMED = {"timeoff.request": 2, "timeoff.decide": 1}


def worked() -> ConsoleMetrics:
    return compute_metrics(HAND_WORKED, spend_usd=SPEND, cap_usd=CAP, confirmed=CONFIRMED)


def test_turns_are_every_row_flagged_ones_included() -> None:
    assert len(HAND_WORKED) == 13
    assert worked().turns == 13


def test_time_to_first_token() -> None:
    tile = worked().first_token

    # Rows with a first word: 1..8 and 11 (rows 9, 10, 12, 13 have none), so 9 values.
    # Sorted: 900, 1000, 1200, 1400, 1600, 1800, 2000, 2400, 2600.
    assert tile.sample_size == 9
    # p50: rank ceil(50 * 9 / 100) = ceil(4.5) = 5, the 5th value: 1600.
    assert tile.p50_ms == 1600
    # p95: rank ceil(95 * 9 / 100) = ceil(8.55) = 9, the 9th value: 2600.
    assert tile.p95_ms == 2600
    assert tile.target_ms == 3000
    assert tile.small_sample is True


def test_safety_check_time() -> None:
    tile = worked().safety_check

    # Rows with a safety time: all but rows 10 and 13, so 11 values.
    # Sorted: 150, 200, 250, 300, 350, 400, 450, 500, 600, 700, 800.
    assert tile.sample_size == 11
    # p95: rank ceil(95 * 11 / 100) = ceil(10.45) = 11, the 11th value: 800.
    assert tile.p95_ms == 800
    assert tile.target_ms == 800
    assert tile.small_sample is True


def test_cost_per_answered_question_counts_only_answered_rows() -> None:
    tile = worked().cost

    # Answered: rows 1..6, costs 0.010 + 0.020 + 0.030 + 0.040 + 0.050 + 0.060 = 0.210.
    # The not-found, refused, failed, and flagged rows are not answered questions.
    assert tile.answered_count == 6
    # Mean: 0.210 / 6 = 0.035.
    assert tile.per_answered_question_usd == D("0.035")
    assert (tile.sandbox_spend_usd, tile.sandbox_cap_usd) == (D("0.40"), D("1.00"))
    assert tile.small_sample is True


def test_escalation_rate_is_flagged_over_turns() -> None:
    tile = worked().escalation

    # Flagged and not abandoned: rows 11 and 12 = 2. Row 13 is flagged too, but a worker died and
    # no verdict was stored, so it is a turn and not an escalation. Turns: 13. 2 / 13.
    assert (tile.flagged_count, tile.turns) == (2, 13)
    assert tile.rate == pytest.approx(2 / 13)


def test_abandoned_turns_are_turns_but_not_escalations() -> None:
    rows = [facts(None, flagged=True, abandoned=True, injection=None, sections=None)] * 3
    tile = compute_metrics(rows, spend_usd=D(0), cap_usd=CAP, confirmed={}).escalation

    assert (tile.flagged_count, tile.turns, tile.rate) == (0, 3, 0.0)


def test_refusals_and_fallbacks_count_a_row_that_is_both_once() -> None:
    tile = worked().refusals

    # Refused: row 9 = 1. Another model served: rows 6 and 9 = 2.
    assert (tile.refused_count, tile.fallback_count) == (1, 2)
    # Either: rows 6 and 9 = 2 (row 9 is both, so 1 + 2 = 3 would count it twice). 2 / 13.
    assert tile.affected_count == 2
    assert tile.rate == pytest.approx(2 / 13)


def test_not_found_counts_its_rows_and_the_sections_they_retrieved() -> None:
    tile = worked().not_found

    # Not found: rows 7 and 8 = 2, of 13 turns.
    assert (tile.count, tile.turns) == (2, 13)
    # Their sections: 4.1 once (row 7), 4.3 twice (rows 7 and 8), CA-1.2 once (row 8).
    # Row 1's "9.9" is an answered row's and doesn't count.
    # Most frequent first: 4.3 (2). The two with 1 go by ID ascending: "4.1" before "CA-1.2".
    assert [(item.section_id, item.count) for item in tile.sections] == [
        ("4.3", 2),
        ("4.1", 1),
        ("CA-1.2", 1),
    ]


def test_possible_injections_count_the_marked_rows() -> None:
    # Row 5 only. Flagged rows hold no flag (null), so they are not counted.
    assert (worked().injections.count, worked().injections.turns) == (1, 13)


def test_every_tile_of_thirteen_turns_is_a_small_sample() -> None:
    metrics = worked()

    assert metrics.small_sample is True
    assert metrics.escalation.small_sample is True
    assert metrics.refusals.small_sample is True
    assert metrics.not_found.small_sample is True
    assert metrics.injections.small_sample is True


def test_cards_confirmed_always_lists_the_three_actions_with_zeros() -> None:
    cards = worked().cards_confirmed

    assert [(item.action, item.count) for item in cards] == [
        ("timeoff.request", 2),
        ("timeoff.decide", 1),
        ("timeoff.cancel", 0),
    ]


# --- Edges ---------------------------------------------------------------------------------------


def test_no_rows_gives_empty_tiles_with_nothing_to_divide() -> None:
    metrics = compute_metrics([], spend_usd=D("0"), cap_usd=CAP, confirmed={})

    assert metrics.turns == 0
    assert (metrics.first_token.p50_ms, metrics.first_token.p95_ms) == (None, None)
    assert metrics.safety_check.p95_ms is None
    assert metrics.cost.per_answered_question_usd is None
    assert metrics.escalation.rate is None
    assert metrics.refusals.rate is None
    assert metrics.not_found.sections == []
    assert [item.count for item in metrics.cards_confirmed] == [0, 0, 0]


def test_nineteen_is_a_small_sample_and_twenty_is_not() -> None:
    assert is_small_sample(19) is True
    assert is_small_sample(20) is False
    rows = [facts(first_text_ms=1000, guard_ms=100)] * 20
    nineteen = compute_metrics(rows[:19], spend_usd=D(0), cap_usd=CAP, confirmed={})
    twenty = compute_metrics(rows, spend_usd=D(0), cap_usd=CAP, confirmed={})

    for tile in (nineteen.first_token, nineteen.safety_check, nineteen.cost):
        assert tile.small_sample is True
    assert nineteen.small_sample is True
    assert nineteen.escalation.small_sample is True
    for tile in (twenty.first_token, twenty.safety_check, twenty.cost):
        assert tile.small_sample is False
    assert twenty.small_sample is False
    assert twenty.escalation.small_sample is False
    assert twenty.refusals.small_sample is False
    assert twenty.not_found.small_sample is False
    assert twenty.injections.small_sample is False


def test_a_tile_counts_its_own_sample_not_the_turns() -> None:
    # 30 turns, but only 19 answered and 19 with a first word: those two tiles stay small.
    rows = [facts(first_text_ms=500) for _ in range(19)] + [facts("failed") for _ in range(11)]
    metrics = compute_metrics(rows, spend_usd=D(0), cap_usd=CAP, confirmed={})

    assert metrics.small_sample is False
    assert metrics.first_token.small_sample is True
    assert metrics.cost.small_sample is True


@pytest.mark.parametrize(
    ("values", "percent", "expected"),
    [
        ([], 50, None),
        ([7], 50, 7),
        ([7], 95, 7),
        ([10, 20], 50, 10),  # rank ceil(1.0) = 1
        ([10, 20], 95, 20),  # rank ceil(1.9) = 2
        ([30, 10, 20], 50, 20),  # sorted 10, 20, 30; rank ceil(1.5) = 2
        (list(range(1, 101)), 95, 95),  # rank ceil(95.0) = 95
        (list(range(1, 101)), 50, 50),
        (list(range(1, 102)), 95, 96),  # n = 101: rank ceil(95.95) = 96, the 96th value is 96
    ],
)
def test_percentile_is_nearest_rank(values: list[int], percent: int, expected: int | None) -> None:
    assert percentile(values, percent) == expected


@pytest.mark.parametrize(
    ("tile", "out"),
    [
        (metrics_module.FirstTokenTile, schemas.FirstTokenTileOut),
        (metrics_module.SafetyCheckTile, schemas.SafetyCheckTileOut),
        (metrics_module.CostTile, schemas.CostTileOut),
        (metrics_module.EscalationTile, schemas.EscalationTileOut),
        (metrics_module.RefusalsTile, schemas.RefusalsTileOut),
        (metrics_module.NotFoundTile, schemas.NotFoundTileOut),
        (metrics_module.InjectionTile, schemas.InjectionTileOut),
        (metrics_module.SectionCount, schemas.SectionCountOut),
        (metrics_module.ActionCount, schemas.ActionCountOut),
    ],
)
def test_each_tile_and_its_response_model_have_the_same_fields(
    tile: type, out: type[BaseModel]
) -> None:
    assert {f.name for f in fields(tile)} == set(out.model_fields)
