"""The conversation store: a person's conversations, the exact history the model is sent, and the
turns that produced it.

The functions take an `AsyncSession` that `tenant_session` has already scoped to the actor's
tenant and person. Row-level security is what keeps another person's rows out of every query here;
the functions never take a person ID from anywhere but the actor or the conversation row they are
given (invariant 1). They add no tenant filter of their own.

The conversation is append-only. A message is written once, as the API's own blocks, and is never
changed, so the history can go back to the model unchanged and its cached prefix stays valid. The
one row that changes is a turn, which is added as `running` and finished once (`finish_turn`).
"""

import base64
import json
import logging
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal, Self, cast
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import CursorResult, Interval, func, insert, literal, select, true, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.console_rows import build_abandoned_row
from app.ai.pricing import HAIKU
from app.ai.prompts.versions import PROMPT_VERSION, TOOLSET_VERSION
from app.ai.text import error_name
from app.ai.transport import count_search_results
from app.core.encryption import (
    DataKey,
    DecryptionFailed,
    KeyProvider,
    Place,
    new_data_key,
    open_,
    seal,
    wrap_aad,
)
from app.db.errors import constraint_name, has_sqlstate
from app.db.models import AiConsoleTurn, AiConversation, AiFeedback, AiMessage, AiTurn
from app.domain.cases import HQ_TIMEZONE
from app.policy import Actor

logger = logging.getLogger(__name__)

ONE_RUNNING_TURN_INDEX = "uq_ai_turns_one_running_per_conversation"
FEEDBACK_ONCE_CONSTRAINT = "uq_ai_feedback_tenant_id_turn_id"
# The SQLSTATE of the trigger that freezes a finished turn (migration 0008). A custom code, like
# the sandbox's OD001: class OD is ours.
FINISHED_TURN_SQLSTATE = "OD002"
# A turn whose task died can't finish itself. After this long it is given up on.
ABANDONED_AFTER = timedelta(minutes=10)


class TurnRunning(Exception):  # noqa: N818
    """The conversation already has a turn in progress."""


class TurnFinished(Exception):  # noqa: N818
    """The turn has ended, and an ended turn is never changed."""


@dataclass(frozen=True)
class Pins:
    """What a conversation begins with and keeps for its whole life."""

    model: str
    guard_model: str
    effort: str
    prompt_version: str
    toolset_version: str


# What a new conversation is pinned to: today's models, effort, prompt, and tool set. The one place
# the app (and the eval harness) reads them. Changing the model is an eval-gated decision
# (CLAUDE.md), and a conversation keeps what it began with.
CURRENT_PINS = Pins(
    model="claude-opus-5-5",
    guard_model=HAIKU,
    effort="low",
    prompt_version=PROMPT_VERSION,
    toolset_version=TOOLSET_VERSION,
)

CONVERSATIONS_TABLE = "ai_conversations"


