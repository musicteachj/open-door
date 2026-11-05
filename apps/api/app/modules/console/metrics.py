"""The console's tiles, worked out from plain values (no query and no framework: the queries
load the values, and this module only counts them).

The queries read the console rows' numbers and labels into `TurnFacts`, and `compute_metrics` turns
them into the tiles. Nothing here sees a person, a conversation, or any text: a section ID is the
most it reads.

Every tile carries its sample size and `small_sample` (under `SMALL_SAMPLE_UNDER`, 20).
"""

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from app.ai.console_rows import CARD_ACTIONS
from app.core.stats import percentile as percentile

# Fewer than this many measurements and a tile says "Small sample".
SMALL_SAMPLE_UNDER: Final = 20
# The design's targets, in milliseconds.
FIRST_TOKEN_TARGET_MS: Final = 3000
SAFETY_CHECK_TARGET_MS: Final = 800


def is_small_sample(size: int) -> bool:
    return size < SMALL_SAMPLE_UNDER


@dataclass(frozen=True)
class TurnFacts:
    """The part of one console row the tiles read. A flagged row has no outcome, no injection flag,
    and no sections, but keeps its timings, its cost, and whether another model served it."""

    flagged: bool
    # The turn died before it stored a verdict: flagged (redacted), but not an escalation.
    abandoned: bool
    outcome: str | None
    fallback: bool
    injection_suspected: bool | None
    first_text_ms: int | None
    guard_ms: int | None
    cost_usd: Decimal
    sections_retrieved: Sequence[str] | None


@dataclass(frozen=True)
class FirstTokenTile:
    """Time to first token: p50 and p95 of `first_text_ms` over the rows that have one."""

    p50_ms: int | None
    p95_ms: int | None
    target_ms: int
    sample_size: int
    small_sample: bool


@dataclass(frozen=True)
class SafetyCheckTile:
    """Safety check time: p95 of `guard_ms` over the rows that have one."""

    p95_ms: int | None
    target_ms: int
    sample_size: int
    small_sample: bool


@dataclass(frozen=True)
class CostTile:
    """Cost per answered question: the mean `cost_usd` of rows with outcome `answered` (None with
    none), and the sandbox's whole spend against its cap, from the ledger."""

    per_answered_question_usd: Decimal | None
    answered_count: int
    sandbox_spend_usd: Decimal
    sandbox_cap_usd: Decimal
    small_sample: bool


@dataclass(frozen=True)
class EscalationTile:
    """Escalation rate: flagged rows that are not abandoned, over all rows (None with no rows).
    An abandoned row is a turn (it is in `turns`) but not an escalation: its process died, and no
    verdict was stored."""

    rate: float | None
    flagged_count: int
    turns: int
    small_sample: bool


@dataclass(frozen=True)
class RefusalsTile:
    """Refusals and fallbacks: rows the model service refused or another model served (a row that
    is both counts once in `affected_count`), over all rows."""

    rate: float | None
    refused_count: int
    fallback_count: int
    affected_count: int
    turns: int
    small_sample: bool


@dataclass(frozen=True)
class SectionCount:
    section_id: str
    count: int


@dataclass(frozen=True)
class NotFoundTile:
    """Said the handbook doesn't cover it: rows with outcome `not_found`, over all rows, and the
    sections those rows retrieved, most frequent first (ties by section ID, ascending)."""

    count: int
    turns: int
    sections: Sequence[SectionCount]
    small_sample: bool


@dataclass(frozen=True)
class ActionCount:
    action: str
    count: int


@dataclass(frozen=True)
class InjectionTile:
    """Possible prompt injections: rows the safety check marked, over all rows."""

    count: int
    turns: int
    small_sample: bool


@dataclass(frozen=True)
class ConsoleMetrics:
    turns: int
    small_sample: bool
    first_token: FirstTokenTile
    safety_check: SafetyCheckTile
    cost: CostTile
    escalation: EscalationTile
    refusals: RefusalsTile
    not_found: NotFoundTile
    cards_confirmed: Sequence[ActionCount]
    injections: InjectionTile


def _rate(count: int, turns: int) -> float | None:
    return count / turns if turns else None


def compute_metrics(
    rows: Sequence[TurnFacts],
    *,
    spend_usd: Decimal,
    cap_usd: Decimal,
    confirmed: Mapping[str, int],
) -> ConsoleMetrics:
    """The tiles for a sandbox's console rows (flagged ones included).

    `confirmed` is the count of `proposal.confirmed` audit events by action; the three actions are
    always listed, with zero for one that has none.
    """
    turns = len(rows)
    small = is_small_sample(turns)

    first_text = [row.first_text_ms for row in rows if row.first_text_ms is not None]
    guard = [row.guard_ms for row in rows if row.guard_ms is not None]
    answered = [row.cost_usd for row in rows if row.outcome == "answered"]
    flagged = sum(1 for row in rows if row.flagged and not row.abandoned)
    refused = sum(1 for row in rows if row.outcome == "refused")
    fell_back = sum(1 for row in rows if row.fallback)
    affected = sum(1 for row in rows if row.outcome == "refused" or row.fallback)
    unanswered = [row for row in rows if row.outcome == "not_found"]
    closest = Counter(section for row in unanswered for section in row.sections_retrieved or ())
    injections = sum(1 for row in rows if row.injection_suspected)

    return ConsoleMetrics(
        turns=turns,
        small_sample=small,
        first_token=FirstTokenTile(
            p50_ms=percentile(first_text, 50),
            p95_ms=percentile(first_text, 95),
            target_ms=FIRST_TOKEN_TARGET_MS,
            sample_size=len(first_text),
            small_sample=is_small_sample(len(first_text)),
        ),
        safety_check=SafetyCheckTile(
            p95_ms=percentile(guard, 95),
            target_ms=SAFETY_CHECK_TARGET_MS,
            sample_size=len(guard),
            small_sample=is_small_sample(len(guard)),
        ),
        cost=CostTile(
            per_answered_question_usd=sum(answered, Decimal(0)) / len(answered)
            if answered
            else None,
            answered_count=len(answered),
            sandbox_spend_usd=spend_usd,
            sandbox_cap_usd=cap_usd,
            small_sample=is_small_sample(len(answered)),
        ),
        escalation=EscalationTile(
            rate=_rate(flagged, turns), flagged_count=flagged, turns=turns, small_sample=small
        ),
        refusals=RefusalsTile(
            rate=_rate(affected, turns),
            refused_count=refused,
            fallback_count=fell_back,
            affected_count=affected,
            turns=turns,
            small_sample=small,
        ),
        not_found=NotFoundTile(
            count=len(unanswered),
            turns=turns,
            sections=[
                SectionCount(section_id, count)
                for section_id, count in sorted(
                    closest.items(), key=lambda pair: (-pair[1], pair[0])
                )
            ],
            small_sample=small,
        ),
        cards_confirmed=[ActionCount(action, confirmed.get(action, 0)) for action in CARD_ACTIONS],
        injections=InjectionTile(count=injections, turns=turns, small_sample=small),
    )
