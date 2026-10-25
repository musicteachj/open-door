"""The turn: one question and everything that answers it (spec, "The turn").

`run_turn` is an async generator of typed events. The stream route (Stage 4) only relays them as
server-sent events, so everything that decides what a person sees lives here and is testable
without HTTP.

The shape of a turn:

1. A short transaction recovers an abandoned turn, starts this one, and reads the history.
2. The guard reads the question. Crisis and an unavailable guard end the turn with fixed text, and
   the main model is never called.
3. The main loop calls the model at most eight times. Each call is reserved before it starts and
   settled once after it ends. Tools run concurrently, and their results go back in one message.
4. The end-of-turn writes run in a `finally`, shielded from cancellation, in a transaction of
   their own: a turn that is stopped, or whose client has gone, still settles what is known and
   records its trace.

What the history keeps (the API's placement rule: a stored `system` message must be followed by an
assistant message). The per-turn context is stored only together with the turn's first complete
assistant message. A turn with no complete assistant message stores its question alone, so two user
messages may follow each other, and a crisis or unavailable-guard turn stores nothing. Nothing
stored is ever changed (Opus 5.5 ties its thinking to the exact conversation).

No database transaction is held across a model call or a tool call. Nothing here logs a question,
an answer, a tool result, or the canary: only IDs, exception types, and timings.
"""

import asyncio
import json
import logging
import re
import time
import unicodedata
from collections.abc import (
    AsyncGenerator,
    AsyncIterator,
    Awaitable,
    Callable,
    Iterator,
    Sequence,
)
from contextlib import aclosing
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from functools import partial
from typing import Any, ClassVar, Literal
from uuid import UUID

import anyio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.ai.budget import BudgetExceeded, Caps, Reservation, reserve, settle
from app.ai.citations import CitationEvent, CitationMapper
from app.ai.context import ActorView, turn_context
from app.ai.conversations import (
    SourceEntry,
    StoredMessage,
    TurnOutcome,
    append_messages,
    conversation_is_outdated,
    finish_turn,
    model_history,
    search_sources,
    start_turn,
)
from app.ai.embeddings import Embedder
from app.ai.fixed_texts import (
    CRISIS_TEXT,
    ERROR_TEXTS,
    SENSITIVE_TEXT,
    UNAVAILABLE_TEXT,
    HrContact,
    hr_contact,
)
from app.ai.guard import GuardOutcome, build_guard_request, guard_reservation_usd, screen
from app.ai.pricing import (
    IterationUsage,
    Usage,
    estimate_input_tokens,
    is_priced,
    reservation_usd,
    total_usage,
    turn_call_cost,
)
from app.ai.prompts.versions import CANARY, system_prompt
from app.ai.proposals import (
    ProposalOut,
    cancel_turn_proposals_in,
    cancel_unreported_proposals_in,
    conversation_proposals,
    outcomes_since,
    recover_abandoned_turns,
)
from app.ai.text import error_name, one_line
from app.ai.tools.base import ToolContext, ToolOutcome, failure, text_block
from app.ai.tools.registry import TOOL_DEFINITIONS, describe_call, proposes, run_tool
from app.ai.transport import (
    FALLBACK_BETA,
    Finished,
    InvalidToolInput,
    ModelEvent,
    ModelRequest,
    ModelUnavailable,
    SpendLimitReached,
    StatusNote,
    TextBlockEnd,
    ToolCall,
    Transport,
)
from app.ai.transport import TextDelta as ModelText
from app.db.models import AiConversation, AiMessage, AiProposal, AiTurn
from app.db.tenancy import TenantContext, tenant_session
from app.domain.handbook.applicability import Asker
from app.modules.audit.service import record_event
from app.policy import Actor

logger = logging.getLogger(__name__)

# Before any change a card can have: the reference point when no context was ever stored.
NEVER = datetime(1970, 1, 1, tzinfo=UTC)

MAX_MODEL_CALLS = 8
MAX_TOKENS = 8000
MAX_QUESTION_CHARACTERS = 2000
THINKING_UPDATES_BETA = "thinking-display-updates-2026-08-18"
BETAS = (FALLBACK_BETA, THINKING_UPDATES_BETA)

# The whole turn, from the end of the start-up transaction. It must stay below the abandoned-turn
# rule (conversations.ABANDONED_AFTER, 10 minutes), or recovery could fail a live turn. The spec has
# no timeout error code, so it is reported as `model-unavailable`.
TURN_DEADLINE = timedelta(minutes=8)
# The end-of-turn writes are shielded from cancellation, so they need a bound of their own: a
# database that hangs must not hold a canceled task (and its connection) forever. When it fires the
# turn is left `running` for `recover_abandoned`.
CLEANUP_TIMEOUT = timedelta(seconds=10)
# One tool call. Past it the model gets an error result and goes on without the tool.
TOOL_TIMEOUT = timedelta(seconds=30)
# One response can hold hundreds of tool calls. Only a few run, a few at a time, and a turn runs a
# bounded number in all, so one person's turn can't fill the connection pool or flood the
# embedding service. The rest still get an error result (the API needs one for every call).
MAX_TOOLS_PER_RESPONSE = 5
MAX_CONCURRENT_TOOLS = 3
MAX_TOOL_RUNS_PER_TURN = 20
# What the model is told for a second card in one response (spec, "Proposals").
ONE_CARD_TEXT = "Only one card can be made per answer; this call was not run."
# The crisis text never waits on the HR lookup longer than this.
HR_CONTACT_TIMEOUT = timedelta(seconds=2)
# Closing the model's stream, and settling a call, are shielded from cancellation (the first so the
# upstream request stops and no more billed tokens are generated); this bounds the wait.
SHIELDED_STEP_TIMEOUT = timedelta(seconds=5)

# The most characters of a taken-back working note shown as a status line.
WORKING_NOTE_MAX_CHARACTERS = 120

ErrorCode = Literal[
    "refusal",
    "model-unavailable",
    "budget-sandbox",
    "budget-daily",
    "spend-limit",
    "too-many-calls",
    "internal",
]
EndStatus = Literal["completed", "stopped", "failed", "crisis", "guard_unavailable"]


class ConversationNotFound(Exception):  # noqa: N818
    """The conversation is not the actor's. The route answers 404. A dedicated type, so a lookup
    error from a bug elsewhere (a `KeyError` is a `LookupError`) is never taken for it."""


class ConversationOutdated(Exception):  # noqa: N818
    """The conversation was pinned to a prompt or tool set that is no longer current. The route
    answers 409 `conversation-outdated` and offers a new conversation."""


# --- Events -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class TurnStarted:
    name: ClassVar[str] = "turn.started"
    turn_id: UUID

    def to_json(self) -> dict[str, Any]:
        return {"turnId": str(self.turn_id)}


@dataclass(frozen=True)
class Status:
    name: ClassVar[str] = "status"
    text: str

    def to_json(self) -> dict[str, Any]:
        return {"text": self.text}


@dataclass(frozen=True)
class TextDelta:
    name: ClassVar[str] = "text.delta"
    text: str

    def to_json(self) -> dict[str, Any]:
        return {"text": self.text}


@dataclass(frozen=True)
class TextRetracted:
    """Tells the client to drop all answer text and citations shown so far in this turn.

    Sent when a model call that showed text ends in a tool call: that text was a working note, not
    the answer. Every earlier tool round was already taken back, so what is shown at that moment is
    only that call's text. The note itself follows as a `status` event."""

    name: ClassVar[str] = "text.retracted"

    def to_json(self) -> dict[str, Any]:
        return {}


@dataclass(frozen=True)
class Citation:
    name: ClassVar[str] = "citation"
    citation: CitationEvent

    def to_json(self) -> dict[str, Any]:
        return self.citation.to_json()


