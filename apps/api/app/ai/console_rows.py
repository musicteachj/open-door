"""The console row: what HR's AI Ops console may know about one finished turn (ADR 0016).

Pure in behavior: this module builds the row as a plain dict and runs no query (it imports the
guard's verdict rule and the proposal cards' actions, which bring database code with them).
`conversations.py` writes it, in the transaction that finishes the turn.

The row is made of labels copied from the turn. It never holds a person ID, a conversation ID, a
name, or any text a person or the model wrote: not the question, the answer, a tool's input, a
refusal's explanation, or a feedback reason. The answer is read once, to decide `not_found`, and
dropped.

A flagged turn (the safety check said sensitive or crisis, an HR panel showed) is redacted here,
before it is written: only its date, its counts, and the model's labels remain. The database
refuses a flagged row that holds more (`ck_ai_console_turns_flagged_row_is_redacted`), so a bug
here fails the insert instead of leaking, and the turn still finishes.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Final, Literal, get_args
from uuid import UUID
from zoneinfo import ZoneInfo

from app.ai.answer_checks import says_not_found
from app.ai.context import Role
from app.ai.guard import verdict_is_flagged
from app.ai.pricing import BUDGET_ERROR_CODES, Usage
from app.ai.proposal_cards import ProposalAction

Outcome = Literal[
    "answered", "not_found", "refused", "stopped", "failed", "budget", "guard_unavailable"
]

# The cards a turn can offer. A value outside it is dropped (the column's check would refuse it).
CARD_ACTIONS: Final = get_args(ProposalAction.__value__)
# A tool's name is the registry's, but it is written by the model until the turn checks it. A name
# that doesn't look like one is stored as this.
UNKNOWN_TOOL: Final = "unknown"
_TOOL_NAME = re.compile(r"[a-z][a-z0-9_]{0,39}")
# The most characters of a refusal category kept: a category is a short word, and anything longer
# is not one.
MAX_REFUSAL_CATEGORY_CHARACTERS: Final = 40
_REFUSAL_CATEGORY = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")
# A handbook section's ID ("4.3", "ca-1.2"): short, with no spaces.
_SECTION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,39}")


@dataclass(frozen=True)
class ToolCallMeta:
    """One tool call as the console keeps it: the name, whether it worked, and how long it took.
    Never the input summary."""

    name: str
    ok: bool
    duration_ms: int


@dataclass(frozen=True)
class ConsoleInputs:
    """What the turn knows at its end. Read by `build_console_row` and kept nowhere else."""

    status: str
    error_code: str | None
    guard_verdict: Mapping[str, Any] | None
    # The turn showed (or would show) an HR panel: the safety check said "sensitive".
    sensitive: bool
    refusal: bool
    refusal_category: str | None
    injection_suspected: bool
    tool_calls: Sequence[ToolCallMeta]
    sections_retrieved: Sequence[str]
    sections_cited: Sequence[str]
    card_action: str | None
    # Read for `says_not_found` only, never stored.
    answer_text: str
    role: Role
    location_label: str
    served_by: Sequence[str]
    # Another model served some of the answer (the API fell back).
    fallback: bool
    effort: str | None
    prompt_version: str | None
    toolset_version: str | None
    # The main model's tokens and the safety check's, added.
    usage: Usage
    cost_usd: Decimal
    guard_ms: int | None
    first_text_ms: int | None
    total_ms: int | None
    occurred_at: datetime
    hq_timezone: ZoneInfo


def refusal_category_of(stop_details: Mapping[str, Any] | None) -> str | None:
    """The refusal's category, and nothing else of its details. The explanation is text the model
    service wrote about the person's message, so it is never kept. A category that isn't a short
    word is dropped."""
    if not isinstance(stop_details, Mapping):
        return None
    return _short_category(stop_details.get("category"))


def _short_category(category: object) -> str | None:
    if (
        isinstance(category, str)
        and len(category) <= MAX_REFUSAL_CATEGORY_CHARACTERS
        and _REFUSAL_CATEGORY.fullmatch(category)
    ):
        return category
    return None


def location_label(city: str, state: str) -> str:
    """ "Oakland, CA": the place's city and state code, copied when the row is written."""
    return f"{city}, {state}"


def is_flagged(inputs: ConsoleInputs) -> bool:
    """Whether the row is redacted. Fails toward redaction: a verdict that gets an escalation, a
    crisis ending, or an HR panel shown each flag the row."""
    return verdict_is_flagged(inputs.guard_verdict) or inputs.status == "crisis" or inputs.sensitive


