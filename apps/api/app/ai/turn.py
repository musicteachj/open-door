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
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from functools import partial
from typing import Any, ClassVar, Literal
from uuid import UUID

import anyio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.ai.budget import BudgetExceeded, Caps, Reservation, reserve, settle
from app.ai.citations import CitationEvent, CitationMapper
from app.ai.context import ActorView, turn_context
from app.ai.conversations import (
    SourceEntry,
    StoredMessage,
    TurnOutcome,
    append_messages,
    finish_turn,
    model_history,
    recover_abandoned,
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
from app.ai.prompts.versions import CANARY, PROMPT_VERSION, TOOLSET_VERSION, system_prompt
from app.ai.text import error_name, one_line
from app.ai.tools.base import ToolContext, ToolOutcome, failure, text_block
from app.ai.tools.registry import TOOL_DEFINITIONS, describe_call, run_tool
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
from app.db.models import AiConversation, AiTurn
from app.db.tenancy import TenantContext, tenant_session
from app.domain.handbook.applicability import Asker
from app.modules.audit.service import record_event
from app.policy import Actor

logger = logging.getLogger(__name__)

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
# The crisis text never waits on the HR lookup longer than this.
HR_CONTACT_TIMEOUT = timedelta(seconds=2)
# Closing the model's stream, and settling a call, are shielded from cancellation (the first so the
# upstream request stops and no more billed tokens are generated); this bounds the wait.
SHIELDED_STEP_TIMEOUT = timedelta(seconds=5)

ErrorCode = Literal[
    "refusal",
    "model-unavailable",
    "budget-sandbox",
    "budget-daily",
    "too-many-calls",
    "internal",
]
EndStatus = Literal["completed", "stopped", "failed", "crisis", "guard_unavailable"]


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
    included), and its cost in dollars (the guard's included)."""

    input_tokens: int
    output_tokens: int
    cost_usd: Decimal

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
    | Citation
    | ToolStarted
    | ToolFinished
    | Escalation
    | Error
    | TurnCompleted
)
# What a person can see, for the time to the first visible event.
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
    embedder: Embedder
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


def _strip_format(text: str) -> str:
    """The text without Unicode format characters (category Cf: zero-width spaces and joiners,
    directional marks), which can hide a phrase from an exact match and are invisible anyway."""
    return "".join(char for char in text if unicodedata.category(char) != "Cf")


def _keep_from(text: str, count: int) -> int:
    """The index from which `text` ends in `count` characters that are not format characters (0 if
    it holds fewer), so what is held back counts the characters a person would see."""
    seen = 0
    for index in range(len(text) - 1, -1, -1):
        if unicodedata.category(text[index]) != "Cf":
            seen += 1
            if seen == count:
                return index
    return 0


def _strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list | tuple):
        for item in value:
            yield from _strings(item)


def _holds_the_canary(event: TurnEvent) -> bool:
    """Whether any string an event would send holds the prompt's canary. A boolean, so nothing
    that checks it ever prints the canary."""
    return any(CANARY in _strip_format(text) for text in _strings(event.to_json()))


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
    if status == "failed" and error_code in ("budget-sandbox", "budget-daily"):
        return ERROR_TEXTS[error_code]
    return None


def _budget_code(scope: str) -> ErrorCode:
    return "budget-sandbox" if scope == "sandbox" else "budget-daily"


def _clock() -> float:
    """Seconds on the monotonic clock. The one place the turn reads time, so a test can move it."""
    return time.monotonic()


def utf16_length(text: str) -> int:
    """The length in UTF-16 code units, which is what a browser's string indexes count. An emoji
    is two units but one Python character, so a citation offset in characters would land early."""
    return len(text.encode("utf-16-le")) // 2