@dataclass(frozen=True)
class ToolStarted:
    name: ClassVar[str] = "tool.started"
    id: str
    tool: str
    summary: str

    def to_json(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.tool, "summary": self.summary}


@dataclass(frozen=True)
class ToolFinished:
    name: ClassVar[str] = "tool.finished"
    id: str
    ok: bool
    summary: str
    duration_ms: int

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "ok": self.ok,
            "summary": self.summary,
            "durationMs": self.duration_ms,
        }


@dataclass(frozen=True)
class Proposal:
    """The card a proposal tool just stored, sent right after that tool's `tool.finished`. The
    payload is the same shape as the conversation read's proposals, with `turnRunning` true."""

    name: ClassVar[str] = "proposal"
    proposal: ProposalOut

    def to_json(self) -> dict[str, Any]:
        return self.proposal.model_dump(mode="json", by_alias=True)


@dataclass(frozen=True)
class Escalation:
    name: ClassVar[str] = "escalation"
    kind: Literal["sensitive", "crisis", "unavailable"]
    message: str
    hr_contact: tuple[HrContact, ...]
    offer_case: bool = False

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "message": self.message,
            "hrContact": [contact.to_json() for contact in self.hr_contact],
            "offerCase": self.offer_case,
        }


@dataclass(frozen=True)
class Error:
    name: ClassVar[str] = "error"
    code: ErrorCode
    message: str
    request_id: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "requestId": self.request_id}


@dataclass(frozen=True)
class TurnUsage:
    """The turn's main-model tokens over every attempt of every call (the guard's are not
    included). Cost stays in the trace (`ai_turns`) and never rides on an event."""

    input_tokens: int
    output_tokens: int

    def to_json(self) -> dict[str, Any]:
        return {
            "inputTokens": self.input_tokens,
            "outputTokens": self.output_tokens,
            # No cost, and no cache counts: cost minus the token counts gives the cached share,
            # and that would hint whether another visitor asked the same thing. The trace in
            # `ai_turns` keeps them.
        }


@dataclass(frozen=True)
class TurnCompleted:
    name: ClassVar[str] = "turn.completed"
    turn_id: UUID
    served_by: str
    usage: TurnUsage
    # True when `max_tokens` cut the answer off. Added to the spec's payload only when true.
    incomplete: bool = False

    def to_json(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "turnId": str(self.turn_id),
            "servedBy": self.served_by,
            "usage": self.usage.to_json(),
        }
        if self.incomplete:
            data["incomplete"] = True
        return data


TurnEvent = (
    TurnStarted
    | Status
    | TextDelta
    | TextRetracted
    | Citation
    | ToolStarted
    | ToolFinished
    | Proposal
    | Escalation
    | Error
    | TurnCompleted
)
# What a person can see, for the time to the first visible event. A retraction is not one: the text
# it takes back was already shown.
_VISIBLE = (Status, TextDelta, ToolStarted, Escalation)


# --- Dependencies -----------------------------------------------------------------------------


@dataclass(frozen=True)
class TurnDeps:
    """Everything a turn needs from the server session. Nothing comes from request input.

    The route builds these once per request: `actor` and `tenant_ctx` from the session,
    `actor_view` from `get_me` (`context.actor_view`), `asker` from `load_asker`, `version_id` from
    `pinned_version_id`, and `handbook_label` from that version's row. Heartbeats are the route's.
    """

    engine: AsyncEngine
    transport: Transport
    embedder: Embedder | None
    actor: Actor
    tenant_ctx: TenantContext
    caps: Caps
    actor_view: ActorView
    asker: Asker
    version_id: UUID
    handbook_label: str


# --- Small helpers ----------------------------------------------------------------------------


class _DeadlineExceeded(Exception):  # noqa: N818
    """The whole-turn deadline fired."""


async def _next_event(stream: AsyncIterator[ModelEvent]) -> ModelEvent | None:
    try:
        return await anext(stream)
    except StopAsyncIteration:
        return None


def _text_blocks(message: dict[str, Any]) -> list[str]:
    return [b["text"] for b in message.get("content", []) if b.get("type") == "text"]


def _has_text(message: dict[str, Any]) -> bool:
    return any(text.strip() for text in _text_blocks(message))


def _ends_cleanly(message: dict[str, Any]) -> bool:
    """Whether a message cut off by `max_tokens` is safe to store: it ends in text, every thinking
    block in it is signed, and it calls no tool."""
    content = message.get("content") or []
    if not content or _has_tool_use(message):
        return False
    last = content[-1]
    if last.get("type") != "text" or not str(last.get("text", "")).strip():
        return False
    return all(b.get("signature") for b in content if b.get("type") == "thinking")


def _has_tool_use(message: dict[str, Any]) -> bool:
    return any(b.get("type") == "tool_use" for b in message.get("content", []))