def outcome_of(inputs: ConsoleInputs) -> Outcome:
    """How an unflagged turn ended, in the console's seven words."""
    if inputs.error_code in BUDGET_ERROR_CODES:
        return "budget"
    if inputs.refusal:
        return "refused"
    if inputs.status == "stopped":
        return "stopped"
    # A guard that errored (its reservation failed) shows the person the same "safety check
    # unavailable" panel as one that could not run.
    if inputs.status == "guard_unavailable" or inputs.error_code == "guard-error":
        return "guard_unavailable"
    if inputs.status == "failed":
        return "failed"
    return "not_found" if says_not_found(inputs.answer_text) else "answered"


def _on_hq_calendar(moment: datetime, zone: ZoneInfo) -> date:
    return moment.astimezone(zone).date()


def _section_ids(ids: Sequence[str]) -> list[str]:
    """Each handbook section ID once, in the order first seen, and only if it looks like one."""
    kept: list[str] = []
    for section_id in ids:
        if _SECTION_ID.fullmatch(section_id) and section_id not in kept:
            kept.append(section_id)
    return kept


def _tools(calls: Sequence[ToolCallMeta]) -> list[dict[str, Any]]:
    """`[{name, ok, durationMs}]` in call order. The turn's `skipped` note is not a tool."""
    return [
        {
            # The turn already checks the name against the registry; this pattern is a second,
            # deliberate guard, so the builder stays safe when called from anywhere.
            "name": call.name if _TOOL_NAME.fullmatch(call.name) else UNKNOWN_TOOL,
            "ok": bool(call.ok),
            "durationMs": max(0, int(call.duration_ms)),
        }
        for call in calls
        if call.name != "skipped"
    ]


def _non_negative(value: int | None) -> int | None:
    return None if value is None else max(0, int(value))


def _counts(inputs: ConsoleInputs) -> dict[str, Any]:
    """The columns a flagged row keeps besides its date: the counts, timings, and the model's
    labels."""
    usage = inputs.usage
    return {
        "served_by": list(inputs.served_by),
        "fallback": bool(inputs.fallback),
        "effort": inputs.effort,
        "prompt_version": inputs.prompt_version,
        "toolset_version": inputs.toolset_version,
        "input_tokens": max(0, usage.input_tokens),
        "output_tokens": max(0, usage.output_tokens),
        "cache_read_tokens": max(0, usage.cache_read_tokens),
        "cache_write_tokens": max(0, usage.cache_write_tokens),
        "cost_usd": max(Decimal(0), inputs.cost_usd),
        "guard_ms": _non_negative(inputs.guard_ms),
        "first_text_ms": _non_negative(inputs.first_text_ms),
        "total_ms": _non_negative(inputs.total_ms),
    }


def build_console_row(inputs: ConsoleInputs, *, turn_id: UUID) -> dict[str, Any]:
    """The row's columns, except its own ID and its sandbox (the writer adds both).

    A flagged turn gets its date and counts, and nothing else: `turn_id` is not even in the dict.
    """
    occurred_on = _on_hq_calendar(inputs.occurred_at, inputs.hq_timezone)
    if is_flagged(inputs):
        return {"flagged": True, "occurred_on": occurred_on, **_counts(inputs)}
    verdict = inputs.guard_verdict or {}
    category = verdict.get("category")
    outcome = outcome_of(inputs)
    return {
        "flagged": False,
        "occurred_on": occurred_on,
        "turn_id": turn_id,
        "occurred_at": inputs.occurred_at,
        "asker_role": inputs.role,
        "asker_location": inputs.location_label,
        "outcome": outcome,
        "refusal_category": _short_category(inputs.refusal_category)
        if outcome == "refused"
        else None,
        "guard_category": category if isinstance(category, str) else None,
        "injection_suspected": bool(inputs.injection_suspected),
        "tools": _tools(inputs.tool_calls),
        "sections_retrieved": _section_ids(inputs.sections_retrieved),
        "sections_cited": _section_ids(inputs.sections_cited),
        "card_action": inputs.card_action if inputs.card_action in CARD_ACTIONS else None,
        **_counts(inputs),
    }


def build_abandoned_row(*, occurred_at: datetime, hq_timezone: ZoneInfo) -> dict[str, Any]:
    """The row for a turn the app marked abandoned: its process died before the turn stored a
    verdict, so nothing proves it was an ordinary one. Redacted, with no model labels and no
    measurements, since none were taken. `occurred_at` is when the turn was asked.

    `abandoned` says a turn died, nothing about a person, so the console can count it as a turn and
    not as an escalation."""
    return {
        "flagged": True,
        "abandoned": True,
        "occurred_on": _on_hq_calendar(occurred_at, hq_timezone),
        "served_by": [],
    }
