"""What the console routes send, in JSON (camelCase).

Nothing here can hold a person, a conversation, a turn ID, or text: the console row has none of
them (ADR 0016), and these shapes name only its labels, counts, and timings.

`costUsd` and the other money fields are JSON numbers (floats), not strings: the API has no other
money field to follow, a console figure is for display, and the column's six decimal places fit a
float exactly enough for it.
"""

from datetime import date, datetime
from uuid import UUID

from pydantic import Field

from app.api.schemas import CamelModel


class ToolOut(CamelModel):
    """A tool the turn called: its name, whether it worked, and its time. Never its input."""

    name: str
    ok: bool
    duration_ms: int


class ConsoleTurnOut(CamelModel):
    """One console row. A flagged row has only its date, its counts, and the model's labels: every
    other field is null. `id` is the row's own and never a turn's."""

    id: UUID
    occurred_on: date
    occurred_at: datetime | None
    flagged: bool
    # The turn died before it stored a verdict (flagged, but not an escalation).
    abandoned: bool
    asker_role: str | None
    asker_location: str | None
    outcome: str | None
    refusal_category: str | None
    guard_category: str | None
    injection_suspected: bool | None
    tools: list[ToolOut] | None
    sections_retrieved: list[str] | None
    sections_cited: list[str] | None
    card_action: str | None
    served_by: list[str]
    fallback: bool
    effort: str | None
    prompt_version: str | None
    toolset_version: str | None
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    cost_usd: float
    guard_ms: int | None
    first_text_ms: int | None
    total_ms: int | None


class ConsoleTurnsPageOut(CamelModel):
    items: list[ConsoleTurnOut]
    next_cursor: str | None


class FirstTokenTileOut(CamelModel):
    p50_ms: int | None
    p95_ms: int | None
    target_ms: int
    sample_size: int
    small_sample: bool


class SafetyCheckTileOut(CamelModel):
    p95_ms: int | None
    target_ms: int
    sample_size: int
    small_sample: bool


class CostTileOut(CamelModel):
    per_answered_question_usd: float | None
    answered_count: int
    sandbox_spend_usd: float
    sandbox_cap_usd: float
    small_sample: bool


class EscalationTileOut(CamelModel):
    rate: float | None
    flagged_count: int
    turns: int
    small_sample: bool


class RefusalsTileOut(CamelModel):
    rate: float | None
    refused_count: int
    fallback_count: int
    affected_count: int
    turns: int
    small_sample: bool


class SectionCountOut(CamelModel):
    section_id: str
    count: int


class NotFoundTileOut(CamelModel):
    count: int
    turns: int
    sections: list[SectionCountOut]
    small_sample: bool


class ActionCountOut(CamelModel):
    action: str
    count: int


class InjectionTileOut(CamelModel):
    count: int
    turns: int
    small_sample: bool


class ConsoleMetricsOut(CamelModel):
    turns: int = Field(description="Every console row in the sandbox, flagged ones included.")
    small_sample: bool
    first_token: FirstTokenTileOut
    safety_check: SafetyCheckTileOut
    cost: CostTileOut
    escalation: EscalationTileOut
    refusals: RefusalsTileOut
    not_found: NotFoundTileOut
    cards_confirmed: list[ActionCountOut]
    injections: InjectionTileOut