def _serialize(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _fold(text: str) -> str:
    """The text as the canary check compares it: NFKC, case-folded, and only its letters and
    digits. So other case, full-width letters, other hyphens or spaces, markdown inside the phrase,
    and invisible characters all fold to the same string as the plain canary."""
    return "".join(
        char for char in unicodedata.normalize("NFKC", text).casefold() if char.isalnum()
    )


FOLDED_CANARY = _fold(CANARY)


# The most characters of model text held back, or kept as the tail of what was sent, for the canary
# check. The folded count alone does not bound it: characters that fold to nothing (spaces,
# punctuation, Markdown, emoji) do not count, so a long run of them would be held and re-folded on
# every delta. This is generous: a canary with up to 20 separator characters after each of its
# letters (19 held letters x 21 = 399) is still caught. One spread wider is not recognizable to a
# person either, and its start is released.
MAX_HELD_CHARACTERS = 512


def _has_canary(text: str) -> bool:
    """Whether `text` holds the canary in any writing `_fold` sees through. A boolean, so nothing
    that checks it ever prints the canary."""
    return FOLDED_CANARY in _fold(text)


def _keep_from(text: str, count: int) -> int:
    """The index from which `text` ends in at least `count` folded characters (0 if it holds
    fewer), so what is held back counts the characters the check compares, not the ones a person
    sees: a canary that ends in text still to come starts within the last `len(canary) - 1` of
    them, however many separators sit between."""
    seen = 0
    for index in range(len(text) - 1, -1, -1):
        seen += len(_fold(text[index]))
        if seen >= count:
            return index
    return 0


def _tail_start(text: str) -> int:
    """Where the held tail of `text` starts: far enough back to cover `len(FOLDED_CANARY) - 1`
    folded characters, but never more than `MAX_HELD_CHARACTERS` back."""
    return max(_keep_from(text, len(FOLDED_CANARY) - 1), len(text) - MAX_HELD_CHARACTERS, 0)


def _strings(value: Any, *, keys: bool = False) -> Iterator[str]:
    """Every string in a JSON-like value (a tuple counts as a list), and with `keys` the keys of
    its mappings too. The one walk behind the canary check and the surrogate check."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            if keys:
                yield from _strings(key)
            yield from _strings(item, keys=keys)
    elif isinstance(value, list | tuple):
        for item in value:
            yield from _strings(item, keys=keys)


def _holds_the_canary(event: TurnEvent) -> bool:
    """Whether any string an event would send holds the prompt's canary. A boolean, so nothing
    that checks it ever prints the canary."""
    return any(_has_canary(text) for text in _strings(event.to_json()))


def _previous_answer(previous: Sequence[Any] | None) -> str | None:
    """What the guard is shown of the turn just before this one. Usually its answer; where it had
    none because the person was sent a fixed text (crisis, the guard down, a budget stop), that
    text, so a short reply such as "yes, tonight" is screened with its context."""
    if previous is None:
        return None
    answer_text, status, error_code = previous
    if answer_text:
        return str(answer_text)
    if status == "crisis":
        return CRISIS_TEXT
    if status == "guard_unavailable" or error_code == "guard-error":
        return UNAVAILABLE_TEXT
    if status == "failed" and error_code == "refusal":
        return ERROR_TEXTS["refusal"]
    if status == "failed" and error_code in ("budget-sandbox", "budget-daily", "spend-limit"):
        return ERROR_TEXTS[error_code]
    return None


def _shortened_on_a_word(text: str, limit: int) -> str:
    """`text` if it fits in `limit` characters, else cut on a word boundary with an ellipsis, the
    ellipsis included in the limit."""
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    if not text[limit - 1].isspace():
        space = cut.rfind(" ")
        if space > 0:
            cut = cut[:space]
    return cut.rstrip() + "…"


def _budget_code(scope: str) -> ErrorCode:
    return "budget-sandbox" if scope == "sandbox" else "budget-daily"


def _clock() -> float:
    """Seconds on the monotonic clock. The one place the turn reads time, so a test can move it."""
    return time.monotonic()


_LONE_SURROGATE = re.compile("[\ud800-\udfff]")


def without_lone_surrogates(text: str) -> str:
    """The text with each lone surrogate replaced by U+FFFD. Python strings can hold one (a model
    that cuts an emoji between two deltas), but UTF-16 and the database cannot encode it. Done
    once where model text enters the turn, so the shown text, offsets, and stored answer agree."""
    return _LONE_SURROGATE.sub("\ufffd", text)


def _has_lone_surrogate(value: Any) -> bool:
    """Whether any string in a JSON-like value, mapping keys included, holds a lone surrogate."""
    return any(_LONE_SURROGATE.search(text) for text in _strings(value, keys=True))


def _scrub(value: Any) -> Any:
    """`without_lone_surrogates` over every string in a JSON-like value."""
    if isinstance(value, str):
        return without_lone_surrogates(value)
    if isinstance(value, list | tuple):
        return [_scrub(item) for item in value]
    if isinstance(value, dict):
        return {_scrub(key): _scrub(item) for key, item in value.items()}
    return value


_SIGNED_BLOCKS = ("thinking", "redacted_thinking")


def _scrubbed_message(message: dict[str, Any]) -> dict[str, Any]:
    """The finished message, scrubbed, except its thinking blocks: they go back to the model with
    their signatures, so they must stay exactly as they came."""
    content = message.get("content")
    if not isinstance(content, list):
        return {key: _scrub(value) for key, value in message.items()}
    return {
        **{key: _scrub(value) for key, value in message.items() if key != "content"},
        "content": [
            block
            if isinstance(block, dict) and block.get("type") in _SIGNED_BLOCKS
            else _scrub(block)
            for block in content
        ],
    }


def scrubbed(event: Any) -> Any:
    """The transport's event with lone surrogates replaced in its text, in the one place events
    enter the loop: the shown text, the notes, and the finished message (which is stored and sent
    back to the model, and holds the tool_use blocks the loop runs) all agree."""
    if isinstance(event, StatusNote | ModelText):
        if _LONE_SURROGATE.search(event.text) is None:
            return event
        return replace(event, text=without_lone_surrogates(event.text))
    if isinstance(event, Finished):
        if not _has_lone_surrogate(event.message):
            return event
        return replace(event, message=_scrubbed_message(event.message))
    return event


def utf16_length(text: str) -> int:
    """The length in UTF-16 code units, which is what a browser's string indexes count. An emoji
    is two units but one Python character, so a citation offset in characters would land early."""
    return len(text.encode("utf-16-le")) // 2


# --- The turn ---------------------------------------------------------------------------------


def model_request(*, model: str, effort: str, messages: Sequence[dict[str, Any]]) -> ModelRequest:
    """The request every main-model call of a conversation has the same shape for: the frozen
    system prompt and tools, and the messages so far. The stream route builds the first call's
    request with this to size its budget check, so it can't drift from the loop's."""
    return ModelRequest(
        model=model,
        system=(
            {
                "type": "text",
                "text": system_prompt(),
                "cache_control": {"type": "ephemeral"},
            },
        ),
        tools=tuple(TOOL_DEFINITIONS),
        messages=tuple(messages),
        effort=effort,
        max_tokens=MAX_TOKENS,
        betas=BETAS,
        fallbacks="default",
    )


def first_call_input_tokens(request: ModelRequest) -> int:
    """The estimate of a turn's first model call's input: the whole request serialized, because
    nothing measured covers the system prompt and the tools yet (`estimate_input_tokens`)."""
    return estimate_input_tokens(
        None,
        _serialize(
            {
                "system": list(request.system),
                "tools": list(request.tools),
                "messages": list(request.messages),
            }
        ),
    )


class TurnRun:
    """One started turn. `events()` streams it; the rest is its state and steps."""

    def __init__(
        self,
        deps: TurnDeps,
        conversation: AiConversation,
        question: str,
        now: datetime,
        *,
        turn_id: UUID,
        history: list[dict[str, Any]],
        sources: list[SourceEntry],
        previous_answer: str | None,
        outcomes: tuple[str, ...] = (),
    ) -> None:
        self.deps = deps
        self.conversation = conversation
        self.question = question
        self.now = now
        self.turn_id = turn_id
        self.history = history
        self.mapper = CitationMapper(sources)
        self.previous_answer = previous_answer
        self.outcomes = outcomes
        self.started_loop_s = _clock()
        self.deadline_loop_s = self.started_loop_s + TURN_DEADLINE.total_seconds()

        self.status: EndStatus | None = None
        self.error: Error | None = None
        self.error_code: str | None = None
        self.incomplete = False
        self.guard_passed = False
        self.guard_verdict: dict[str, object] | None = None
        self.injection = False
        self.refusal = False
        self.fallback = False
        # Stored apart from the context, so storing the question never depends on building it.
        self.question_message = StoredMessage("user", [text_block(question)])
        self.context_message: StoredMessage | None = None
        # This turn's rounds and its final answer, held in memory. They go into history together,
        # in one append, only when the turn ends with a storable answer.
        self.rounds: list[StoredMessage] = []
        self.final: StoredMessage | None = None
        self.shown: list[str] = []
        # The shown text's length in UTF-16 units, kept running so a block end is not a re-scan.
        self.shown_units = 0
        # Model text not yet sent: the last `len(FOLDED_CANARY) - 1` folded characters are held
        # back, so a canary split across deltas is still caught before any part that completes
        # it goes out.
        self.held = ""
        # The last characters of everything sent, answer text and progress notes alike, so a canary
        # split across the two channels is still caught. A half already sent stays sent (a known
        # limit); the half that completes the canary is withheld.
        self.sent_tail = ""
        self.sensitive = False
        # The guard never ran, and not for a budget stop: the message was not screened.
        self.unscreened = False
        # The guard never ran because of a budget stop. The budget error itself carries 911 and 988,
        # so no escalation event follows it, but the stop is still audited.
        self.budget_stopped = False
        # The turn ended with the answer shown but no storable final message: its rounds are
        # stored, its empty last message is not.
        self.answer_without_final = False
        self.citations: list[dict[str, Any]] = []
        # The same citations as events, so a taken-back text can be sent again with them.
        self.citation_events: list[CitationEvent] = []
        # The last text taken back as a note, with its citations. If the model then ends with
        # nothing more to say, that text was the answer after all (see `_restore_the_answer`).
        self.taken_back_answer: tuple[str, tuple[CitationEvent, ...]] | None = None
        self.tool_trace: list[dict[str, Any]] = []
        self.tool_runs = 0  # Tools actually run this turn, against MAX_TOOL_RUNS_PER_TURN.
        self.sections: list[dict[str, Any]] = []
        self.served_by_models: list[str] = []
        self.last_served_by = ""
        self.iterations: list[IterationUsage] = []
        self.cost_usd = Decimal(0)
        self.inflight: Reservation | None = None
        self.first_event_ms: int | None = None
        self.finish_failed = False
        # The cards that successful tool outcomes reported this turn. A card stored while its tool
        # timed out or was canceled is not here, and the ending cancels it.
        self.reported_proposals: set[UUID] = set()
        # Whether the whole turn (question, context, every round, answer) reached the history.
        self.history_stored = False

    # -- start --

    @classmethod
    async def begin(
        cls, deps: TurnDeps, conversation: AiConversation, question: str, now: datetime
    ) -> "TurnRun":
        """Recover an abandoned turn, add this one, and read what the turn starts from. Raises
        `TurnRunning` when a turn is still in progress."""
        async with tenant_session(deps.engine, deps.tenant_ctx) as db:
            # The abandoned turns' cards are canceled in this same transaction, after their turns.
            await recover_abandoned_turns(db, deps.tenant_ctx, conversation.id)
            turn = await start_turn(db, conversation, question)
            history = await model_history(db, conversation.id)
            sources = await search_sources(db, conversation.id)
            previous = (
                await db.execute(
                    select(
                        AiTurn.answer_text,
                        AiTurn.status,
                        AiTurn.error_code,
                        AiTurn.started_at,
                        AiTurn.ended_at,
                    )
                    .where(AiTurn.conversation_id == conversation.id, AiTurn.id != turn.id)
                    .order_by(AiTurn.started_at.desc(), AiTurn.id.desc())
                    .limit(1)
                )
            ).first()
            # What changed for the person's cards since the last context the model was shown: the
            # start of the latest earlier turn whose context was stored in the history (its
            # outcomes were computed at that same `now()`, the transaction's start). A turn that
            # failed, crashed, or ended in a crisis stored none, so what it would have said is
            # still news. With no such turn, every change is.
            # Wait for a confirm or dismiss still committing (it holds the card's row), so the read
            # below sees the card's final state: its `ended_at` is its transaction's start, which
            # can be earlier than this turn's, and a row nobody could see would never be reported.
            # Lock order here: the turn rows (recovery, the new turn), then these card rows. A
            # confirm takes only a card row and the balance lock, never a turn, and a proposal
            # being made takes the conversation's advisory lock, then its turn row, then the card
            # rows. Nothing holding a card row waits on a turn row, so none of them can cycle.
            await db.execute(
                select(AiProposal.id)
                .where(
                    AiProposal.conversation_id == conversation.id, AiProposal.status == "pending"
                )
                .with_for_update(read=True)
            )
            reference = (
                await db.execute(
                    select(func.max(AiTurn.started_at))
                    .join(AiMessage, AiMessage.turn_id == AiTurn.id)
                    .where(
                        AiTurn.conversation_id == conversation.id,
                        AiTurn.id != turn.id,
                        AiMessage.role == "system",
                    )
                )
            ).scalar_one()
            outcomes = outcomes_since(
                await conversation_proposals(db, conversation.id),
                reference or NEVER,
                (await db.execute(select(func.now()))).scalar_one(),
            )
        return cls(
            deps,
            conversation,
            question,
            now,
            turn_id=turn.id,
            history=history,
            sources=sources,
            previous_answer=_previous_answer(None if previous is None else previous[:3]),
            outcomes=outcomes,
        )

    # -- bookkeeping --

    def _seen(self, event: TurnEvent) -> TurnEvent:
        if self.first_event_ms is None and isinstance(event, _VISIBLE):
            self.first_event_ms = int((_clock() - self.started_loop_s) * 1000)
        return event

    def fail(self, code: ErrorCode, *, request_id: str | None = None) -> None:
        self.status = "failed"
        self.error_code = code
        self.error = Error(code, ERROR_TEXTS[code], request_id)

    def _hold(self, text: str) -> tuple[str, bool]:
        """Take model text in. Returns what is safe to send now and whether the canary showed up
        (in the text already sent, the text held, and this text together). Nothing is sent after
        a leak."""
        if _has_canary(self.sent_tail + self.held + text):
            return "", True
        buffer = self.held + text
        cut = _tail_start(buffer)
        send = buffer[:cut]
        self.held = buffer[cut:]
        return send, False

    def _flush_held(self) -> TurnEvent | None:
        """Send the held text, at a block end or the end of a call, before any citation, so the
        offsets count it."""
        text, self.held = self.held, ""
        return self._shown_text(text) if text else None

    def _forget_what_was_shown(self) -> None:
        """Reset the answer's text, its offsets, its citations, and the marker numbering: what the
        client was told to drop with a `text.retracted` event. (`search_result_index` counts across
        the whole conversation, so the mapper keeps its results.)"""
        self.shown.clear()
        self.shown_units = 0
        self.citations.clear()
        self.citation_events.clear()
        self.mapper.restart_markers()

    def _take_back_the_note(self) -> list[TurnEvent] | None:
        """A call that showed text has ended in a tool call, so that text was a working note.

        Returns the events that take it back (a retraction, then the note as one status line), and
        resets what the turn counts as shown, so the stored answer, the offsets, and the markers
        of what follows start fresh. The mapper keeps its results: `search_result_index` counts
        across the whole conversation. `sent_tail` keeps the taken-back text, which is
        conservative.

        Returns None when the status line holds the canary (the caller ends the turn as a leak)."""
        written = "".join(self.shown)
        note = _shortened_on_a_word(one_line(written), WORKING_NOTE_MAX_CHARACTERS)
        if _has_canary(self.sent_tail + self.held + note):
            return None
        tail = self.sent_tail + note
        self.sent_tail = tail[_tail_start(tail) :]
        if written.strip():
            self.taken_back_answer = (written, tuple(self.citation_events))
        # Blank text is taken back (so the offsets restart) but is never an answer, and it does
        # not wipe an earlier one.
        self._forget_what_was_shown()
        events: list[TurnEvent] = [self._seen(TextRetracted())]
        if note:
            events.append(self._seen(Status(note)))
        return events

    def _restore_the_answer(self) -> list[TurnEvent] | None:
        """The last taken-back text, sent again as the answer, for a final call that said nothing.

        Returns its events (the text, then its citations; the offsets and markers are the ones it
        had, which already count from zero), and puts it back in `shown` and `citations`. Returns
        an empty list when there is nothing to bring back, and None when the text holds the canary
        (it passed once; it is checked again because it is sent again)."""
        if self.taken_back_answer is None:
            return []
        text, citations = self.taken_back_answer
        self.taken_back_answer = None
        # Checked with what was just sent, like every send: the note (a prefix of this text) ended
        # a moment ago, and a canary can straddle its end and this text's start.
        if _has_canary(self.sent_tail + text):
            return None
        events: list[TurnEvent] = []
        if self.shown:
            # Only blank text was shown since the note was taken back. Take it back too, so the
            # answer and its citation offsets start from zero.
            events.append(self._seen(TextRetracted()))
            self._forget_what_was_shown()
        events.append(self._shown_text(text))
        for cited in citations:
            self.citations.append(cited.to_json())
            self.citation_events.append(cited)
            events.append(self._seen(Citation(cited)))
        return events

    def _prompt_leak(self) -> None:
        """The model repeated the prompt's canary. Nothing of it was sent; the person gets the
        plain internal error and the turn stores only the question. IDs only in the log."""
        logger.warning("prompt leak withheld (turn %s)", self.turn_id)
        self.held = ""
        self.fail("internal")
        self.error_code = "prompt-leak"

    def _shown_text(self, text: str) -> TurnEvent:
        """Add text the person is about to see to the answer, and return its event."""
        self.shown.append(text)
        self.shown_units += utf16_length(text)
        if text.strip():
            # This call has its own text now, so an earlier call's is not the one to bring back.
            # Cleared when the text is sent, not when it arrives: text still held back, or from a
            # call that is re-issued, was never shown. (Blank text is not an answer.)
            self.taken_back_answer = None
        if text:
            tail = self.sent_tail + text
            self.sent_tail = tail[_tail_start(tail) :]
        return self._seen(TextDelta(text))

    def _keep(self, reservation: Reservation) -> None:
        """Count a reservation at its amount: the call's cost is unknown, or its settle failed, so
        the reserve row stays in the ledger as it is."""
        self.cost_usd += reservation.amount_usd
        if self.inflight is reservation:
            self.inflight = None

    async def _within[T](self, step: Callable[..., Awaitable[T]], *args: Any) -> T:
        remaining = self.deadline_loop_s - _clock()
        if remaining <= 0:
            raise _DeadlineExceeded
        timeout = asyncio.timeout(remaining)
        try:
            async with timeout:
                return await step(*args)
        except TimeoutError:
            if timeout.expired():
                raise _DeadlineExceeded from None
            raise

    async def _reserve(self, amount_usd: Decimal) -> Reservation:
        # A native `task.cancel()` inside `reserve` rolls its transaction back, or, if it lands just
        # after the commit, leaves a reserve row this turn never saw. Either way the ledger is
        # right (a reservation only ever counts toward the caps); only `cost_usd` can under-report.
        reservation = await reserve(
            self.deps.engine,
            self.deps.tenant_ctx,
            turn_id=self.turn_id,
            amount_usd=amount_usd,
            caps=self.deps.caps,
        )
        self.inflight = reservation
        return reservation

    async def _settle(self, reservation: Reservation, price: Callable[[], Decimal] | None) -> None:
        """Settle a reservation once, never again.

        A native `task.cancel()` can cut a settle (or the reserve before it). The transaction rolls
        back whole and the reservation is still `inflight`, so `_finish` keeps it: the ledger stays
        right, and only this turn's own `cost_usd` can under-report.

        A cost that can't be worked out (`price` None or raising) or a settle that fails keeps the
        reservation, which counts at its amount."""
        if price is None:
            self._keep(reservation)
            return
        try:
            actual_usd = price()
        except Exception as error:
            logger.warning("Pricing a call failed (%s); keeping its reservation", error_name(error))
            self._keep(reservation)
            return
        try:
            with (
                anyio.CancelScope(shield=True),
                anyio.move_on_after(SHIELDED_STEP_TIMEOUT.total_seconds()) as bound,
            ):
                await settle(
                    self.deps.engine, self.deps.tenant_ctx, reservation, actual_usd=actual_usd
                )
            if bound.cancelled_caught:
                logger.warning("Settling a reservation timed out; keeping it")
                self._keep(reservation)
                return
        except Exception as error:
            # A settle row has no tie to its reservation, so a second try could count the
            # difference twice. The reservation stays as it is.
            logger.warning("Settling a reservation failed (%s); not retrying", error_name(error))
            self._keep(reservation)
            return
        self.cost_usd += actual_usd
        if self.inflight is reservation:
            self.inflight = None

    async def _contacts(self) -> tuple[HrContact, ...]:
        try:
            async with (
                asyncio.timeout(HR_CONTACT_TIMEOUT.total_seconds()),
                tenant_session(self.deps.engine, self.deps.tenant_ctx) as db,
            ):
                return tuple(await hr_contact(db))
        except Exception as error:  # A timeout too: the fixed text goes out without the names.
            logger.warning("Reading the HR contact failed (%s)", error_name(error))
            return ()

    # -- the guard --

    async def _screen(self) -> tuple[GuardOutcome | None, list[TurnEvent]]:
        """The guard's verdict, or None with the events that end the turn. When the guard can't
        run at all, the turn fails and the message, never read, still gets the emergency text
        (see `_late_escalation`)."""
        try:
            request = build_guard_request(
                self.question, self.previous_answer, self.conversation.guard_model
            )
            reservation = await self._reserve(guard_reservation_usd(request))
        except BudgetExceeded as error:
            self.budget_stopped = True
            self.fail(_budget_code(error.scope))
            return None, []
        except Exception as error:
            logger.error("Reserving for the guard failed (%s)", error_name(error))
            self.unscreened = True
            self.fail("internal")
            # The client sees `internal`; the row says the guard never ran, so the next message is
            # screened with the "can't answer right now" text as its context.
            self.error_code = "guard-error"
            return None, []
        try:
            outcome = await screen(self.deps.transport, request)
        except SpendLimitReached:
            # The API refused the request, so nothing was billed.
            await self._settle(reservation, lambda: Decimal(0))
            self.budget_stopped = True
            self.fail("spend-limit")
            return None, []
        usage = outcome.usage
        # Priced at the model that served it when that has a pinned price (the scripted stand-in
        # is free). The name the API echoes can be a dated snapshot with no pinned price, which
        # would be charged at the dearest rates, so then the pinned guard model is used.
        model = (
            outcome.served_by
            if outcome.served_by is not None and is_priced(outcome.served_by)
            else self.conversation.guard_model
        )
        await self._settle(
            reservation,
            None if usage is None else partial(turn_call_cost, [IterationUsage(model, usage)]),
        )
        self.guard_verdict = outcome.verdict_json()
        self.injection = outcome.injection_suspected
        if outcome.route == "crisis":
            self.status = "crisis"
            return None, [Escalation("crisis", CRISIS_TEXT, await self._contacts())]
        if outcome.route == "unavailable":
            self.status = "guard_unavailable"
            return None, [Escalation("unavailable", UNAVAILABLE_TEXT, await self._contacts())]
        return outcome, []

    # -- the loop --

    def _request(self, turn_messages: list[dict[str, Any]]) -> ModelRequest:
        conversation = self.conversation
        return model_request(
            model=conversation.model,
            effort=conversation.effort,
            messages=(*self.history, *turn_messages),
        )

    async def _loop(self) -> AsyncGenerator[TurnEvent]:
        outcome, early = await self._screen()
        for early_event in early:
            yield self._seen(early_event)
        if outcome is None:
            return
        self.guard_passed = True
        self.sensitive = outcome.escalation == "sensitive"

        # If this raises, the turn fails as `internal` and the question is still stored.
        context = turn_context(
            self.deps.actor_view,
            now=self.now,
            handbook_label=self.deps.handbook_label,
            operator_notes=outcome.operator_notes,
            outcomes=self.outcomes,
        )
        question_message = {"role": "user", "content": self.question_message.content}
        context_message: dict[str, Any] = {"role": "system", "content": [text_block(context)]}
        self.context_message = StoredMessage("system", context_message["content"])
        turn_messages = [question_message, context_message]
        previous_usage: Usage | None = None
        added_text = ""
        calls = 0
        reissues = 0

        while True:
            if calls >= MAX_MODEL_CALLS:
                self.fail("too-many-calls")
                return
            if self.deadline_loop_s - _clock() <= 0:
                # Nothing is reserved for a call that can't be made.
                self.fail("model-unavailable")
                return
            request = self._request(turn_messages)
            if previous_usage is None:
                estimate = first_call_input_tokens(request)
            else:
                estimate = estimate_input_tokens(previous_usage, added_text)
            try:
                reservation = await self._reserve(
                    reservation_usd(
                        request.model, estimated_input_tokens=estimate, max_tokens=MAX_TOKENS
                    )
                )
            except BudgetExceeded as error:
                self.fail(_budget_code(error.scope))
                return
            calls += 1

            finished: Finished | None = None
            shown_before = len(self.shown)
            saved_answer = self.taken_back_answer
            stream = self.deps.transport.stream(request)
            try:
                while True:
                    # Each read is bounded on its own, never across a yield: a deadline that fell
                    # while the consumer was busy would cancel the consumer's await.
                    event = await self._within(_next_event, stream)
                    if event is None:
                        break
                    event = scrubbed(event)
                    if isinstance(event, StatusNote):
                        text_of_note = one_line(event.text)
                        if _has_canary(self.sent_tail + self.held + text_of_note):
                            # The prompt's canary must never reach a person, even split across
                            # notes. By type only; the turn ends like any prompt leak.
                            logger.warning("status note withheld")
                            self._prompt_leak()
                            return
                        tail = self.sent_tail + text_of_note
                        self.sent_tail = tail[_tail_start(tail) :]
                        yield self._seen(Status(event.text))
                    elif isinstance(event, ModelText):
                        text = event.text
                        send, leaked = self._hold(text)
                        if leaked:
                            self._prompt_leak()
                            return
                        if send:
                            yield self._shown_text(send)
                    elif isinstance(event, TextBlockEnd):
                        flushed = self._flush_held()
                        if flushed is not None:
                            yield flushed
                        # In UTF-16 units, for the browser (see `utf16_length`).
                        length = self.shown_units
                        for cited in self.mapper.on_block_end(length, event.citations):
                            self.citations.append(cited.to_json())
                            self.citation_events.append(cited)
                            yield self._seen(Citation(cited))
                    elif isinstance(event, ToolCall):
                        pass  # The tool_use blocks of the finished message are what is run.
                    elif isinstance(event, Finished):
                        flushed = self._flush_held()
                        if flushed is not None:
                            yield flushed
                        finished = event
            except InvalidToolInput:
                # Nothing of this call is complete or stored, and its reservation stays (the cost is
                # unknown). The same request goes out again as the next call. Text it had already
                # shown is taken back first, so the person is not shown the same words twice; it is
                # an aborted call's, not a working note, so it is not kept as an answer, and the
                # answer saved before the call is kept.
                self._keep(reservation)
                self.held = ""  # Held text was never sent; the retry starts clean.
                reissues += 1
                # One re-issue per turn: a model that keeps producing broken input won't mend.
                if reissues > 1:
                    self.fail("internal")
                    return
                if len(self.shown) > shown_before:
                    self._forget_what_was_shown()
                    self.taken_back_answer = saved_answer
                    yield self._seen(TextRetracted())
                continue
            except ModelUnavailable as error:
                self._keep(reservation)
                self.fail("model-unavailable", request_id=error.request_id)
                return
            except SpendLimitReached:
                await self._settle(reservation, lambda: Decimal(0))  # Refused, so not billed.
                self.fail("spend-limit")
                return
            except _DeadlineExceeded:
                self._keep(reservation)
                self.fail("model-unavailable")
                return
            finally:
                close = getattr(stream, "aclose", None)
                if close is not None:
                    try:
                        with (
                            anyio.CancelScope(shield=True),
                            anyio.move_on_after(SHIELDED_STEP_TIMEOUT.total_seconds()),
                        ):
                            await close()
                    except Exception as error:
                        logger.warning("Closing the model stream failed (%s)", error_name(error))

            if finished is None:
                self._keep(reservation)
                self.fail("model-unavailable")
                return
            await self._settle(reservation, partial(turn_call_cost, finished.iterations))
            self.iterations.extend(finished.iterations)
            self.fallback = self.fallback or finished.fell_back
            # One model, one name: the iterations' own model IDs. The message's `served_by` can be
            # a dated snapshot of the same model, so it is used only when there are no iterations.
            models = [item.model for item in finished.iterations] or [finished.served_by]
            self.last_served_by = models[-1]
            for model in models:
                if model not in self.served_by_models:
                    self.served_by_models.append(model)
            message = finished.message

            if finished.stop_reason == "tool_use":
                blocks = [b for b in message.get("content", []) if b.get("type") == "tool_use"]
                if self.shown:
                    # Streamed live, then taken back: it was a note before a tool call, not the
                    # answer. First, so a turn that fails just below does not keep it as its
                    # answer, and before the round's `tool.started` events.
                    taken_back = self._take_back_the_note()
                    if taken_back is None:
                        logger.warning("status note withheld")
                        self._prompt_leak()
                        return
                    for taken_back_event in taken_back:
                        yield taken_back_event
                if not blocks:
                    self.fail("internal")
                    return
                if calls >= MAX_MODEL_CALLS:
                    # Another call can't follow, so these tools' results could never be used.
                    self.fail("too-many-calls")
                    return
                results: dict[int, ToolOutcome] = {}
                summaries = [describe_call(b["name"], b.get("input")) for b in blocks]
                slot_of = self._plan_tools(blocks, summaries, results)
                for index in slot_of:
                    block = blocks[index]
                    yield self._seen(ToolStarted(block["id"], block["name"], summaries[index]))
                try:
                    # aclosing, so an early close cancels the tool tasks right now.
                    async with aclosing(
                        self._run_tools(blocks, summaries, results, slot_of)
                    ) as tool_events:
                        async for tool_event in tool_events:
                            yield tool_event
                except _DeadlineExceeded:
                    return
                tool_blocks: list[dict[str, Any]] = []
                round_sources: list[SourceEntry] = []
                for index, block in enumerate(blocks):
                    result = results[index]
                    item: dict[str, Any] = {
                        "type": "tool_result",
                        "tool_use_id": block["id"],
                        "content": result.content,
                    }
                    if result.is_error:
                        item["is_error"] = True
                    tool_blocks.append(item)
                    round_sources.extend(result.sources)
                    for source in result.sources:
                        self.sections.append(
                            {"sectionId": source.section_id, "passageIds": list(source.passage_ids)}
                        )
                assistant_dict = {"role": "assistant", "content": message["content"]}
                results_dict = {"role": "user", "content": tool_blocks}
                self.rounds += [
                    StoredMessage("assistant", message["content"]),
                    StoredMessage("user", tool_blocks, tuple(round_sources)),
                ]
                self.mapper.add(round_sources)
                turn_messages = [*turn_messages, assistant_dict, results_dict]
                previous_usage = finished.usage
                # Only the tool results are new input: the assistant message is already counted in
                # the previous call's output tokens (see `estimate_input_tokens`).
                added_text = _serialize([results_dict])
                continue

            if finished.stop_reason == "end_turn":
                if _has_tool_use(message):
                    self.fail("internal")
                    return
                if _has_text(message):
                    self.final = StoredMessage("assistant", message["content"])
                elif "".join(self.shown).strip():
                    # This call streamed text that its finished message doesn't hold, so there is
                    # no message to store. What was shown stands as the answer.
                    self.answer_without_final = True
                else:
                    # The model ended with nothing more to say, so the text it wrote before its
                    # last tool call was the answer after all. It was taken back as a note; send
                    # it again as the answer. The empty message can't be stored.
                    restored = self._restore_the_answer()
                    if restored is None:
                        self._prompt_leak()
                        return
                    if not restored:
                        self.fail("internal")
                        return
                    for restored_event in restored:
                        yield restored_event
                    self.answer_without_final = True
                self.status = "completed"
            elif finished.stop_reason == "max_tokens":
                if not "".join(self.shown).strip():
                    # Nothing was written in this call (the thinking used the whole budget). What
                    # was taken back before the last tool call is usually a working note ("Let me
                    # look that up first"), not an answer, so it is not brought back here (only
                    # a call that ends cleanly with nothing more to say does that). Nothing is
                    # shown, so there is no answer to mark incomplete.
                    self.taken_back_answer = None
                    self.fail("internal")
                    return
                if _ends_cleanly(message):
                    self.final = StoredMessage("assistant", message["content"])
                else:
                    # A dangling tool_use, or a thinking block cut off before its signature,
                    # would break every later turn. The complete rounds are stored without this
                    # message; the person keeps the text they saw.
                    self.answer_without_final = True
                self.status = "completed"
                self.error_code = "max-tokens"
                self.incomplete = True
            elif finished.stop_reason == "refusal":
                self.refusal = True
                if self.shown:
                    # The client holds this partial text (and its citations); tell it to drop
                    # them before the refusal error, or they would stay beside it.
                    yield self._seen(TextRetracted())
                self._forget_what_was_shown()
                self.taken_back_answer = None
                self.fail("refusal")
                return
            else:
                logger.warning("Unexpected stop reason %r", finished.stop_reason[:40])
                self.fail("internal")
                return

            return

    async def _offer_escalation(self, kind: str = "sensitive", reason: str | None = None) -> None:
        try:
            async with tenant_session(self.deps.engine, self.deps.tenant_ctx) as db:
                await record_event(
                    db,
                    tenant_id=self.deps.actor.tenant_id,
                    actor_id=self.deps.actor.person_id,
                    action="escalation.offered",
                    target_type="ai_turn",
                    target_id=self.turn_id,
                    after={"kind": kind} if reason is None else {"kind": kind, "reason": reason},
                    via="assistant",
                )
        except Exception as error:
            logger.warning("Auditing the escalation failed (%s)", error_name(error))

    def _plan_tools(
        self,
        blocks: list[dict[str, Any]],
        summaries: list[str],
        results: dict[int, ToolOutcome],
    ) -> dict[int, int]:
        """Decide which of a response's tool calls run. The others get their error result now (the
        API needs a result for every call) but no events and no trace entry of their own: one
        trace entry, `{"name": "skipped", "count": N, ...}`, records how many the round skipped.

        Returns the calls that run, each with its slot in the trace: one slot per tool, in the
        model's order, filled as the tool finishes. A tool still running when the turn is canceled
        keeps its slot: not ok, with what it was asked."""
        runnable: list[int] = []
        over_limit = 0
        extra_cards = 0
        made_a_card = False
        for index in range(len(blocks)):
            if index >= MAX_TOOLS_PER_RESPONSE:
                message = (
                    f"At most {MAX_TOOLS_PER_RESPONSE} tools can run at once. "
                    "Ask for the rest in another step."
                )
                over_limit += 1
            elif self.tool_runs >= MAX_TOOL_RUNS_PER_TURN:
                message = (
                    f"At most {MAX_TOOL_RUNS_PER_TURN} tools can run for one question. "
                    "Answer with what you have."
                )
                over_limit += 1
            elif proposes(blocks[index]["name"]) and made_a_card:
                # Two cards from one response would both be told "a card is shown", but a new card
                # replaces the pending one, so only the first call in call order is made.
                message = ONE_CARD_TEXT
                extra_cards += 1
            else:
                self.tool_runs += 1
                made_a_card = made_a_card or proposes(blocks[index]["name"])
                runnable.append(index)
                continue
            results[index] = failure(message)
        base = len(self.tool_trace)
        slot_of = {index: base + k for k, index in enumerate(runnable)}
        self.tool_trace.extend(
            {"name": blocks[i]["name"], "inputSummary": summaries[i], "ok": False, "durationMs": 0}
            for i in runnable
        )
        for count, reason in ((over_limit, "limit"), (extra_cards, "one card at a time")):
            if count:
                self.tool_trace.append(
                    {
                        "name": "skipped",
                        "inputSummary": f"{count} calls not run ({reason})",
                        "ok": False,
                        "durationMs": 0,
                        "count": count,
                    }
                )
        return slot_of

    async def _run_tools(
        self,
        blocks: list[dict[str, Any]],
        summaries: list[str],
        results: dict[int, ToolOutcome],
        slot_of: dict[int, int],
    ) -> AsyncGenerator[TurnEvent]:
        """Run the tools at the same time, yielding each `tool.finished` as its tool ends."""
        deps = self.deps
        context = ToolContext(
            engine=deps.engine,
            tenant_ctx=deps.tenant_ctx,
            actor=deps.actor,
            asker=deps.asker,
            version_id=deps.version_id,
            embedder=deps.embedder,
            now=self.now,
            conversation_id=self.conversation.id,
            turn_id=self.turn_id,
        )
        finished_events: asyncio.Queue[ToolFinished | Proposal] = asyncio.Queue()
        slots = asyncio.Semaphore(MAX_CONCURRENT_TOOLS)

        async def one(index: int, block: dict[str, Any]) -> None:
            started = _clock()
            summary = summaries[index]  # For the results that fail without one of their own.
            try:
                async with slots, asyncio.timeout(TOOL_TIMEOUT.total_seconds()):
                    outcome = await run_tool(block["name"], block.get("input"), context)
            except TimeoutError:
                logger.warning("A tool timed out: %s", block["name"][:40])
                outcome = failure(
                    "That tool took too long. Try again, or answer without it.", summary
                )
            except asyncio.CancelledError:
                raise
            except BaseException as error:  # A tool bug is an error result, never a failed turn.
                # Even one that isn't an Exception: this task must queue its one `ToolFinished`,
                # or the loop waits for it until the deadline.
                logger.warning("A tool failed (%s): %s", error_name(error), block["name"][:40])
                outcome = failure("That tool failed. Try again, or answer without it.", summary)
            results[index] = outcome
            elapsed_ms = int((_clock() - started) * 1000)
            self.tool_trace[slot_of[index]] = {
                "name": block["name"],
                "inputSummary": outcome.summary,
                "ok": not outcome.is_error,
                "durationMs": elapsed_ms,
            }
            finished_events.put_nowait(
                ToolFinished(block["id"], not outcome.is_error, outcome.summary, elapsed_ms)
            )
            if outcome.proposal is not None and not outcome.is_error:
                # Reported to the model as made, so the ending keeps it; then sent to the browser,
                # right after this tool's own `tool.finished`.
                self.reported_proposals.add(outcome.proposal.id)
                finished_events.put_nowait(Proposal(outcome.proposal))

        tasks = [asyncio.create_task(one(index, blocks[index])) for index in slot_of]
        try:
            # One `tool.finished` for each tool that runs, and a `proposal` after the ones that made
            # a card.
            remaining = len(slot_of)
            while remaining:
                event = await self._within(finished_events.get)
                if isinstance(event, ToolFinished):
                    remaining -= 1
                yield event
            # A tool queues its `proposal` right after its `tool.finished`, in the same step, so
            # the last one is already waiting here.
            while not finished_events.empty():
                yield finished_events.get_nowait()
        except _DeadlineExceeded:
            self.fail("model-unavailable")
            raise
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def events(self) -> AsyncGenerator[TurnEvent]:
        """Stream the turn: started, the guard's escalation or the loop's events, then the closing
        events once the end-of-turn writes are done. Iterate it right away: a turn nobody reads
        stays `running` until the abandoned-turn rule fails it. A consumer that stops iterating
        (`aclose()`), or a canceled task, ends the turn as `stopped`."""
        try:
            yield TurnStarted(self.turn_id)
            loop = self._loop()
            try:
                async for event in loop:
                    if _holds_the_canary(event):
                        # The one place events leave: nothing with the canary in any string field
                        # goes out. The turn ends as a prompt leak.
                        self._prompt_leak()
                        break
                    yield event
            finally:
                await loop.aclose()
        except Exception as error:
            logger.error("Turn %s failed (%s)", self.turn_id, error_name(error))
            self.fail("internal")
        finally:
            await self.finish()
        for event in await self.closing_events():
            if not _holds_the_canary(event):
                yield event

    # -- the end --

    def _late_escalation(self) -> Literal["sensitive", "unavailable"] | None:
        """The escalation that goes out with the turn's last events, after the answer or the error.

        Crisis and "guard unavailable" escalations went out as soon as they were known. A message
        the guard never read gets the "can't answer right now" text (911, 988, HR); a sensitive
        one gets the HR contact whether the turn answered, failed, or was stopped (the stop's
        closing event rarely reaches anyone, but the audit and the reload's panel do). A stopped
        turn that the guard never read has nothing to offer.
        """
        if self.status not in ("completed", "failed", "stopped"):
            return None
        if self.status == "stopped":
            return "sensitive" if self.sensitive else None
        if self.unscreened:
            return "unavailable"
        return "sensitive" if self.sensitive else None

    async def closing_events(self) -> list[TurnEvent]:
        events = self._closing_events()
        kind = self._late_escalation()
        if kind is not None and events:
            escalation = Escalation(
                kind,
                SENSITIVE_TEXT if kind == "sensitive" else UNAVAILABLE_TEXT,
                await self._contacts(),
            )
            # After an error; before the completion, so the HR contact follows the answer.
            if isinstance(events[0], TurnCompleted):
                events.insert(0, escalation)
            else:
                events.append(escalation)
        return [self._seen(event) for event in events]

    def _closing_events(self) -> list[TurnEvent]:
        if self.finish_failed:
            return [Error("internal", ERROR_TEXTS["internal"])]
        if self.error is not None:
            return [self.error]
        if self.status == "completed":
            return [
                TurnCompleted(
                    self.turn_id,
                    self.last_served_by,
                    TurnUsage(*self._tokens()),
                    incomplete=self.incomplete,
                )
            ]
        return []

    def _tokens(self) -> tuple[int, int]:
        usage = total_usage(self.iterations)
        return usage.input_tokens, usage.output_tokens

    async def finish(self) -> None:
        """The end-of-turn writes. Shielded, so a canceled task still saves its turn."""
        with (
            anyio.CancelScope(shield=True),
            anyio.move_on_after(CLEANUP_TIMEOUT.total_seconds()) as bound,
        ):
            await self._finish()
        if bound.cancelled_caught:
            logger.error("Recording the end of turn %s timed out", self.turn_id)
            self.finish_failed = True

    async def _finish(self) -> None:
        if self.inflight is not None:
            self._keep(self.inflight)
        if self.status is None:
            self.status = "stopped"
        kind = self._audited_escalation()
        if kind is not None:
            # First, and in its own try, so a slow history write, a failed finish, or the cleanup
            # bound can't lose the audit (invariant 7).
            await self._offer_escalation(kind, reason="budget" if self.budget_stopped else None)
        if self.guard_passed:
            self.history_stored = await self._store_history()
        if self.first_event_ms is None and (self.error is not None or self.sensitive):
            # The error (and any escalation) goes out right after this write: it is the first
            # thing the person sees.
            self.first_event_ms = int((_clock() - self.started_loop_s) * 1000)
        # What is stored is checked like what is sent: a tool summary or citation holding the
        # canary is dropped, never written to the turn.
        for entry in self.tool_trace:
            if _has_canary(entry["inputSummary"]):
                entry["inputSummary"] = ""
        self.citations = [c for c in self.citations if not any(_has_canary(t) for t in _strings(c))]
        usage = total_usage(self.iterations)
        outcome = TurnOutcome(
            status=self.status,
            error_code=self.error_code,
            answer_text="".join(self.shown),
            citations=self.citations,
            guard_verdict=self.guard_verdict,
            tool_calls=self.tool_trace,
            sections_retrieved=self.sections,
            served_by_models=self.served_by_models,
            effort=self.conversation.effort,
            prompt_version=self.conversation.prompt_version,
            toolset_version=self.conversation.toolset_version,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read_tokens=usage.cache_read_tokens,
            cache_write_tokens=usage.cache_write_tokens,
            cost_usd=self.cost_usd,
            first_event_ms=self.first_event_ms,
            total_ms=int((_clock() - self.started_loop_s) * 1000),
            refusal=self.refusal,
            fallback=self.fallback,
            injection_suspected=self.injection,
        )
        try:
            async with tenant_session(self.deps.engine, self.deps.tenant_ctx) as db:
                # The turn's row first, then its cards, in one transaction: a confirm sees either
                # both ended or neither (the reverse order deadlocks with a late proposal).
                await finish_turn(db, self.turn_id, outcome)
                await self._cancel_cards(db)
        except Exception as error:
            logger.error(
                "Recording the end of turn %s failed (%s)", self.turn_id, error_name(error)
            )
            self.finish_failed = True
            return

    async def _cancel_cards(self, db: AsyncSession) -> None:
        """Cancel the turn's pending cards that its stored history doesn't back, in the ending's own
        transaction. A turn that completed with its whole history stored keeps the cards the model
        was told about; every other ending (stopped, failed, deadline, crisis, a question-only
        history) cancels all of them. Even a kept turn cancels a card no successful tool outcome
        reported: it was stored while its tool timed out or was canceled."""
        ctx = self.deps.tenant_ctx
        if self.status == "completed" and self.history_stored:
            await cancel_unreported_proposals_in(
                db, ctx, self.turn_id, self.reported_proposals, "turn-incomplete"
            )
        else:
            await cancel_turn_proposals_in(db, ctx, self.turn_id, "turn-incomplete")

    def _audited_escalation(self) -> str | None:
        if self.budget_stopped:
            # Set only where the guard could not run, so the message is unscreened. A late stop at
            # the model call leaves it unset and takes `_late_escalation` below (sensitive).
            return "unavailable"  # No event goes out, but the unscreened stop is audited.
        if self.status == "crisis":
            return "crisis"
        if self.status == "guard_unavailable":
            return "unavailable"
        return self._late_escalation()

    async def _store_history(self) -> bool:
        """Put this turn into history: all of it in one append when it ended with a storable
        answer (the question, the context, every round, and the answer), otherwise its question
        alone, so the next turn's history shows what was asked and replays nothing half-finished.

        If the whole turn is refused, the question alone is tried in its own attempt. Nothing here
        raises, so `finish_turn` always runs. Returns whether the whole turn was stored."""
        complete = self.final is not None or (self.answer_without_final and self.rounds)
        if complete and self.status == "completed" and self.context_message:
            # With no final message the history ends on the last tool results, and the next
            # question makes two user messages in a row, which is allowed.
            tail = [self.final] if self.final is not None else []
            whole = [self.question_message, self.context_message, *self.rounds, *tail]
            if await self._try_append(whole):
                return True
        await self._try_append([self.question_message])
        return False

    async def _try_append(self, batch: list[StoredMessage]) -> bool:
        try:
            async with tenant_session(self.deps.engine, self.deps.tenant_ctx) as db:
                await append_messages(db, self.conversation.id, self.turn_id, batch)
        except Exception as error:
            logger.warning("Storing the turn's messages failed (%s)", error_name(error))
            return False
        return True


async def start_turn_run(
    deps: TurnDeps, *, conversation: AiConversation, question: str, now: datetime
) -> TurnRun:
    """Check the question and the conversation, start the turn, and return it. Await this before
    the response is sent: the checks raise here, not on the first event.

    Raises `ValueError` for a question that isn't 1 to 2,000 characters after trimming,
    `ConversationNotFound` for a conversation that isn't the actor's, `ConversationOutdated` for a
    prompt or tool set that has moved on, and `TurnRunning` (from the store) when a turn is in
    progress.
    The route maps them to 422, 404, 409, and 409. The personal-data check is the route's. Then
    iterate `TurnRun.events()` right away.
    """
    trimmed = question.strip()
    if not 1 <= len(trimmed) <= MAX_QUESTION_CHARACTERS:
        raise ValueError(f"a question is 1 to {MAX_QUESTION_CHARACTERS} characters")
    if (
        conversation.person_id != deps.actor.person_id
        or conversation.tenant_id != deps.actor.tenant_id
    ):
        raise ConversationNotFound
    if conversation_is_outdated(conversation):
        raise ConversationOutdated
    return await TurnRun.begin(deps, conversation, trimmed, now)


async def run_turn(
    deps: TurnDeps, *, conversation: AiConversation, question: str, now: datetime
) -> AsyncIterator[TurnEvent]:
    """Start a turn and stream it, for callers that don't need the checks apart from the stream.
    The checks raise on the first event here; the stream route uses `start_turn_run` instead."""
    run = await start_turn_run(deps, conversation=conversation, question=question, now=now)
    events = run.events()
    try:
        async for event in events:
            yield event
    finally:
        await events.aclose()
