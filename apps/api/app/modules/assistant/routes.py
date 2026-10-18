"""The assistant: the current conversation, a new one, feedback on an answer, and the turn stream.

Every route needs a session, and the routes that change something need the CSRF token and the
same-origin check like every other. Whose data is read comes only from the session (invariant 1):
Postgres shows a person only their own conversations and turns, so another person's IDs are a 404
here, never a 403, and an ID can't be probed.

**The stream's checks run before it opens**, each a problem response and not an event, in the
spec's order: the conversation (404), its pins (409 `conversation-outdated`), the question (422, and
422 `personal-data`), a turn already running (409 `turn-running`), and the budget (429). The
`running` check is a read, and the budget is checked before the turn's row is added, so a refused
request leaves nothing behind. A race between these checks and the start can still end inside the
stream, as an `error` event.
"""

import asyncio
import contextlib
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

import anyio
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.ai.admission import (
    HISTORY_OFFER_TOKENS,
    HISTORY_REFUSE_TOKENS,
    SMALLEST_QUESTION,
    history_tokens,
    room_needed_usd,
    scope_without_room,
    short_scopes,
)
from app.ai.budget import Caps, budget_state
from app.ai.context import ActorView, actor_view
from app.ai.conversations import (
    CURRENT_PINS,
    FeedbackGiven,
    TurnNotCompleted,
    TurnNotFound,
    TurnRunning,
    add_feedback,
    conversation_is_outdated,
    conversation_turns,
    create_conversation,
    current_conversation,
    has_running_turn,
    model_history,
    section_names,
    turn_feedback,
)
from app.ai.embeddings import Embedder, for_sandbox
from app.ai.fixed_texts import (
    BUDGET_DAILY_TEXT,
    BUDGET_SANDBOX_TEXT,
    ERROR_TEXTS,
    PERSONAL_DATA_TEXT,
    STILL_ANSWERING_TEXT,
    hr_contact,
)
from app.ai.personal_data import kind_of_personal_data
from app.ai.transport import Transport
from app.ai.turn import (
    MAX_QUESTION_CHARACTERS,
    ConversationNotFound,
    ConversationOutdated,
    TurnDeps,
    start_turn_run,
)
from app.api.deps import get_app_settings, get_embedder, get_engine, get_streams, get_transport
from app.api.problems import problem_responses
from app.core.config import Settings
from app.core.problems import ProblemError
from app.db.models import AiConversation, HandbookVersion
from app.db.tenancy import TenantContext, set_is_hr, tenant_session
from app.domain.handbook.applicability import Asker
from app.modules.assistant.display import hr_contact_out, needs_hr_contact, shown, turn_out
from app.modules.assistant.schemas import (
    AssistantTextsOut,
    BudgetBannerOut,
    BudgetOut,
    ConversationOut,
    FeedbackGivenOut,
    FeedbackIn,
    TurnIn,
    is_storable,
)
from app.modules.assistant.sse import StreamTracker, TurnResponse, TurnStream
from app.modules.handbook.asker import load_asker
from app.modules.handbook.search import pinned_version_id
from app.modules.identity.deps import (
    Caller,
    CallerDep,
    SignedIn,
    SignedInDep,
    current_session,
)
from app.modules.people.queries import get_me

router = APIRouter(prefix="/assistant", tags=["assistant"])

NO_CONVERSATION = "No such conversation."
NO_TURN = "No such turn."
NO_VERSION = "This sandbox has no handbook version."


def personal_data_refusal() -> ProblemError:
    return ProblemError(status.HTTP_422_UNPROCESSABLE_CONTENT, "personal-data", PERSONAL_DATA_TEXT)