@dataclass(frozen=True)
class ConversationCipher:
    """A conversation's data key, unwrapped once, with the sandbox it seals for. It seals and
    opens every encrypted value in the conversation's messages, turns, and feedback, each bound to
    its table, column, and row (ADR 0015). Its repr shows no key."""

    tenant_id: UUID
    conversation_id: UUID
    data_key: DataKey = field(repr=False)

    def require_conversation(self, conversation_id: UUID) -> None:
        """Refuse a conversation this key was not unwrapped for, before anything is sealed."""
        if conversation_id != self.conversation_id:
            raise ValueError("this cipher belongs to another conversation")

    def seal_text(self, text: str, table: str, column: str, row_id: UUID) -> bytes:
        place = Place(table, column, self.tenant_id, row_id)
        return seal(self.data_key, text.encode(), place=place)

    def open_text(self, ciphertext: bytes, table: str, column: str, row_id: UUID) -> str:
        place = Place(table, column, self.tenant_id, row_id)
        return open_(self.data_key, ciphertext, place=place).decode()

    def seal_tool_calls(
        self, turn_id: UUID, calls: Sequence[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """The trace with each `inputSummary` sealed and base64 encoded. Everything else stays
        readable. The entry's position is part of its place, so summaries can't be swapped between
        calls and still open."""
        out = []
        for index, call in enumerate(calls):
            if "inputSummary" in call:
                place = _summary_place(turn_id, index)
                sealed = self.seal_text(call["inputSummary"], *place)
                call = {**call, "inputSummary": base64.b64encode(sealed).decode()}
            out.append(call)
        return out

    def open_tool_calls(
        self, turn_id: UUID, calls: Sequence[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        out = []
        for index, call in enumerate(calls):
            if "inputSummary" in call:
                try:
                    sealed = base64.b64decode(call["inputSummary"], validate=True)
                except (ValueError, TypeError):  # binascii.Error is a ValueError
                    sealed = None
                if sealed is None:  # raised here, not in the handler, so nothing is chained
                    raise DecryptionFailed
                call = {
                    **call,
                    "inputSummary": self.open_text(sealed, *_summary_place(turn_id, index)),
                }
            out.append(call)
        return out


def _summary_place(turn_id: UUID, index: int) -> tuple[str, str, UUID]:
    # Every entry of a turn shares its row, so the entry's position goes in the column part.
    return "ai_turns", f"tool_calls.inputSummary:{index}", turn_id


def conversation_cipher(keys: KeyProvider, conversation: AiConversation) -> ConversationCipher:
    """Unwrap the conversation's data key. Raises `DecryptionFailed` if it does not open."""
    aad = wrap_aad(conversation.tenant_id, CONVERSATIONS_TABLE, conversation.id)
    data_key = keys.unwrap(conversation.key_id, conversation.wrapped_key, aad=aad)
    return ConversationCipher(conversation.tenant_id, conversation.id, DataKey(data_key))


@dataclass(frozen=True)
class TurnText:
    """A turn's encrypted text, opened: what the person asked, the answer (empty until the turn
    ends), and the trace with its input summaries in the clear."""

    question: str
    answer: str
    tool_calls: list[dict[str, Any]]


def open_turn(cipher: ConversationCipher, turn: AiTurn) -> TurnText:
    answer = turn.answer_ciphertext
    return TurnText(
        question=cipher.open_text(
            turn.question_ciphertext, "ai_turns", "question_ciphertext", turn.id
        ),
        answer=""
        if answer is None
        else cipher.open_text(answer, "ai_turns", "answer_ciphertext", turn.id),
        tool_calls=cipher.open_tool_calls(turn.id, turn.tool_calls),
    )


def open_reason(cipher: ConversationCipher, feedback: AiFeedback) -> str | None:
    if feedback.reason_ciphertext is None:
        return None
    return cipher.open_text(
        feedback.reason_ciphertext, "ai_feedback", "reason_ciphertext", feedback.id
    )


FEEDBACK_REASON_MAX_CHARACTERS = 500


class FeedbackGiven(Exception):  # noqa: N818
    """The turn already has feedback. There is one per turn."""


class TurnNotFound(Exception):  # noqa: N818
    """No turn of the actor's has that ID. Dedicated, so a lookup error from a bug is never taken
    for it."""


class TurnNotCompleted(Exception):  # noqa: N818
    """Feedback is only for answers that finished."""


@dataclass(frozen=True)
class SourceEntry:
    """One `search_result` block the model was sent: what a citation to it needs to show."""

    section_id: str
    passage_ids: tuple[str, ...]
    title: str
    group_name: str
    audience_label: str
    last_updated: date
    deep_link: str

    def to_json(self) -> dict[str, Any]:
        """The form stored in ai_messages.sources."""
        return {
            "sectionId": self.section_id,
            "passageIds": list(self.passage_ids),
            "title": self.title,
            "groupName": self.group_name,
            "audienceLabel": self.audience_label,
            "lastUpdated": self.last_updated.isoformat(),
            "deepLink": self.deep_link,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Self:
        return cls(
            section_id=data["sectionId"],
            passage_ids=tuple(data["passageIds"]),
            title=data["title"],
            group_name=data["groupName"],
            audience_label=data["audienceLabel"],
            last_updated=date.fromisoformat(data["lastUpdated"]),
            deep_link=data["deepLink"],
        )


@dataclass(frozen=True)
class StoredMessage:
    """A message to store. `content` is the API's own blocks, exactly as the model should see them
    again. `sources` has one entry per `search_result` block in it, in block order.
    `reported_outcomes` is for a context message: a `told_entry` for each card it reports."""

    role: Literal["user", "assistant", "system"]
    content: list[dict[str, Any]]
    sources: tuple[SourceEntry, ...] = ()
    reported_outcomes: tuple[str, ...] = ()


@dataclass(frozen=True)
class TurnOutcome:
    """How a turn ended and what it cost: the columns `finish_turn` is allowed to write."""

    status: Literal["completed", "stopped", "failed", "crisis", "guard_unavailable"]
    error_code: str | None = None
    answer_text: str = ""
    citations: list[dict[str, Any]] = field(default_factory=list)
    guard_verdict: dict[str, Any] | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    sections_retrieved: list[dict[str, Any]] = field(default_factory=list)
    served_by_models: list[str] = field(default_factory=list)
    effort: str | None = None
    prompt_version: str | None = None
    toolset_version: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: Decimal = Decimal(0)
    first_event_ms: int | None = None
    total_ms: int | None = None
    refusal: bool = False
    fallback: bool = False
    injection_suspected: bool = False


async def create_conversation(
    db: AsyncSession, actor: Actor, pins: Pins, keys: KeyProvider
) -> AiConversation:
    """Add a conversation with a new data key of its own, wrapped for its sandbox and its ID. The
    ID is made here, before anything is sealed, because the wrapped key is bound to it."""
    conversation_id = uuid4()
    key_id, wrapped_key = keys.wrap(
        new_data_key(), aad=wrap_aad(actor.tenant_id, CONVERSATIONS_TABLE, conversation_id)
    )
    conversation = AiConversation(
        id=conversation_id,
        key_id=key_id,
        wrapped_key=wrapped_key,
        tenant_id=actor.tenant_id,
        person_id=actor.person_id,
        model=pins.model,
        guard_model=pins.guard_model,
        effort=pins.effort,
        prompt_version=pins.prompt_version,
        toolset_version=pins.toolset_version,
    )
    db.add(conversation)
    await db.flush()
    return conversation


async def current_conversation(db: AsyncSession, actor: Actor) -> AiConversation | None:
    """The actor's newest conversation, or None if they have none."""
    return (
        await db.scalars(
            select(AiConversation)
            .where(AiConversation.person_id == actor.person_id)
            # Conversations made in one transaction share a creation time. The id only makes the
            # order deterministic then; it doesn't say which is newer.
            .order_by(AiConversation.created_at.desc(), AiConversation.id.desc())
            .limit(1)
        )
    ).first()


async def model_history(
    db: AsyncSession, conversation_id: UUID, cipher: ConversationCipher
) -> list[dict[str, Any]]:
    """The messages as the Messages API takes them, in order and exactly as stored.

    Each message was sealed as the JSON text it was given, and `json.loads` keeps its key order,
    so a thinking block comes back with the bytes its signature covers. A ciphertext that was
    moved to another row raises `DecryptionFailed`.
    """
    rows = await db.execute(
        select(AiMessage.id, AiMessage.role, AiMessage.content_ciphertext)
        .where(AiMessage.conversation_id == conversation_id)
        .order_by(AiMessage.position)
    )
    return [
        {
            "role": role,
            "content": json.loads(
                cipher.open_text(ciphertext, "ai_messages", "content_ciphertext", message_id)
            ),
        }
        for message_id, role, ciphertext in rows.all()
    ]


def _tool_use_ids(message: StoredMessage) -> set[str]:
    return {b["id"] for b in message.content if b.get("type") == "tool_use"}


def _require_tool_results_first(message: StoredMessage) -> None:
    """Refuse a user message with a `tool_result` block after any other kind of block: the Messages
    API requires the results to come before the rest of the content."""
    seen_other = False
    for block in message.content:
        if block.get("type") != "tool_result":
            seen_other = True
        elif seen_other:
            raise ValueError("tool_result blocks must come before any other content in a message")


def _require_results_to_answer_the_call_before(
    messages: Sequence[StoredMessage], index: int
) -> None:
    """Refuse a user message whose `tool_result` blocks answer nothing in the assistant message
    just before it, in the same call.

    A tool call and its results are always stored together, so the call is in this batch. A result
    with no call before it would be stored for good, and the API refuses every later request that
    holds one.
    """
    result_ids = {
        b.get("tool_use_id") for b in messages[index].content if b.get("type") == "tool_result"
    }
    if not result_ids:
        return
    before = messages[index - 1] if index > 0 else None
    call_ids = _tool_use_ids(before) if before is not None and before.role == "assistant" else set()
    if not result_ids <= call_ids:
        stray = sorted(map(str, result_ids - call_ids))
        raise ValueError(
            "a user message has tool_result blocks that the assistant message just before it, in"
            f" the same call, did not ask for with tool_use blocks: {stray}"
        )


def _require_every_tool_call_answered(messages: Sequence[StoredMessage]) -> None:
    """Refuse a batch whose assistant `tool_use` blocks aren't answered inside it.

    A tool call and its results are stored together, in one call. A failure between two appends
    would leave a `tool_use` with no `tool_result` in the history, and the API refuses every later
    request that holds one, for good.
    """
    for index, message in enumerate(messages):
        if message.role == "user":
            _require_results_to_answer_the_call_before(messages, index)
            continue
        if message.role != "assistant":
            continue
        call_ids = _tool_use_ids(message)
        if not call_ids:
            continue
        following = messages[index + 1] if index + 1 < len(messages) else None
        answered = (
            {b.get("tool_use_id") for b in following.content if b.get("type") == "tool_result"}
            if following is not None and following.role == "user"
            else set()
        )
        if not call_ids <= answered:
            raise ValueError(
                "an assistant message has tool_use blocks that the next message, in the same"
                f" call, does not answer with tool_result blocks: {sorted(call_ids - answered)}"
            )


async def append_messages(
    db: AsyncSession,
    conversation_id: UUID,
    turn_id: UUID,
    messages: Sequence[StoredMessage],
    cipher: ConversationCipher,
) -> None:
    """Add messages after the conversation's last one, with their search sources, in one INSERT.

    The tenant and person come from the conversation row, which row-level security shows only to
    its owner. Only one turn at a time runs in a conversation, so positions can't race.
    """
    cipher.require_conversation(conversation_id)
    # One source per search_result block, or a citation's index would point at the wrong passage.
    for message in messages:
        found = count_search_results(message.content)
        if len(message.sources) != found:
            raise ValueError(
                f"a message holds {found} search_result blocks but was given"
                f" {len(message.sources)} sources"
            )
    for message in messages:
        if message.role == "assistant" and not message.content:
            # The API rejects an empty assistant message anywhere but last, so one in the history
            # (a refusal before any output makes exactly that) would wedge the conversation.
            raise ValueError("an assistant message with empty content can't be stored")
        for block in message.content:
            # The API rejects an empty text block anywhere but last, and a refusal or a max_tokens
            # stop can leave one. (A thinking block's empty text is normal under `display:
            # "updates"`, and only `text` blocks are checked.)
            if block.get("type") == "text" and not str(block.get("text", "")).strip():
                raise ValueError("a message with an empty text block can't be stored")
        _require_tool_results_first(message)
    _require_every_tool_call_answered(messages)
    if not messages:
        return
    conversation = (
        await db.execute(
            select(AiConversation.tenant_id, AiConversation.person_id).where(
                AiConversation.id == conversation_id
            )
        )
    ).one_or_none()
    if conversation is None:
        raise LookupError("no such conversation")
    # The database's keys tie a message to its owner and its turn, but not the two to each other.
    # The row is locked until this transaction ends, so that recovery can't fail the turn between
    # the check that it is still running and the insert. A task that wakes after its turn was
    # failed would otherwise add a half-turn to the history that every later call is built on. The
    # lock is FOR NO KEY UPDATE, which still excludes recovery's UPDATE but not the key-share lock
    # that every foreign-key check on the turn takes, so spend rows can be written meanwhile.
    turn = (
        await db.execute(
            select(AiTurn.conversation_id, AiTurn.status)
            .where(AiTurn.id == turn_id)
            .with_for_update(key_share=True)
        )
    ).one_or_none()
    if turn is None or turn.conversation_id != conversation_id:
        raise ValueError("the turn is not one of this conversation's turns")
    if turn.status != "running":
        raise TurnFinished(str(turn_id))
    last_position = (
        await db.execute(
            select(func.max(AiMessage.position)).where(AiMessage.conversation_id == conversation_id)
        )
    ).scalar_one()
    first_position = 0 if last_position is None else last_position + 1
    # The IDs are made here, because each message is sealed for its own row. The default
    # serialization (ASCII only) is what the JSON column used to store.
    rows = []
    for offset, message in enumerate(messages):
        message_id = uuid4()
        rows.append(
            {
                "id": message_id,
                "tenant_id": conversation.tenant_id,
                "person_id": conversation.person_id,
                "conversation_id": conversation_id,
                "turn_id": turn_id,
                "position": first_position + offset,
                "role": message.role,
                "content_ciphertext": cipher.seal_text(
                    json.dumps(message.content), "ai_messages", "content_ciphertext", message_id
                ),
                "sources": [entry.to_json() for entry in message.sources] or None,
                "reported_outcomes": list(message.reported_outcomes) or None,
            }
        )
    await db.execute(insert(AiMessage), rows)


async def start_turn(
    db: AsyncSession, conversation: AiConversation, question: str, cipher: ConversationCipher
) -> AiTurn:
    """Add a `running` turn, with its question sealed. Raises TurnRunning if the conversation
    already has one."""
    cipher.require_conversation(conversation.id)
    turn_id = uuid4()
    turn = AiTurn(
        id=turn_id,
        tenant_id=conversation.tenant_id,
        person_id=conversation.person_id,
        conversation_id=conversation.id,
        question_ciphertext=cipher.seal_text(question, "ai_turns", "question_ciphertext", turn_id),
        status="running",
    )
    try:
        # A savepoint, so that the refused insert doesn't abort the caller's transaction.
        async with db.begin_nested():
            db.add(turn)
            await db.flush()
    except IntegrityError as error:
        if constraint_name(error) == ONE_RUNNING_TURN_INDEX:
            raise TurnRunning from error
        raise
    return turn


async def finish_turn(
    db: AsyncSession, turn_id: UUID, outcome: TurnOutcome, cipher: ConversationCipher
) -> None:
    """Record how the turn ended.

    A turn changes only while it is `running`, through this function and `recover_abandoned`; once
    it has ended, a trigger freezes it. The database allows these columns only. Any object loaded
    for the turn before this call is stale afterward.
    """
    # The type says no, but the type is not enforced: the trigger allows running to running, so
    # only this check stops a turn that never ends.
    if str(outcome.status) == "running":
        raise ValueError("a turn is finished with an ending status, not running")
    # Every field of the outcome is a column of the same name, so a new field can't be dropped.
    # The answer and the input summaries are the exceptions: they are sealed on the way in.
    fields = asdict(outcome)
    answer = fields.pop("answer_text")
    values: dict[str, Any] = {
        **fields,
        "answer_ciphertext": cipher.seal_text(answer, "ai_turns", "answer_ciphertext", turn_id),
        "tool_calls": cipher.seal_tool_calls(turn_id, fields["tool_calls"]),
        "ended_at": func.clock_timestamp(),
    }
    # The turn must be in the cipher's conversation: a mismatch finds no row and writes nothing.
    try:
        async with db.begin_nested():
            result = await db.execute(
                update(AiTurn)
                .where(AiTurn.id == turn_id, AiTurn.conversation_id == cipher.conversation_id)
                .values(**values)
                .execution_options(synchronize_session=False)
            )
    except DBAPIError as error:
        if has_sqlstate(error, FINISHED_TURN_SQLSTATE):
            raise TurnFinished(str(turn_id)) from error
        raise
    if cast("CursorResult[Any]", result).rowcount == 0:
        raise LookupError("no such turn")


async def write_console_row(db: AsyncSession, tenant_id: UUID, row: dict[str, Any]) -> bool:
    """Add a console row (`console_rows.build_console_row`) in the caller's transaction, in a
    savepoint of its own. Returns whether it was written.

    The console must never hurt the person: a row the database refuses (its check constraint, say)
    rolls back only the savepoint, is logged by the error's type alone (a message can hold what the
    row held), and is dropped. The turn still finishes and commits.

    A Core insert with no RETURNING: only HR can read a console row, and Postgres checks RETURNING
    against the read rule, which the person writing the row doesn't pass.
    """
    try:
        async with db.begin_nested():
            await db.execute(insert(AiConsoleTurn).values(id=uuid4(), tenant_id=tenant_id, **row))
    except Exception as error:
        logger.error("Writing the console row failed (%s)", error_name(error))
        return False
    return True


async def recover_abandoned(
    db: AsyncSession, conversation_id: UUID, *, older_than: timedelta = ABANDONED_AFTER
) -> list[UUID]:
    """Mark the conversation's `running` turns older than `older_than` as failed, so that the next
    question can start. A task that crashed or was restarted leaves its turn running for good.

    Returns the IDs of the turns it marked. The caller cancels their proposals in the same
    transaction (`proposals.recover_abandoned_turns` does both), after this update. Each turn also
    gets a redacted console row, in a savepoint, dated by when it was asked: it never stored a
    verdict, so nothing proves it was an ordinary turn. A failed row never fails the person's new
    question.
    """
    result = await db.execute(
        update(AiTurn)
        .where(
            AiTurn.conversation_id == conversation_id,
            AiTurn.status == "running",
            AiTurn.started_at < func.now() - literal(older_than, Interval()),
        )
        .values(status="failed", error_code="abandoned", ended_at=func.clock_timestamp())
        .returning(AiTurn.id, AiTurn.tenant_id, AiTurn.started_at)
        .execution_options(synchronize_session=False)
    )
    recovered = list(result.all())
    for _, tenant_id, started_at in recovered:
        # Dated by when the turn was asked, not by when it was recovered.
        row = build_abandoned_row(occurred_at=started_at, hq_timezone=ZoneInfo(HQ_TIMEZONE))
        await write_console_row(db, tenant_id, row)
    return [turn_id for turn_id, _, _ in recovered]


async def search_sources(db: AsyncSession, conversation_id: UUID) -> list[SourceEntry]:
    """Every `search_result` block the conversation has sent the model, in the order sent.

    A citation's `search_result_index` counts them across the whole conversation, so this list
    includes the messages of turns that failed or were stopped, whose trace was never filled in.
    """
    rows: Sequence[list[dict[str, Any]] | None] = (
        await db.scalars(
            select(AiMessage.sources)
            .where(AiMessage.conversation_id == conversation_id, AiMessage.sources.is_not(None))
            .order_by(AiMessage.position)
        )
    ).all()
    return [SourceEntry.from_json(entry) for sources in rows for entry in sources or []]


async def section_names(
    db: AsyncSession, conversation_id: UUID
) -> dict[str, tuple[str | None, str | None]]:
    """Each section the conversation's searches found, mapped to its (title, group name), either of
    which is None if no stored block of the section has it.

    One query, which unpacks `ai_messages.sources` in the database and selects only the distinct
    section ID, title and group, so the cited text and the rest of every stored block are never
    loaded or parsed. The page asks on every read of the conversation. Under the same row-level
    security as `search_sources`: only the person's own messages.
    """
    block = func.jsonb_array_elements(AiMessage.sources).table_valued("value").lateral("block")
    section_id = block.c.value.op("->>")("sectionId")
    title = block.c.value.op("->>")("title")
    group_name = block.c.value.op("->>")("groupName")
    rows = await db.execute(
        select(section_id, title, group_name)
        .select_from(AiMessage)
        .join(block, true())
        .where(AiMessage.conversation_id == conversation_id, AiMessage.sources.is_not(None))
        .distinct()
        .order_by(section_id, title, group_name)
    )
    # A block with no title or group (or a null one) never hides a section's real one, whichever
    # way the rows sort.
    names: dict[str, tuple[str | None, str | None]] = {}
    for found_id, found_title, found_group in rows:
        known_title, known_group = names.get(found_id, (None, None))
        names[found_id] = (known_title or found_title, known_group or found_group)
    return names


def is_abandoned(started_at: datetime, now: datetime) -> bool:
    """Whether a `running` turn started at `started_at` is given up on at `now`: strictly older
    than `ABANDONED_AFTER`. The same cut as SQL's, which `recover_abandoned` uses
    (`started_at < now - limit`) and `has_running_turn` is the complement of
    (`started_at >= now - limit` blocks), so a turn exactly at the limit is still running for all
    three. Pass the database's clock for `now`."""
    return now - started_at > ABANDONED_AFTER


def conversation_is_outdated(conversation: AiConversation) -> bool:
    """Whether the conversation is pinned to a prompt or tool set that is no longer current. It
    can't be continued: the history is append-only and the model's thinking is tied to the exact
    prompt and tools that produced it."""
    return (
        conversation.prompt_version != PROMPT_VERSION
        or conversation.toolset_version != TOOLSET_VERSION
    )


async def has_running_turn(db: AsyncSession, conversation_id: UUID) -> bool:
    """Whether the conversation has a turn in progress that the next question must wait for.

    A `running` turn older than `ABANDONED_AFTER` doesn't count: its task died, and starting the
    next turn marks it failed (`recover_abandoned`). A read only, so a refused request writes
    nothing.
    """
    found = await db.scalar(
        select(AiTurn.id)
        .where(
            AiTurn.conversation_id == conversation_id,
            AiTurn.status == "running",
            AiTurn.started_at >= func.now() - literal(ABANDONED_AFTER, Interval()),
        )
        .limit(1)
    )
    return found is not None


async def conversation_turns(db: AsyncSession, conversation_id: UUID) -> list[AiTurn]:
    """The conversation's turns, oldest first, for display."""
    return list(
        (
            await db.scalars(
                select(AiTurn)
                .where(AiTurn.conversation_id == conversation_id)
                .order_by(AiTurn.started_at, AiTurn.id)
            )
        ).all()
    )


async def turn_feedback(db: AsyncSession, conversation_id: UUID) -> dict[UUID, AiFeedback]:
    """The feedback given on the conversation's turns, by turn ID."""
    rows = await db.scalars(
        select(AiFeedback)
        .join(
            AiTurn,
            (AiTurn.tenant_id == AiFeedback.tenant_id) & (AiTurn.id == AiFeedback.turn_id),
        )
        .where(AiTurn.conversation_id == conversation_id)
    )
    return {row.turn_id: row for row in rows}


async def add_feedback(
    db: AsyncSession,
    actor: Actor,
    turn_id: UUID,
    *,
    helpful: bool,
    reason: str | None,
    keys: KeyProvider,
) -> None:
    """Record the actor's thumbs up or down on one of their completed turns.

    Raises `TurnNotFound` for a turn that is not the actor's (Postgres shows a turn only to its
    person, so another's is not found, the same as an ID that doesn't exist), `TurnNotCompleted`
    for one that did not finish, and `FeedbackGiven` if the turn has some already.
    """
    turn = await db.get(AiTurn, turn_id)
    if turn is None or turn.person_id != actor.person_id:
        raise TurnNotFound
    if turn.status != "completed":
        raise TurnNotCompleted
    if reason is not None and len(reason) > FEEDBACK_REASON_MAX_CHARACTERS:
        # The request body is checked against the same limit, so this is a bug if it is reached.
        raise ValueError("a reason is at most 500 characters")
    # Feedback is given once and never replaced, so the reason is sealed once, for its own row.
    feedback_id = uuid4()
    reason_ciphertext = None
    if reason is not None:
        conversation = await db.get(AiConversation, turn.conversation_id)
        if conversation is None:
            raise TurnNotFound
        reason_ciphertext = conversation_cipher(keys, conversation).seal_text(
            reason, "ai_feedback", "reason_ciphertext", feedback_id
        )
    try:
        # A savepoint, so that the refused insert doesn't abort the caller's transaction.
        async with db.begin_nested():
            db.add(
                AiFeedback(
                    id=feedback_id,
                    tenant_id=actor.tenant_id,
                    person_id=actor.person_id,
                    turn_id=turn.id,
                    helpful=helpful,
                    reason_ciphertext=reason_ciphertext,
                )
            )
            await db.flush()
    except IntegrityError as error:
        if constraint_name(error) == FEEDBACK_ONCE_CONSTRAINT:
            raise FeedbackGiven from error
        raise