# --- The turn ---------------------------------------------------------------------------------


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
    ) -> None:
        self.deps = deps
        self.conversation = conversation
        self.question = question
        self.now = now
        self.turn_id = turn_id
        self.history = history
        self.mapper = CitationMapper(sources)
        self.previous_answer = previous_answer
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
        self.last_shown_char = ""
        self.shown: list[str] = []
        # The shown text's length in UTF-16 units, kept running so a block end is not a re-scan.
        self.shown_units = 0
        # Model text not yet sent: the last `len(CANARY) - 1` characters are held back, so a canary
        # split across deltas is still caught before any part that completes it goes out.
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

    # -- start --

    @classmethod
    async def begin(
        cls, deps: TurnDeps, conversation: AiConversation, question: str, now: datetime
    ) -> "TurnRun":
        """Recover an abandoned turn, add this one, and read what the turn starts from. Raises
        `TurnRunning` when a turn is still in progress."""
        async with tenant_session(deps.engine, deps.tenant_ctx) as db:
            await recover_abandoned(db, conversation.id)
            turn = await start_turn(db, conversation, question)
            history = await model_history(db, conversation.id)
            sources = await search_sources(db, conversation.id)
            previous = (
                await db.execute(
                    select(AiTurn.answer_text, AiTurn.status, AiTurn.error_code)
                    .where(AiTurn.conversation_id == conversation.id, AiTurn.id != turn.id)
                    .order_by(AiTurn.started_at.desc(), AiTurn.id.desc())
                    .limit(1)
                )
            ).first()
        return cls(
            deps,
            conversation,
            question,
            now,
            turn_id=turn.id,
            history=history,
            sources=sources,
            previous_answer=_previous_answer(previous),
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
        if CANARY in _strip_format(self.sent_tail + self.held + text):
            return "", True
        buffer = self.held + text
        cut = _keep_from(buffer, len(CANARY) - 1)
        send = buffer[:cut]
        self.held = buffer[cut:]
        return send, False

    def _flush_held(self) -> TurnEvent | None:
        """Send the held text, at a block end or the end of a call, before any citation, so the
        offsets count it."""
        text, self.held = self.held, ""
        return self._shown_text(text) if text else None

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
        if text:
            self.last_shown_char = text[-1]
            tail = self.sent_tail + text
            self.sent_tail = tail[_keep_from(tail, len(CANARY) - 1) :]
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
            self.fail("budget-daily")
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
        return ModelRequest(
            model=conversation.model,
            system=(
                {
                    "type": "text",
                    "text": system_prompt(),
                    "cache_control": {"type": "ephemeral"},
                },
            ),
            tools=tuple(TOOL_DEFINITIONS),
            messages=(*self.history, *turn_messages),
            effort=conversation.effort,
            max_tokens=MAX_TOKENS,
            betas=BETAS,
            fallbacks="default",
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
                estimate = estimate_input_tokens(
                    None,
                    _serialize(
                        {
                            "system": list(request.system),
                            "tools": list(request.tools),
                            "messages": list(request.messages),
                        }
                    ),
                )
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
            call_has_text = False
            shown_before = len(self.shown)
            stream = self.deps.transport.stream(request)
            try:
                while True:
                    # Each read is bounded on its own, never across a yield: a deadline that fell
                    # while the consumer was busy would cancel the consumer's await.
                    event = await self._within(_next_event, stream)
                    if event is None:
                        break
                    if isinstance(event, StatusNote):
                        text_of_note = one_line(event.text)
                        if CANARY in _strip_format(self.sent_tail + self.held + text_of_note):
                            # The prompt's canary must never reach a person, even split across
                            # notes. By type only; the turn ends like any prompt leak.
                            logger.warning("status note withheld")
                            self._prompt_leak()
                            return
                        tail = self.sent_tail + text_of_note
                        self.sent_tail = tail[_keep_from(tail, len(CANARY) - 1) :]
                        yield self._seen(Status(event.text))
                    elif isinstance(event, ModelText):
                        text = event.text
                        if text and not call_has_text and self.last_shown_char.strip():
                            # Earlier text would run into this call's first word. It travels
                            # with that text, so it is neither sent nor counted before it is.
                            text = "\n\n" + text
                        call_has_text = call_has_text or bool(event.text)
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
                # unknown). If it showed no text, the same request goes out again as the next call.
                # If it showed some, a retry would show the person the same words twice and a
                # stream can't take text back, so the turn ends instead.
                self._keep(reservation)
                self.held = ""  # Held text was never sent; the retry starts clean.
                reissues += 1
                # One re-issue per turn: a model that keeps producing broken input won't mend.
                if len(self.shown) > shown_before or reissues > 1:
                    self.fail("internal")
                    return
                continue
            except ModelUnavailable as error:
                self._keep(reservation)
                self.fail("model-unavailable", request_id=error.request_id)
                return
            except SpendLimitReached:
                await self._settle(reservation, lambda: Decimal(0))  # Refused, so not billed.
                self.fail("budget-daily")
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
                    # The answer was already shown (before the last tool call); the model ended
                    # with nothing more to say. The empty message can't be stored.
                    self.answer_without_final = True
                else:
                    self.fail("internal")
                    return
                self.status = "completed"
            elif finished.stop_reason == "max_tokens":
                if not "".join(self.shown).strip():
                    # Nothing was written (the thinking used the whole budget). There is no
                    # answer to mark incomplete.
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
                self.shown.clear()
                self.shown_units = 0
                self.last_shown_char = ""
                self.citations.clear()
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
        for index in range(len(blocks)):
            if index >= MAX_TOOLS_PER_RESPONSE:
                message = (
                    f"At most {MAX_TOOLS_PER_RESPONSE} tools can run at once. "
                    "Ask for the rest in another step."
                )
            elif self.tool_runs >= MAX_TOOL_RUNS_PER_TURN:
                message = (
                    f"At most {MAX_TOOL_RUNS_PER_TURN} tools can run for one question. "
                    "Answer with what you have."
                )
            else:
                self.tool_runs += 1
                runnable.append(index)
                continue
            results[index] = failure(message)
        base = len(self.tool_trace)
        slot_of = {index: base + k for k, index in enumerate(runnable)}
        self.tool_trace.extend(
            {"name": blocks[i]["name"], "inputSummary": summaries[i], "ok": False, "durationMs": 0}
            for i in runnable
        )
        skipped = len(blocks) - len(runnable)
        if skipped:
            self.tool_trace.append(
                {
                    "name": "skipped",
                    "inputSummary": f"{skipped} calls not run (limit)",
                    "ok": False,
                    "durationMs": 0,
                    "count": skipped,
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
        )
        finished_events: asyncio.Queue[ToolFinished] = asyncio.Queue()
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

        tasks = [asyncio.create_task(one(index, blocks[index])) for index in slot_of]
        try:
            for _ in slot_of:
                yield await self._within(finished_events.get)
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
        one gets the HR contact whether the turn answered or failed. A stopped turn gets neither.
        """
        if self.status not in ("completed", "failed"):
            return None
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
                    TurnUsage(
                        *self._tokens(),
                        self.cost_usd,
                    ),
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
            await self._store_history()
        if self.first_event_ms is None and (self.error is not None or self.sensitive):
            # The error (and any escalation) goes out right after this write: it is the first
            # thing the person sees.
            self.first_event_ms = int((_clock() - self.started_loop_s) * 1000)
        # What is stored is checked like what is sent: a tool summary or citation holding the
        # canary is dropped, never written to the turn.
        for entry in self.tool_trace:
            if CANARY in entry["inputSummary"]:
                entry["inputSummary"] = ""
        self.citations = [c for c in self.citations if not any(CANARY in t for t in _strings(c))]
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
                await finish_turn(db, self.turn_id, outcome)
        except Exception as error:
            logger.error(
                "Recording the end of turn %s failed (%s)", self.turn_id, error_name(error)
            )
            self.finish_failed = True
            return

    def _audited_escalation(self) -> str | None:
        if self.budget_stopped:
            return "unavailable"  # No event goes out, but the unscreened stop is audited.
        if self.status == "crisis":
            return "crisis"
        if self.status == "guard_unavailable":
            return "unavailable"
        return self._late_escalation()

    async def _store_history(self) -> None:
        """Put this turn into history: all of it in one append when it ended with a storable
        answer (the question, the context, every round, and the answer), otherwise its question
        alone, so the next turn's history shows what was asked and replays nothing half-finished.

        If the whole turn is refused, the question alone is tried in its own attempt. Nothing here
        raises, so `finish_turn` always runs."""
        complete = self.final is not None or (self.answer_without_final and self.rounds)
        if complete and self.status == "completed" and self.context_message:
            # With no final message the history ends on the last tool results, and the next
            # question makes two user messages in a row, which is allowed.
            tail = [self.final] if self.final is not None else []
            whole = [self.question_message, self.context_message, *self.rounds, *tail]
            if await self._try_append(whole):
                return
        await self._try_append([self.question_message])

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
    `LookupError` for a conversation that isn't the actor's, `ConversationOutdated` for a prompt
    or tool set that has moved on, and `TurnRunning` (from the store) when a turn is in progress.
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
        raise LookupError("no such conversation")
    if (
        conversation.prompt_version != PROMPT_VERSION
        or conversation.toolset_version != TOOLSET_VERSION
    ):
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