CURRENT_ERRORS = problem_responses(status.HTTP_401_UNAUTHORIZED)
CREATE_ERRORS = problem_responses(status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
FEEDBACK_ERRORS = problem_responses(
    status.HTTP_401_UNAUTHORIZED,
    status.HTTP_403_FORBIDDEN,
    status.HTTP_404_NOT_FOUND,
    status.HTTP_409_CONFLICT,
    status.HTTP_422_UNPROCESSABLE_CONTENT,
)
TURN_ERRORS = problem_responses(
    status.HTTP_401_UNAUTHORIZED,
    status.HTTP_403_FORBIDDEN,
    status.HTTP_404_NOT_FOUND,
    status.HTTP_409_CONFLICT,
    status.HTTP_422_UNPROCESSABLE_CONTENT,
    status.HTTP_429_TOO_MANY_REQUESTS,
)


@dataclass(frozen=True)
class AskerContext:
    """What a turn, and the room it needs, are worked out from. Loaded from the server session."""

    actor_view: ActorView
    asker: Asker
    version_id: UUID
    handbook_label: str


async def pinned_version(db: AsyncSession) -> tuple[UUID, str] | None:
    """The sandbox's pinned handbook version and its label, or None if it has none."""
    version_id = await pinned_version_id(db)
    if version_id is None:
        return None
    label = await db.scalar(select(HandbookVersion.label).where(HandbookVersion.id == version_id))
    return None if label is None else (version_id, label)


async def load_asker_context(db: AsyncSession, signed_in: SignedIn | Caller) -> AskerContext:
    """The asker's view for the model, their handbook asker, and the pinned handbook version."""
    pinned = await pinned_version(db)
    if pinned is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NO_VERSION)
    version_id, label = pinned
    me = await get_me(db, signed_in.actor, signed_in.session.expires_at)
    return AskerContext(
        actor_view=actor_view(me),
        asker=await load_asker(db, signed_in.actor),
        version_id=version_id,
        handbook_label=label,
    )


def budget_banner(*, sandbox_reached: bool, daily_reached: bool) -> BudgetBannerOut | None:
    """The fixed text for the cap that stops the person. The day's wins when both are reached:
    a new sandbox would not help then, and the sandbox text's only offer is a new one. The POST's
    429 (`scope_without_room`) names the sandbox first, but no 429 shows beside this banner: with
    either cap reached the composer is disabled, and a new sandbox doesn't lift the daily cap."""
    if daily_reached:
        return BudgetBannerOut(kind="daily", message=BUDGET_DAILY_TEXT)
    if sandbox_reached:
        return BudgetBannerOut(kind="sandbox", message=BUDGET_SANDBOX_TEXT)
    return None


async def budget_out(
    db: AsyncSession,
    signed_in: SignedIn,
    caps: Caps,
    now: datetime,
    *,
    model: str,
    guard_model: str,
    effort: str,
    history: list[dict[str, Any]],
) -> BudgetOut:
    """Whether the person's next question has room, and the banner for the cap that stops it. One
    function builds it for the conversation read and for the budget route, so they never disagree:
    the route only has the pins and history of a conversation that is not there yet."""
    state = await budget_state(db, caps)
    view = actor_view(await get_me(db, signed_in.actor, signed_in.session.expires_at))
    # The handbook label is in the context the estimate sizes, a few characters of thousands. A
    # sandbox with no pinned version has none, and the estimate is made without it: the banner is
    # a size estimate, and the question itself is refused (404) when a turn needs the version.
    pinned = await pinned_version(db)
    label = "" if pinned is None else pinned[1]
    needed = room_needed_usd(
        model=model,
        guard_model=guard_model,
        effort=effort,
        history=history,
        question=SMALLEST_QUESTION,
        actor_view=view,
        handbook_label=label or "",
        now=now,
    )
    sandbox_short, daily_short = short_scopes(state, needed)
    return BudgetOut(
        sandbox_reached=sandbox_short,
        daily_reached=daily_short,
        sandbox_remaining_cents=max(0, int(state.sandbox_remaining_usd * 100)),
        banner=budget_banner(sandbox_reached=sandbox_short, daily_reached=daily_short),
    )


