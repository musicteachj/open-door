"""What the assistant's routes send and take.

The browser sees a turn's question, answer, citations, status, and trace, and the fixed texts for
an error or an escalation, so a reload shows what the stream showed. It does not see the guard's
injection flag (telling an attacker they were flagged helps them probe), the cost, or the cache
counts (the prompt cache is shared across the account, so a cache hit could hint that another
visitor asked the same thing).
"""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, Field, StringConstraints

from app.ai.conversations import FEEDBACK_REASON_MAX_CHARACTERS
from app.api.schemas import CamelModel


def is_storable(text: str) -> bool:
    """Whether Postgres can hold the text: no NUL, and valid Unicode (a lone surrogate can't be
    encoded). Otherwise the insert fails with a 500."""
    if "\x00" in text:
        return False
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _storable(value: str | None) -> str | None:
    if value is not None and not is_storable(value):
        raise ValueError("The text can't contain a NUL character or a lone surrogate.")
    return value


class CitationOut(CamelModel):
    """A citation as the `citation` event sent it."""

    marker: int
    offset_utf16: int
    section_id: str
    passage_id: str
    title: str
    group_name: str
    audience_label: str
    last_updated: str
    deep_link: str
    cited_text: str


class GuardOut(CamelModel):
    """What the safety check decided. Its injection flag stays on the server."""

    category: Literal["ordinary", "sensitive", "crisis"]
    kind: str | None = None


class ToolCallOut(CamelModel):
    name: str
    input_summary: str
    ok: bool
    duration_ms: int


class SectionOut(CamelModel):
    section_id: str
    passage_ids: list[str]
    # Read from the conversation's stored sources when the page loads. Null for a section they
    # don't hold.
    title: str | None
    group_name: str | None


class FeedbackOut(CamelModel):
    helpful: bool
    reason: str | None = None


class TurnErrorOut(CamelModel):
    """The code the stream's `error` event had, and its fixed text."""

    code: str
    message: str


class HrContactOut(CamelModel):
    name: str
    work_email: str
    job_title: str | None
    location_name: str | None


class EscalationOut(CamelModel):
    """The fixed text the stream's `escalation` event had, and the HR team to reach."""

    kind: Literal["sensitive", "crisis", "unavailable"]
    message: str
    hr_contact: list[HrContactOut]


class TurnOut(CamelModel):
    id: UUID
    question: str
    status: Literal["running", "completed", "stopped", "failed", "crisis", "guard_unavailable"]
    answer_text: str
    citations: list[CitationOut]
    # True when the output limit cut the answer off.
    incomplete: bool
    error: TurnErrorOut | None
    escalation: EscalationOut | None
    # The turn searched the handbook and found nothing to cite: the page offers the HR team, whose
    # contacts are in the conversation's `hrContacts`.
    not_found: bool
    guard: GuardOut | None
    tool_calls: list[ToolCallOut]
    sections: list[SectionOut]
    feedback: FeedbackOut | None
    started_at: datetime
    ended_at: datetime | None


class BudgetBannerOut(CamelModel):
    """The fixed text for the cap that stops the person: the sandbox's, or the day's."""

    kind: Literal["sandbox", "daily"]
    message: str


class BudgetOut(CamelModel):
    """Whether a turn can start. A cap counts as reached when it has less than a turn needs left,
    not only at zero (the 429 uses the same measure)."""

    sandbox_reached: bool
    daily_reached: bool
    sandbox_remaining_cents: int
    # The day's wins when both are reached, because a new sandbox would not help.
    banner: BudgetBannerOut | None


class ConversationOut(CamelModel):
    id: UUID
    created_at: datetime
    turns: list[TurnOut]
    # The HR team, for the "not found" cards. Empty when no turn needs them. A sensitive or crisis
    # turn's escalation carries its own.
    hr_contacts: list[HrContactOut]
    budget: BudgetOut
    # Past 60,000 tokens of history: a new conversation is offered.
    long_history: bool
    # Past 80,000: the next question is refused until a new conversation starts.
    history_too_long: bool
    # Pinned to a prompt or tool set that is no longer current: it can't continue.
    outdated: bool


class AssistantTextsOut(CamelModel):
    """The fixed refusals the composer shows before a request is sent, so the web app holds no
    copy of the words."""

    personal_data: str
    still_answering: str


class FeedbackIn(CamelModel):
    helpful: bool
    reason: Annotated[
        str | None,
        StringConstraints(strip_whitespace=True, max_length=FEEDBACK_REASON_MAX_CHARACTERS),
        AfterValidator(_storable),
    ] = None


class FeedbackGivenOut(CamelModel):
    turn_id: UUID
    helpful: bool
    reason: str | None = None


class TurnIn(CamelModel):
    # Trimmed and measured by the route, which answers 422 with its own wording. This limit only
    # refuses an absurd question early, with the schema's 422, before the route's work (the body
    # has been read by then). Limiting the body's size is the reverse proxy's job (Phase 8).
    question: Annotated[str, Field(max_length=20_000)]
