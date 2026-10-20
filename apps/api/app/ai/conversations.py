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

from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal, Self, cast
from uuid import UUID

from sqlalchemy import CursorResult, Interval, func, insert, literal, select, true, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.pricing import HAIKU
from app.ai.prompts.versions import PROMPT_VERSION, TOOLSET_VERSION
from app.ai.transport import count_search_results
from app.db.errors import constraint_name, has_sqlstate
from app.db.models import AiConversation, AiFeedback, AiMessage, AiTurn
from app.policy import Actor

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
    again. `sources` has one entry per `search_result` block in it, in block order."""

    role: Literal["user", "assistant", "system"]
    content: list[dict[str, Any]]
    sources: tuple[SourceEntry, ...] = ()


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


async def create_conversation(db: AsyncSession, actor: Actor, pins: Pins) -> AiConversation:
    conversation = AiConversation(
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


async def model_history(db: AsyncSession, conversation_id: UUID) -> list[dict[str, Any]]:
    """The messages as the Messages API takes them, in order and exactly as stored.

    Postgres keeps `content` as the text it was given (a `json` column), and SQLAlchemy parses it
    without reordering, so a thinking block comes back with the bytes its signature covers.
    """
    rows = await db.execute(
        select(AiMessage.role, AiMessage.content)
        .where(AiMessage.conversation_id == conversation_id)
        .order_by(AiMessage.position)
    )
    return [{"role": role, "content": content} for role, content in rows.all()]


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
) -> None:
    """Add messages after the conversation's last one, with their search sources, in one INSERT.

    The tenant and person come from the conversation row, which row-level security shows only to
    its owner. Only one turn at a time runs in a conversation, so positions can't race.
    """
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
    await db.execute(
        insert(AiMessage),
        [
            {
                "tenant_id": conversation.tenant_id,
                "person_id": conversation.person_id,
                "conversation_id": conversation_id,
                "turn_id": turn_id,
                "position": first_position + offset,
                "role": message.role,
                "content": message.content,
                "sources": [entry.to_json() for entry in message.sources] or None,
            }
            for offset, message in enumerate(messages)
        ],
    )


async def start_turn(db: AsyncSession, conversation: AiConversation, question: str) -> AiTurn:
    """Add a `running` turn. Raises TurnRunning if the conversation already has one."""
    turn = AiTurn(
        tenant_id=conversation.tenant_id,
        person_id=conversation.person_id,
        conversation_id=conversation.id,
        question=question,
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


async def finish_turn(db: AsyncSession, turn_id: UUID, outcome: TurnOutcome) -> None:
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
    values: dict[str, Any] = {**asdict(outcome), "ended_at": func.clock_timestamp()}
    try:
        async with db.begin_nested():
            result = await db.execute(
                update(AiTurn)
                .where(AiTurn.id == turn_id)
                .values(**values)
                .execution_options(synchronize_session=False)
            )
    except DBAPIError as error:
        if has_sqlstate(error, FINISHED_TURN_SQLSTATE):
            raise TurnFinished(str(turn_id)) from error
        raise
    if cast("CursorResult[Any]", result).rowcount == 0:
        raise LookupError("no such turn")


async def recover_abandoned(
    db: AsyncSession, conversation_id: UUID, *, older_than: timedelta = ABANDONED_AFTER
) -> int:
    """Mark the conversation's `running` turns older than `older_than` as failed, so that the next
    question can start. A task that crashed or was restarted leaves its turn running for good.

    Returns how many it marked.
    """
    result = await db.execute(
        update(AiTurn)
        .where(
            AiTurn.conversation_id == conversation_id,
            AiTurn.status == "running",
            AiTurn.started_at < func.now() - literal(older_than, Interval()),
        )
        .values(status="failed", error_code="abandoned", ended_at=func.clock_timestamp())
        .execution_options(synchronize_session=False)
    )
    return cast("CursorResult[Any]", result).rowcount


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
    db: AsyncSession, actor: Actor, turn_id: UUID, *, helpful: bool, reason: str | None
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
    try:
        # A savepoint, so that the refused insert doesn't abort the caller's transaction.
        async with db.begin_nested():
            db.add(
                AiFeedback(
                    tenant_id=actor.tenant_id,
                    person_id=actor.person_id,
                    turn_id=turn.id,
                    helpful=helpful,
                    reason=reason,
                )
            )
            await db.flush()
    except IntegrityError as error:
        if constraint_name(error) == FEEDBACK_ONCE_CONSTRAINT:
            raise FeedbackGiven from error
        raise