async def conversation_out(
    db: AsyncSession,
    signed_in: SignedIn,
    conversation: AiConversation,
    caps: Caps,
    now: datetime,
) -> ConversationOut:
    turns = await conversation_turns(db, conversation.id)
    feedback = await turn_feedback(db, conversation.id)
    # The database's clock decides what is abandoned, as for the POST.
    database_now = (await db.execute(select(func.now()))).scalar_one()
    shows = [shown(t, database_now) for t in turns]
    contacts = await hr_contact(db) if needs_hr_contact(shows) else []
    history = await model_history(db, conversation.id)
    tokens = history_tokens(history)
    budget = await budget_out(
        db,
        signed_in,
        caps,
        now,
        model=conversation.model,
        guard_model=conversation.guard_model,
        effort=conversation.effort,
        history=history,
    )
    # One lookup for the whole conversation, not one per turn.
    names = await section_names(db, conversation.id)
    return ConversationOut(
        id=conversation.id,
        created_at=conversation.created_at,
        turns=[
            turn_out(t, s, feedback.get(t.id), contacts, names)
            for t, s in zip(turns, shows, strict=True)
        ],
        hr_contacts=hr_contact_out(contacts),
        budget=budget,
        long_history=tokens > HISTORY_OFFER_TOKENS,
        history_too_long=tokens > HISTORY_REFUSE_TOKENS,
        outdated=conversation_is_outdated(conversation),
    )


@router.get(
    "/conversations/current",
    operation_id="getCurrentConversation",
    summary="The signed-in person's newest conversation with its turns, or null",
    response_model=ConversationOut | None,
    responses=CURRENT_ERRORS,
)
async def get_current_conversation(
    signed_in: SignedInDep, settings: Annotated[Settings, Depends(get_app_settings)]
) -> ConversationOut | None:
    conversation = await current_conversation(signed_in.db, signed_in.actor)
    if conversation is None:
        return None
    return await conversation_out(
        signed_in.db, signed_in, conversation, Caps.from_settings(settings), datetime.now(UTC)
    )


@router.get(
    "/budget",
    operation_id="getAssistantBudget",
    summary="Whether the next question has room, before there is a conversation to ask",
    response_model=BudgetOut,
    responses=CURRENT_ERRORS,
)
async def get_assistant_budget(
    signed_in: SignedInDep, settings: Annotated[Settings, Depends(get_app_settings)]
) -> BudgetOut:
    """The same `BudgetOut` the conversation carries, for a person with none yet: the home needs
    the banner before the first question. With a conversation it is that conversation's, built by
    the same function."""
    db = signed_in.db
    conversation = await current_conversation(db, signed_in.actor)
    # The pins and history the next question would have: the conversation's own, or today's pins
    # and an empty history for a person who has none yet.
    pins = CURRENT_PINS if conversation is None else conversation
    history = [] if conversation is None else await model_history(db, conversation.id)
    return await budget_out(
        db,
        signed_in,
        Caps.from_settings(settings),
        datetime.now(UTC),
        model=pins.model,
        guard_model=pins.guard_model,
        effort=pins.effort,
        history=history,
    )


@router.get(
    "/texts",
    operation_id="getAssistantTexts",
    summary="The fixed refusals the composer shows before a request is sent",
    response_model=AssistantTextsOut,
    responses=CURRENT_ERRORS,
    dependencies=[Depends(current_session)],
)
async def get_assistant_texts() -> AssistantTextsOut:
    """Needs a session like every assistant route, but reads nothing of the tenant's, so it takes
    no transaction: only the short session lookup."""
    return AssistantTextsOut(personal_data=PERSONAL_DATA_TEXT, still_answering=STILL_ANSWERING_TEXT)


@router.post(
    "/conversations",
    operation_id="createConversation",
    summary="Start a new conversation, pinned to today's model, prompt, and tool set",
    status_code=status.HTTP_201_CREATED,
    response_model=ConversationOut,
    responses=CREATE_ERRORS,
)
async def create_new_conversation(
    signed_in: SignedInDep, settings: Annotated[Settings, Depends(get_app_settings)]
) -> ConversationOut:
    conversation = await create_conversation(signed_in.db, signed_in.actor, CURRENT_PINS)
    # The server fills these in at insert; read them back for the response.
    await signed_in.db.refresh(conversation)
    return await conversation_out(
        signed_in.db, signed_in, conversation, Caps.from_settings(settings), datetime.now(UTC)
    )


@router.post(
    "/turns/{turn_id}/feedback",
    operation_id="giveFeedback",
    summary="Thumbs up or down on one of the person's own completed answers, once",
    status_code=status.HTTP_201_CREATED,
    response_model=FeedbackGivenOut,
    responses=FEEDBACK_ERRORS,
)
async def give_feedback(
    turn_id: UUID, body: FeedbackIn, signed_in: SignedInDep
) -> FeedbackGivenOut:
    reason = body.reason or None
    if reason is not None and kind_of_personal_data(reason) is not None:
        raise personal_data_refusal()
    try:
        await add_feedback(
            signed_in.db, signed_in.actor, turn_id, helpful=body.helpful, reason=reason
        )
    except TurnNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NO_TURN) from None
    except TurnNotCompleted:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Feedback is for answers that finished."
        ) from None
    except FeedbackGiven:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "You've already given feedback on this answer."
        ) from None
    return FeedbackGivenOut(turn_id=turn_id, helpful=body.helpful, reason=reason)


# --- The turn stream ------------------------------------------------------------------------

SSE_RESPONSE: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "The turn as server-sent events: `turn.started`, `status`, `text.delta`,"
        " `text.retracted`, `citation`, `tool.started`, `tool.finished`, `escalation`, `error`,"
        " and `turn.completed`, with `: keep-alive` comments between them.",
        "content": {"text/event-stream": {"schema": {"type": "string"}}},
    }
}


@dataclass(frozen=True)
class Admitted:
    """A question that passed every check, with what the turn is started from."""

    conversation: AiConversation
    question: str
    asker: AskerContext
    caps: Caps


async def admit_question(
    engine: AsyncEngine,
    caller: Caller,
    conversation_id: UUID,
    raw_question: str,
    settings: Settings,
    now: datetime,
) -> Admitted:
    """Run the checks in the spec's order, each a problem response, in a short transaction of its
    own. The transaction ends before this returns, so the request holds no database connection
    while the turn takes its own (see `Caller`)."""
    actor = caller.actor
    context = TenantContext(actor.tenant_id, actor.person_id)
    async with tenant_session(engine, context) as db:
        await set_is_hr(db, actor.is_hr_admin)

        # 2. The conversation is the person's (Postgres shows no other), and is current.
        conversation = await db.get(AiConversation, conversation_id)
        if conversation is None or conversation.person_id != actor.person_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, NO_CONVERSATION)
        if conversation_is_outdated(conversation):
            raise outdated_refusal()
        history = await model_history(db, conversation.id)
        if history_tokens(history) > HISTORY_REFUSE_TOKENS:
            # Too long to send again. The page offers a new conversation (the GET's
            # `historyTooLong` says so too), and tells it apart from an outdated one.
            raise history_too_long_refusal()

        # 3. The question.
        question = raw_question.strip()
        if not 1 <= len(question) <= MAX_QUESTION_CHARACTERS or not is_storable(question):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"A question is 1 to {MAX_QUESTION_CHARACTERS:,} characters.",
            )
        if kind_of_personal_data(question) is not None:
            # Never echoed back or logged, only that it looked like a number we must not take.
            raise personal_data_refusal()

        # 4. One turn at a time. A read, so a refusal writes nothing.
        if await has_running_turn(db, conversation.id):
            raise still_answering_refusal()

        # 5. Budgets, before the turn's row is added: a refusal leaves no `running` turn behind.
        asker = await load_asker_context(db, caller)
        caps = Caps.from_settings(settings)
        needed = room_needed_usd(
            model=conversation.model,
            guard_model=conversation.guard_model,
            effort=conversation.effort,
            history=history,
            question=question,
            actor_view=asker.actor_view,
            handbook_label=asker.handbook_label,
            now=now,
        )
        scope = scope_without_room(await budget_state(db, caps), needed)
        if scope is not None:
            code = f"budget-{scope}"
            raise ProblemError(status.HTTP_429_TOO_MANY_REQUESTS, code, ERROR_TEXTS[code])
    return Admitted(conversation, question, asker, caps)


def outdated_refusal() -> ProblemError:
    return ProblemError(
        status.HTTP_409_CONFLICT,
        "conversation-outdated",
        "This conversation can't continue. Start a new one.",
    )


def history_too_long_refusal() -> ProblemError:
    return ProblemError(
        status.HTTP_409_CONFLICT,
        "history-too-long",
        "This conversation has grown too long to continue. Start a new one.",
    )


def still_answering_refusal() -> ProblemError:
    return ProblemError(status.HTTP_409_CONFLICT, "turn-running", STILL_ANSWERING_TEXT)


@dataclass
class StreamSlot:
    """Holds the stream a request made, so that the request's end can close it whether or not the
    response was ever sent."""

    stream: TurnStream | None = None


async def stream_slot() -> AsyncIterator[StreamSlot]:
    slot = StreamSlot()
    try:
        yield slot
    finally:
        # Idempotent: a stream whose response ran has closed itself. One whose response never
        # started (a failure or a cancel between the turn's start and the first byte) is stopped
        # here, which saves its turn and frees the conversation.
        if slot.stream is not None:
            await slot.stream.aclose()


# Request scope: the teardown runs after the response, not before it as `SignedInDep`'s does.
StreamSlotDep = Annotated[StreamSlot, Depends(stream_slot, scope="request")]


@router.post(
    "/conversations/{conversation_id}/turns",
    operation_id="startTurn",
    summary="Ask a question and stream the turn as server-sent events",
    response_model=None,
    response_class=StreamingResponse,
    responses={**SSE_RESPONSE, **TURN_ERRORS},
)
async def start_turn_stream(
    conversation_id: UUID,
    body: TurnIn,
    caller: CallerDep,
    slot: StreamSlotDep,
    engine: Annotated[AsyncEngine, Depends(get_engine)],
    transport: Annotated[Transport, Depends(get_transport)],
    embedder: Annotated[Embedder | None, Depends(get_embedder)],
    settings: Annotated[Settings, Depends(get_app_settings)],
    streams: Annotated[StreamTracker, Depends(get_streams)],
) -> TurnResponse:
    actor = caller.actor
    now = datetime.now(UTC)
    admitted = await admit_question(engine, caller, conversation_id, body.question, settings, now)
    asker = admitted.asker
    deps = TurnDeps(
        engine=engine,
        transport=transport,
        embedder=for_sandbox(embedder, actor.tenant_id),
        actor=actor,
        tenant_ctx=TenantContext(actor.tenant_id, actor.person_id),
        caps=admitted.caps,
        actor_view=asker.actor_view,
        asker=asker.asker,
        version_id=asker.version_id,
        handbook_label=asker.handbook_label,
    )

    async def start() -> TurnStream:
        # Counted from the start, so the shutdown's drain waits for a turn still being added.
        streams.opened()
        try:
            run = await start_turn_run(
                deps, conversation=admitted.conversation, question=admitted.question, now=now
            )
            started = TurnStream(
                run,
                heartbeat_seconds=settings.ai_heartbeat_seconds,
                tracker=streams,
                counted=True,
            )
        except BaseException as error:
            streams.closed()  # No stream took over the count.
            if isinstance(error, TurnRunning):
                raise still_answering_refusal() from None  # Another request won the race.
            if isinstance(error, ConversationOutdated):
                raise outdated_refusal() from None
            if isinstance(error, ConversationNotFound):
                raise HTTPException(status.HTTP_404_NOT_FOUND, NO_CONVERSATION) from None
            raise
        slot.stream = started
        return started

    # From the turn's row being added to the stream being in the slot, no cancellation may land:
    # the row would be `running` with nothing to end it. A cancel of this task (uvicorn does that
    # when its graceful-shutdown time runs out) is a plain `task.cancel()`, which an anyio shield
    # does not block. So the start runs as a task of its own, shielded, and a cancel waits for it
    # to finish; the slot then holds the stream, and the request's teardown stops it.
    starting = asyncio.ensure_future(start())
    try:
        stream = await asyncio.shield(starting)
    except asyncio.CancelledError:
        with anyio.CancelScope(shield=True):
            await asyncio.wait({starting})
        with contextlib.suppress(asyncio.CancelledError):
            starting.exception()  # Taken, so asyncio does not warn that nobody retrieved it.
        raise
    return TurnResponse(stream)
