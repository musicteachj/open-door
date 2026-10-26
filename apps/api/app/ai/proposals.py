"""The proposal service: the model proposes, a person confirms, and the server runs the stored
payload once (ADR 0004, ADR 0013).

A proposal is a row in `ai_proposals`, bound to the person it was made for. Its status moves one
way, `pending` to one of four endings, and the database refuses every other change (migration
0009). This module is the only thing that changes one.

    pending --confirm--> executed | failed (re-validation refused it; the reason is kept)
    pending --dismiss--> canceled (reason: dismissed)
    pending --a newer card, or a turn that didn't finish--> canceled (replaced, turn-incomplete)
    pending --15 minutes--> expired (written the next time anyone acts on it)

Where each function runs:

- `create_proposal` and `cancel_turn_proposals` take their own short transaction, scoped to the
  person (as the AI tools and the budget do), because the assistant's turn isn't inside a request.
- `confirm` and `cancel` run in the route's transaction, so the proposal's ending, the time-off
  change, and the audit events commit or roll back together.

**Two clocks.** A proposal's own clock is the database's `now()`: `expires_at` is computed in SQL,
the expiry check reads `now()` in the same transaction, and the trigger that stamps `ended_at`
and refuses a late execute uses the same one. The caller's `now` goes only to the time-off
service, for "today" at the person's location.

**Lock order, everywhere.**

- `create_proposal`: the conversation (an advisory lock, so two proposals made at once in one
  conversation can't both see it empty), then the turn's row (`FOR NO KEY UPDATE`, as the history's
  writes take it, so a turn that ended, or is being failed by recovery, can't gain a card), then the
  conversation's pending proposal rows (the replace).
- `confirm` and `cancel`: the proposal's row (`SELECT ... FOR UPDATE`), then the person's balance
  lock (the time-off service takes it). Two confirms of one proposal wait at the row, and the second
  finds it ended. Taken the other way round, one confirm could hold the person's lock and wait for
  the row while another held the row and waited for the lock.
- In `confirm`, the turn's status is a plain read with no lock. Its safety rests on the caller:
  whatever ends a turn (`finish_turn`, `recover_abandoned`) must cancel that turn's proposals in the
  same transaction (`cancel_turn_proposals_in` takes the caller's session for that), so a confirm
  sees either both or neither. The turn's row is updated first and its proposals canceled second,
  in that order: the reverse deadlocks with a late `create_proposal`, which holds the turn's row
  and waits on the old card's row. As a backstop, `confirm` executes a card only when its turn is
  `completed`, and cancels it as `turn-incomplete` for any other ending.

The only thing a confirm takes from the client is a denial's note. It is checked here, goes to the
service, and is stored on the request alone: never in the proposal's payload, card, or outcome,
never in an audit event, and never in a line the model reads.
"""

import unicodedata
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal, Protocol, cast
from uuid import UUID

from sqlalchemy import and_, func, insert, literal_column, null, or_, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.sql import ColumnElement
from sqlalchemy.sql.dml import ReturningUpdate

from app.ai.conversations import TurnFinished, is_abandoned, recover_abandoned
from app.ai.proposal_cards import (
    CARD_TYPES,
    PAYLOAD_TYPES,
    CancelCard,
    Card,
    DecideCard,
    DecidePayload,
    Payload,
    ProposalAction,
    RequestCard,
    RequestPayload,
    stored_json,
)
from app.api.schemas import CamelModel
from app.db.errors import constraint_name, has_sqlstate
from app.db.models import AiProposal, AiTurn, TimeOffRequest
from app.db.tenancy import TenantContext, tenant_session
from app.domain.timeoff.evaluate import NewRequest, overlapping_days
from app.modules.audit.service import AuditAction, Via, record_event
from app.modules.timeoff import queries, service
from app.modules.timeoff.service import Refused
from app.modules.timeoff.texts import REFUSAL_TEXTS, refusal_text
from app.policy import Actor

type ProposalStatus = Literal["pending", "executed", "failed", "canceled", "expired"]
type CanceledReason = Literal["dismissed", "replaced", "turn-incomplete"]
type AutomaticReason = Literal["replaced", "turn-incomplete"]

# The two-integer advisory lock's namespace for a conversation's proposals. 4401 and 4402 are the AI
# budget's, and 4403 is a person's time-off balance.
CONVERSATION_PROPOSALS_NS = 4404
TAKE_CONVERSATION_LOCK = text(
    f"SELECT pg_advisory_xact_lock({CONVERSATION_PROPOSALS_NS},"
    " hashtext(CAST(:tenant_id AS text) || ':' || CAST(:conversation_id AS text)))"
)
PROPOSAL_LIFETIME: ColumnElement[Any] = literal_column("interval '15 minutes'")
# The SQLSTATE of migration 0009's triggers: a proposal ends once, and never executes after expiry.
PROPOSAL_TRIGGER_SQLSTATE = "OD003"
# For a stored failure code nobody recognizes: a fixed sentence, never a stored string.
UNKNOWN_FAILURE_TEXT = "This card could not be completed."
# One request per proposal: the unique index on time_off_requests (tenant_id, proposal_id).
ONE_REQUEST_PER_PROPOSAL = "uq_time_off_requests_tenant_id_proposal_id"
# The status of a conflict when the turn is still answering. The proposal itself stays pending.
TURN_RUNNING = "turn-running"
_TARGET = "ai_proposal"


class ProposalNotFound(Exception):  # noqa: N818
    """No such proposal for this person: someone else's and a missing one look the same."""


class Conflict(Exception):  # noqa: N818
    """The proposal can't be acted on, and `status` says why: the status it has now (`executed`,
    `failed`, `canceled`, `expired`), or `turn-running` for a proposal whose turn is still
    answering.

    `reason` says why a canceled proposal was canceled, so a card canceled because its answer never
    finished isn't described as dismissed.

    `wrote` is true when finding that out wrote something that must stay, such as marking the
    proposal expired. The route then answers 409 by returning the response, so its transaction
    commits, and not by raising, which would roll the write back.
    """

    def __init__(self, status: str, *, wrote: bool = False, reason: str | None = None) -> None:
        super().__init__(status)
        self.status = status
        self.wrote = wrote
        # For a canceled proposal, why: `dismissed`, `replaced`, or `turn-incomplete`.
        self.reason = reason


class InvalidNote(Exception):  # noqa: N818
    """The note can't be stored or isn't for a denial. The route answers 422."""


class _AlreadyEnded(Exception):  # noqa: N818
    """The proposal was not pending when the update ran."""


# ---------------------------------------------------------------------------------------------
# What a proposal looks like to a reader


class FailureOut(CamelModel):
    """Why a confirmed proposal didn't go through: the engine's or the service's code, and its one
    fixed sentence. `dates` is the days that clash, for `overlaps` only."""

    code: str
    text: str
    dates: list[date] | None = None


class ProposalOut(CamelModel):
    id: UUID
    action: ProposalAction
    status: ProposalStatus
    # Why a canceled proposal was canceled: the card says "You dismissed this." or "Replaced by a
    # newer card."
    canceled_reason: CanceledReason | None
    expires_at: datetime
    card: Card
    failure: FailureOut | None
    # True while the card's turn is still answering (and the card still pending): Confirm waits
    # until it finishes. Always false in a confirm's or a dismiss's own answer.
    turn_running: bool
    # A denial's note, for the person who wrote it, in the conversation read only (so the card can
    # say "Zara will see your note" after a reload). Null everywhere else: the stream event, the
    # confirm's and the dismiss's own answers, and every card that is not an executed denial. It
    # goes to the page and never to the model.
    denied_note: str | None = None


@dataclass(frozen=True, slots=True)
class ProposalRef:
    id: UUID
    action: str
    expires_at: datetime
    # Whether it canceled a card that was still pending in the conversation.
    replaced: bool = False


class ProposalRow(Protocol):
    """What reading a proposal needs. The ORM's `AiProposal` has all of it."""

    @property
    def status(self) -> str: ...

    @property
    def expires_at(self) -> datetime: ...

    @property
    def outcome(self) -> Mapping[str, Any] | None: ...


class ProposalData(ProposalRow, Protocol):
    @property
    def id(self) -> UUID: ...

    @property
    def action(self) -> str: ...

    @property
    def card(self) -> Mapping[str, Any]: ...


TurnState = Literal["completed", "answering", "incomplete"]


def turn_state_of(status: str, started_at: datetime, now: datetime) -> TurnState:
    """Whether a proposal's turn finished its answer, from the turn's stored status.

    `completed` is the only state a card may be confirmed in: its history holds the round that made
    the card. `answering` is a `running` turn still inside the time limit. Anything else is
    `incomplete`: a turn that failed, was stopped, or ended in crisis or an unavailable guard, one
    that recovery failed as abandoned, or one `running` past the limit (its task is presumed dead).
    The model would never know of such a card. `confirm` and the conversation read both use this,
    with the database's clock, so what the page shows is what a confirm would do.
    """
    if status == "completed":
        return "completed"
    if status == "running" and not is_abandoned(started_at, now):
        return "answering"
    return "incomplete"


def shown_ending(
    row: ProposalRow, now: datetime, turn_state: TurnState | None = None
) -> tuple[ProposalStatus, CanceledReason | None]:
    """The status and canceled reason a reader should see at `now`, matching what a confirm would
    do, with nothing written: a pending proposal past its `expires_at` is expired, and (when the
    turn's state is given) a pending one whose turn is `incomplete` is canceled as
    `turn-incomplete`. The expiry is judged first, as `confirm` does. Pass the database's clock."""
    if row.status == "pending":
        if now > row.expires_at:
            return "expired", None
        if turn_state == "incomplete":
            return "canceled", "turn-incomplete"
        return "pending", None
    reason = (row.outcome or {}).get("reason") if row.status == "canceled" else None
    return cast("ProposalStatus", row.status), cast("CanceledReason | None", reason)


def status_as_of(row: ProposalRow, now: datetime) -> ProposalStatus:
    """The status a reader should see at `now`: a pending proposal past its `expires_at` is
    expired, even though nothing has written that yet. Pass the database's clock."""
    return shown_ending(row, now)[0]


def proposal_out(
    row: ProposalData,
    now: datetime,
    turn_state: TurnState | None = None,
    denied_note: str | None = None,
) -> ProposalOut:
    """The proposal as the person sees it, with the status as of `now` (the database's clock).
    `turn_state` is the proposal's turn, for the conversation read; a confirm's own answer leaves
    it out. `denied_note` is the conversation read's `denial_notes` entry for this row."""
    status, reason = shown_ending(row, now, turn_state)
    outcome = row.outcome or {}
    failure = None
    if row.status == "failed":
        code = str(outcome.get("code", ""))
        raw_dates = outcome.get("dates")
        failure = FailureOut(
            code=code,
            # The fixed sentence for the code, never a stored string a reader could not vouch for.
            text=REFUSAL_TEXTS.get(code, UNKNOWN_FAILURE_TEXT),
            dates=None
            if raw_dates is None
            else [date.fromisoformat(str(item)) for item in raw_dates],
        )
    return ProposalOut(
        id=row.id,
        action=cast("ProposalAction", row.action),
        status=status,
        canceled_reason=reason,
        expires_at=row.expires_at,
        card=CARD_TYPES[row.action].model_validate(row.card),
        failure=failure,
        turn_running=status == "pending" and turn_state == "answering",
        denied_note=denied_note,
    )


async def denial_notes(
    db: AsyncSession, actor: Actor, rows: Sequence[ProposalData]
) -> dict[UUID, str]:
    """The note on each executed denial among `rows`, by proposal ID, for the conversation read.

    One query for all of them, and none when there is no executed denial. Read as the signed-in
    person: the request must be one this person decided, so a note is only ever handed back to the
    person who wrote it. A denial with no note, or a blank one, has no entry.
    """
    request_of: dict[UUID, UUID] = {}
    for row in rows:
        if row.status != "executed" or row.action != "timeoff.decide":
            continue
        if row.card.get("decision") != "deny":
            continue
        request_id = (row.outcome or {}).get("requestId")
        if isinstance(request_id, str):
            try:
                request_of[row.id] = UUID(request_id)
            except ValueError:
                continue
    if not request_of:
        return {}
    found = (
        await db.execute(
            select(TimeOffRequest.id, TimeOffRequest.decision_note).where(
                TimeOffRequest.id.in_(request_of.values()),
                TimeOffRequest.decided_by == actor.person_id,
                TimeOffRequest.status == "denied",
                TimeOffRequest.decision_note.is_not(None),
            )
        )
    ).all()
    notes = {request_id: note for request_id, note in found if note is not None and note.strip()}
    return {
        proposal_id: notes[request_id]
        for proposal_id, request_id in request_of.items()
        if request_id in notes
    }


async def conversation_proposals(
    db: AsyncSession, conversation_id: UUID, *, relevant_since: datetime | None = None
) -> list[AiProposal]:
    """Every proposal of the conversation, oldest first, in one query. Postgres shows a person
    only their own. With `relevant_since`, only those `outcomes_since` can use for that point:
    still pending, or ended or expiring after it."""
    query = select(AiProposal).where(AiProposal.conversation_id == conversation_id)
    if relevant_since is not None:
        query = query.where(
            or_(
                AiProposal.status == "pending",
                AiProposal.ended_at > relevant_since,
                AiProposal.expires_at > relevant_since,
            )
        )
    return list((await db.scalars(query.order_by(AiProposal.created_at, AiProposal.id))).all())


# ---------------------------------------------------------------------------------------------
# Reading and ending a row


@dataclass(frozen=True, slots=True)
class StoredProposal:
    id: UUID
    person_id: UUID
    conversation_id: UUID
    turn_id: UUID
    action: str
    payload: dict[str, Any]
    card: dict[str, Any]
    status: str
    expires_at: datetime
    outcome: dict[str, Any] | None


_COLUMNS = (
    AiProposal.id,
    AiProposal.person_id,
    AiProposal.conversation_id,
    AiProposal.turn_id,
    AiProposal.action,
    AiProposal.payload,
    AiProposal.card,
    AiProposal.status,
    AiProposal.expires_at,
    AiProposal.outcome,
)


async def _lock_proposal(db: AsyncSession, proposal_id: UUID) -> StoredProposal | None:
    """The proposal, with its row locked until the transaction ends. Postgres shows a person only
    their own proposals, so someone else's, and a missing one, are None."""
    row = (
        await db.execute(select(*_COLUMNS).where(AiProposal.id == proposal_id).with_for_update())
    ).one_or_none()
    return None if row is None else StoredProposal(*row)


async def _read_proposal(db: AsyncSession, proposal_id: UUID) -> StoredProposal:
    row = (await db.execute(select(*_COLUMNS).where(AiProposal.id == proposal_id))).one()
    return StoredProposal(*row)


async def _current_conflict(db: AsyncSession, proposal_id: UUID) -> Conflict:
    """The Conflict for a proposal that turned out to have ended: its status now, and for a
    canceled one the reason."""
    found = (
        await db.execute(
            select(AiProposal.status, AiProposal.outcome).where(AiProposal.id == proposal_id)
        )
    ).one_or_none()
    # Present for any proposal the lock found. A row that vanished means the sandbox is gone.
    if found is None:
        return Conflict("canceled")
    return Conflict(found.status, reason=_canceled_reason(found.status, found.outcome))


def _canceled_reason(status: str, outcome: Mapping[str, Any] | None) -> str | None:
    if status != "canceled" or not outcome:
        return None
    reason = outcome.get("reason")
    return reason if isinstance(reason, str) else None


async def _database_now(db: AsyncSession) -> datetime:
    """The transaction's `now()`: the clock the expiry check, `created_at`, `ended_at`, and the
    trigger that refuses a late execute all use."""
    return (await db.execute(select(func.now()))).scalar_one()


def _ending_update(
    proposal_id: UUID,
    status: str,
    outcome: Mapping[str, Any] | None,
    *,
    guarded: bool = True,
) -> ReturningUpdate[UUID]:
    """The update that ends a proposal. It changes a pending proposal only (`guarded`), so the
    update of an ended one affects no row. `ended_at` is the trigger's: it stamps the database's
    clock on any move out of pending."""
    statement = (
        update(AiProposal)
        .where(AiProposal.id == proposal_id)
        # SQL NULL, not the JSON value null, when there is no outcome.
        .values(status=status, outcome=null() if outcome is None else dict(outcome))
        .returning(AiProposal.id)
        .execution_options(synchronize_session=False)
    )
    if guarded:
        statement = statement.where(AiProposal.status == "pending")
    return statement


async def _end(
    db: AsyncSession, proposal_id: UUID, status: str, outcome: Mapping[str, Any] | None
) -> None:
    """End a pending proposal. Raises _AlreadyEnded if it wasn't pending: the update touched no
    row, or the trigger (SQLSTATE OD003) refused the move. The statement runs in a savepoint, so
    the caller's transaction stays usable either way."""
    try:
        async with db.begin_nested():
            ended = (
                await db.execute(_ending_update(proposal_id, status, outcome))
            ).scalar_one_or_none()
    except DBAPIError as error:
        if has_sqlstate(error, PROPOSAL_TRIGGER_SQLSTATE):
            raise _AlreadyEnded from error
        raise
    if ended is None:
        raise _AlreadyEnded


async def _end_or_conflict(
    db: AsyncSession, proposal_id: UUID, status: str, outcome: Mapping[str, Any] | None
) -> None:
    try:
        await _end(db, proposal_id, status, outcome)
    except _AlreadyEnded:
        raise await _current_conflict(db, proposal_id) from None


async def _audit(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    action: AuditAction,
    proposal_id: UUID,
    proposal_action: str,
    via: Via,
    status: str,
    extra: Mapping[str, object] | None = None,
) -> None:
    """A proposal's audit event: what it was, where it ended up, and the codes or IDs that say so.
    Never the card, the payload, or a person's words."""
    await record_event(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action=action,
        target_type=_TARGET,
        target_id=proposal_id,
        before=None if action == "proposal.created" else {"status": "pending"},
        after={"action": proposal_action, "status": status, **(extra or {})},
        via=via,
        proposal_id=proposal_id,
    )


# ---------------------------------------------------------------------------------------------
# Making a proposal, and ending one the person didn't touch


async def _end_pending(
    db: AsyncSession,
    ctx: TenantContext,
    where: ColumnElement[bool],
    reason: AutomaticReason,
) -> int:
    """End the person's pending proposals that match `where`, as the system. Returns how many it
    canceled (an expired one is not counted).

    One that has already run out its fifteen minutes is marked expired and not audited (nobody
    acted on it, and the card should still say it expired). The rest are canceled with `reason`,
    each with a `proposal.canceled` event from the system. A confirm holding a proposal's row makes
    this wait for it, and then skip it: the update re-reads, and an ended proposal isn't pending.
    """
    tenant_id, person_id = ctx.tenant_id, ctx.person_id
    if tenant_id is None or person_id is None:
        msg = "A proposal belongs to a person, so its transaction needs a tenant and a person"
        raise ValueError(msg)
    await db.execute(
        update(AiProposal)
        .where(where, AiProposal.status == "pending", AiProposal.expires_at < func.now())
        .values(status="expired", outcome=null())
        .execution_options(synchronize_session=False)
    )
    ended = (
        await db.execute(
            update(AiProposal)
            .where(where, AiProposal.status == "pending")
            .values(status="canceled", outcome={"reason": reason})
            .returning(AiProposal.id, AiProposal.action)
            .execution_options(synchronize_session=False)
        )
    ).all()
    for proposal_id, proposal_action in ended:
        await _audit(
            db,
            tenant_id=tenant_id,
            actor_id=person_id,
            action="proposal.canceled",
            proposal_id=proposal_id,
            proposal_action=proposal_action,
            via="system",
            status="canceled",
            extra={"reason": reason},
        )
    return len(ended)


async def create_proposal(
    engine: AsyncEngine,
    ctx: TenantContext,
    *,
    conversation_id: UUID,
    turn_id: UUID,
    action: ProposalAction,
    payload: Payload,
    card: RequestCard | DecideCard | CancelCard,
) -> ProposalRef:
    """Store a pending proposal for the person in `ctx`, and replace the one still pending in the
    conversation. Its own short transaction.

    `payload` and `card` are the typed models for `action` (a mismatch is a ValueError: a bug in
    the caller, never a model's mistake), stored as camelCase JSON. `expires_at` is computed in
    SQL, fifteen minutes after the database's own `now()`, which is also what the database stamps
    as `created_at`, so the check that holds one to the other can't fail on a Python clock.
    """
    tenant_id, person_id = ctx.tenant_id, ctx.person_id
    if tenant_id is None or person_id is None:
        msg = "A proposal is made for a person, so its context needs a tenant and a person"
        raise ValueError(msg)
    if action not in PAYLOAD_TYPES:
        msg = f"An unknown action: {action!r}"
        raise ValueError(msg)
    if not isinstance(payload, PAYLOAD_TYPES[action]):
        msg = f"The payload for {action} is a {PAYLOAD_TYPES[action].__name__}"
        raise ValueError(msg)
    if not isinstance(card, CARD_TYPES[action]):
        msg = f"The card for {action} is a {CARD_TYPES[action].__name__}"
        raise ValueError(msg)
    async with tenant_session(engine, ctx) as db:
        # Two proposals made at once in one conversation would both see "nothing pending" and both
        # store a pending card. A transaction-scoped advisory lock on the conversation serializes
        # them (the API's login may not lock the conversation's row: it can update none of its
        # columns), and a partial unique index (migration 0010) refuses it if this ever changes.
        await db.execute(
            TAKE_CONVERSATION_LOCK,
            {"tenant_id": str(tenant_id), "conversation_id": str(conversation_id)},
        )
        # Then the turn's row: a tool task that wakes after its turn ended (stopped, failed, or
        # recovered as abandoned) must store nothing, since the model never learns of the card.
        turn = (
            await db.execute(
                select(AiTurn.conversation_id, AiTurn.status, AiTurn.started_at)
                .where(AiTurn.id == turn_id)
                .with_for_update(key_share=True)
            )
        ).one_or_none()
        if turn is None or turn.conversation_id != conversation_id:
            msg = "the turn is not one of this conversation's turns"
            raise ValueError(msg)
        # `answering` only: a `running` turn past the limit is presumed dead, and its late tool
        # must not replace a valid earlier card (the database's clock, as the confirm reads it).
        if turn_state_of(turn.status, turn.started_at, await _database_now(db)) != "answering":
            raise TurnFinished(str(turn_id))
        replaced = await _end_pending(
            db, ctx, AiProposal.conversation_id == conversation_id, "replaced"
        )
        proposal_id, expires_at = (
            await db.execute(
                insert(AiProposal)
                .values(
                    tenant_id=tenant_id,
                    person_id=person_id,
                    conversation_id=conversation_id,
                    turn_id=turn_id,
                    action=action,
                    payload=stored_json(payload),
                    card=stored_json(card),
                    status="pending",
                    expires_at=func.now() + PROPOSAL_LIFETIME,
                )
                .returning(AiProposal.id, AiProposal.expires_at)
            )
        ).one()
        await _audit(
            db,
            tenant_id=tenant_id,
            actor_id=person_id,
            action="proposal.created",
            proposal_id=proposal_id,
            proposal_action=action,
            via="assistant",
            status="pending",
        )
    return ProposalRef(proposal_id, action, expires_at, replaced > 0)


async def cancel_turn_proposals(
    engine: AsyncEngine, ctx: TenantContext, turn_id: UUID, reason: AutomaticReason
) -> None:
    """Cancel the turn's proposals that are still pending (one that was confirmed, dismissed, or
    replaced is left as it is), each with a `proposal.canceled` event from the system. For a turn
    whose stored history doesn't hold the round that made them, so the model would never know of
    them. Its own short transaction."""
    async with tenant_session(engine, ctx) as db:
        await cancel_turn_proposals_in(db, ctx, turn_id, reason)


async def cancel_turn_proposals_in(
    db: AsyncSession, ctx: TenantContext, turn_id: UUID, reason: AutomaticReason
) -> None:
    """`cancel_turn_proposals` in the caller's transaction, for whatever ends a turn
    (`finish_turn`, `recover_abandoned`): the turn's ending and its proposals' cancellation commit
    together. Update the turn's row FIRST and call this second: the reverse order deadlocks with a
    late `create_proposal`, which holds the turn's row and waits on the old card's row."""
    await _end_pending(db, ctx, AiProposal.turn_id == turn_id, reason)


async def cancel_unreported_proposals_in(
    db: AsyncSession,
    ctx: TenantContext,
    turn_id: UUID,
    keep_ids: Collection[UUID],
    reason: AutomaticReason,
) -> None:
    """Cancel the turn's pending proposals whose ID is not in `keep_ids`, in the caller's
    transaction (same lock order as `cancel_turn_proposals_in`). For a turn that did complete: a
    card stored while its tool timed out or was canceled was never reported to the model as made,
    so the model's history does not hold it."""
    await _end_pending(
        db, ctx, and_(AiProposal.turn_id == turn_id, AiProposal.id.not_in(list(keep_ids))), reason
    )


async def recover_abandoned_turns(
    db: AsyncSession, ctx: TenantContext, conversation_id: UUID
) -> int:
    """`recover_abandoned`, and the cancellation of each recovered turn's pending proposals in the
    same transaction, after the turn's update (the order the lock rule needs). Returns how many
    turns it recovered."""
    turn_ids = await recover_abandoned(db, conversation_id)
    for turn_id in turn_ids:
        await cancel_turn_proposals_in(db, ctx, turn_id, "turn-incomplete")
    return len(turn_ids)


# ---------------------------------------------------------------------------------------------
# Confirm


def _clean_note(note: str | None) -> str | None:
    """The note trimmed, or None if it is blank. The same rule as the page's route (at most 300
    characters, no NUL); anything else is an InvalidNote the route maps to 422."""
    if note is None:
        return None
    try:
        return service.checked_note(note) or None
    except ValueError as error:
        raise InvalidNote(str(error)) from None


def _require_note_fits(row: StoredProposal, note: str | None) -> None:
    if note is None:
        return
    if row.action != "timeoff.decide" or row.payload.get("decision") != "deny":
        msg = "Only a denial takes a note."
        raise InvalidNote(msg)


async def _dispatch(
    db: AsyncSession,
    actor: Actor,
    row: StoredProposal,
    payload: Payload,
    note: str | None,
    now: datetime,
) -> service.Created | service.Decided | service.Canceled | Refused:
    """Run the STORED payload through the time-off service, as the assistant, from this proposal."""
    if isinstance(payload, RequestPayload):
        new = NewRequest(
            payload.type, payload.start_date, payload.end_date, payload.partial_minutes
        )
        return await service.create(db, actor, new, now, via="assistant", proposal_id=row.id)
    if isinstance(payload, DecidePayload):
        return await service.decide(
            db,
            actor,
            payload.request_id,
            payload.decision,
            note,
            now,
            via="assistant",
            proposal_id=row.id,
        )
    return await service.cancel(
        db, actor, payload.request_id, now, via="assistant", proposal_id=row.id
    )


async def _guarded_dispatch(
    db: AsyncSession,
    actor: Actor,
    row: StoredProposal,
    payload: Payload,
    note: str | None,
    now: datetime,
) -> service.Created | service.Decided | service.Canceled | Refused:
    """`_dispatch`, in a savepoint of its own. The time-off tables' trigger shares SQLSTATE OD003
    with the proposal's: if it refuses the service's update, the request has changed under the
    confirm, which is `status-changed`, not a 500. The savepoint undoes anything the service did."""
    try:
        async with db.begin_nested():
            return await _dispatch(db, actor, row, payload, note, now)
    except DBAPIError as error:
        if has_sqlstate(error, PROPOSAL_TRIGGER_SQLSTATE):
            return Refused("status-changed")
        raise


async def _failure(
    db: AsyncSession, actor: Actor, payload: Payload, refused: Refused
) -> dict[str, Any]:
    """The outcome of a proposal the service refused: its code, the fixed sentence for it, and for
    an overlap the days that clash. Never a note."""
    outcome: dict[str, Any] = {"code": refused.code, "text": refusal_text(refused.code)}
    if refused.code == "overlaps" and isinstance(payload, RequestPayload):
        stored = await queries.load_requests(db, actor.tenant_id, actor.person_id)
        days = overlapping_days(stored, payload.start_date, payload.end_date)
        outcome["dates"] = [day.isoformat() for day in days]
    return outcome


async def _turn_state(db: AsyncSession, turn_id: UUID, now: datetime) -> TurnState:
    """The proposal's turn, as `turn_state_of` reads it. A plain read, with no lock."""
    turn = (
        await db.execute(select(AiTurn.status, AiTurn.started_at).where(AiTurn.id == turn_id))
    ).one_or_none()
    if turn is None:
        return "incomplete"
    return turn_state_of(turn.status, turn.started_at, now)


async def confirm(
    db: AsyncSession, actor: Actor, proposal_id: UUID, note: str | None, now: datetime
) -> ProposalOut:
    """Confirm the actor's proposal: run its stored payload through the time-off service, once.

    In order: the row is locked (not the actor's, or missing, is ProposalNotFound); anything but
    pending is a Conflict with its status; past its expiry it is marked expired and refused; a turn
    still answering is `turn-running` with nothing written, and one abandoned cancels the proposal
    as `turn-incomplete`. Then the payload runs. The service refusing it ends the proposal `failed`
    with the reason, and the confirm itself still succeeded: it returns normally. Everything is in
    the caller's transaction.

    `note` is a denial's note, the only thing that comes from the client. InvalidNote if it can't be
    stored or isn't for a denial, with nothing written.
    """
    # The row first, then the person's lock (the service takes it): see the module's note.
    row = await _lock_proposal(db, proposal_id)
    if row is None or row.person_id != actor.person_id:
        raise ProposalNotFound
    if row.status != "pending":
        raise Conflict(row.status, reason=_canceled_reason(row.status, row.outcome))
    database_now = await _database_now(db)
    if database_now > row.expires_at:
        await _end_or_conflict(db, row.id, "expired", None)
        raise Conflict("expired", wrote=True)
    turn_state = await _turn_state(db, row.turn_id, database_now)
    if turn_state == "answering":
        raise Conflict(TURN_RUNNING)
    if turn_state == "incomplete":
        await _end_or_conflict(db, row.id, "canceled", {"reason": "turn-incomplete"})
        await _audit(
            db,
            tenant_id=actor.tenant_id,
            actor_id=actor.person_id,
            action="proposal.canceled",
            proposal_id=row.id,
            proposal_action=row.action,
            via="system",
            status="canceled",
            extra={"reason": "turn-incomplete"},
        )
        raise Conflict("canceled", wrote=True, reason="turn-incomplete")
    # After the 404 and the 409s, so an ended proposal answers 409 whatever the note says.
    note = _clean_note(note)
    _require_note_fits(row, note)

    payload = PAYLOAD_TYPES[row.action].model_validate(row.payload)
    try:
        # One savepoint around the service's writes and the proposal's ending, so a proposal that
        # turns out to have ended already leaves no request behind.
        async with db.begin_nested():
            result = await _guarded_dispatch(db, actor, row, payload, note, now)
            if isinstance(result, Refused):
                await _end(db, row.id, "failed", await _failure(db, actor, payload, result))
                await _audit(
                    db,
                    tenant_id=actor.tenant_id,
                    actor_id=actor.person_id,
                    action="proposal.failed",
                    proposal_id=row.id,
                    proposal_action=row.action,
                    via="ui",
                    status="failed",
                    extra={"code": result.code},
                )
            else:
                request_id = str(result.request_id)
                await _end(db, row.id, "executed", {"requestId": request_id})
                await _audit(
                    db,
                    tenant_id=actor.tenant_id,
                    actor_id=actor.person_id,
                    action="proposal.confirmed",
                    proposal_id=row.id,
                    proposal_action=row.action,
                    via="ui",
                    status="executed",
                    extra={"requestId": request_id},
                )
    except _AlreadyEnded:
        raise await _current_conflict(db, row.id) from None
    except IntegrityError as error:
        if constraint_name(error) == ONE_REQUEST_PER_PROPOSAL:
            raise await _current_conflict(db, row.id) from error
        raise
    return proposal_out(await _read_proposal(db, row.id), database_now)


async def cancel(db: AsyncSession, actor: Actor, proposal_id: UUID) -> ProposalOut:
    """The person dismissed the card. Works while the turn is still running, since a card that
    can't be confirmed yet can still be waved away. Past its expiry it is marked expired and
    refused, like a confirm."""
    row = await _lock_proposal(db, proposal_id)
    if row is None or row.person_id != actor.person_id:
        raise ProposalNotFound
    if row.status != "pending":
        raise Conflict(row.status, reason=_canceled_reason(row.status, row.outcome))
    database_now = await _database_now(db)
    if database_now > row.expires_at:
        await _end_or_conflict(db, row.id, "expired", None)
        raise Conflict("expired", wrote=True)
    await _end_or_conflict(db, row.id, "canceled", {"reason": "dismissed"})
    await _audit(
        db,
        tenant_id=actor.tenant_id,
        actor_id=actor.person_id,
        action="proposal.canceled",
        proposal_id=row.id,
        proposal_action=row.action,
        via="ui",
        status="canceled",
        extra={"reason": "dismissed"},
    )
    return proposal_out(await _read_proposal(db, row.id), database_now)


# ---------------------------------------------------------------------------------------------
# What the model learns afterward


class OutcomeRow(Protocol):
    """A stored proposal, as far as its outcome line needs it."""

    @property
    def action(self) -> str: ...

    @property
    def status(self) -> str: ...

    @property
    def expires_at(self) -> datetime: ...

    @property
    def ended_at(self) -> datetime | None: ...

    @property
    def outcome(self) -> Mapping[str, Any] | None: ...

    @property
    def card(self) -> Mapping[str, Any]: ...


OUTCOME_PREFIX = "Since the last message: "

_WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)

# Every sentence the model can be told is in this table or in `_outcome_line`: fixed words with a
# few slots (dates, a directory name). Nothing a person or a model wrote is ever put in a slot.
_FAILURE_REASONS = {
    "no-scheduled-days": "none of those days are scheduled workdays",
    "too-long": "the request was longer than one request may be",
    "out-of-range": "those dates can't be requested",
    "bad-partial": "that partial day can't be requested",
    "overlaps": "some of those days are already covered by another request",
    "not-enough": "there was not enough time available",
    "no-approver": "no manager is on file to approve it",
    "not-found": "the request could not be found",
    "not-allowed": "that action was not open to the person",
    "status-changed": "the request had changed in the meantime",
    "already-started": "the request had already started",
}
_CANCELED_ENDINGS = {
    "dismissed": "was dismissed, so nothing was changed",
    "replaced": "was replaced by a newer card, so nothing was changed",
    "turn-incomplete": "was canceled because the answer did not finish, so nothing was changed",
}
_APOSTROPHES = "'\N{RIGHT SINGLE QUOTATION MARK}"
MAX_NAME_CHARACTERS = 60
MAX_NAME_WORDS = 4


def _is_latin_letter(char: str, category: str) -> bool:
    return unicodedata.category(char) == category and "LATIN" in unicodedata.name(char, "")


def _plain_word(word: str) -> bool:
    """One word of a plain name: Latin letters (accents are fine), starting with an uppercase one,
    with at most one hyphen and one apostrophe, and a period only as the whole word "J."."""
    if "." in word:
        return len(word) == 2 and word[1] == "." and _is_latin_letter(word[0], "Lu")
    if not _is_latin_letter(word[0], "Lu"):
        return False
    if word.count("-") > 1 or sum(word.count(mark) for mark in _APOSTROPHES) > 1:
        return False
    return all(
        _is_latin_letter(char, "Lu") or _is_latin_letter(char, "Ll") or char in "-" + _APOSTROPHES
        for char in word
    )


def _plain_name(value: object) -> str | None:
    """A directory name that is safe to repeat. Only Latin-script words (accented letters are fine)
    that each start with an uppercase letter, with at most one hyphen and one apostrophe in a word,
    a period only after a single-letter initial, at most four words and 60 characters, on one
    line. Anything else is dropped, so a name can never carry a sentence, or another script's
    look-alike letters, into a model's context."""
    if not isinstance(value, str):
        return None
    name = value.strip()
    if not name or len(name) > MAX_NAME_CHARACTERS:
        return None
    words = name.split(" ")
    if len(words) > MAX_NAME_WORDS or not all(words) or not all(_plain_word(w) for w in words):
        return None
    return name


def _day_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        day = date.fromisoformat(value)
    except ValueError:
        return None
    return f"{_WEEKDAYS[day.weekday()]}, {_MONTHS[day.month - 1]} {day.day}"


def _dates_text(card: Mapping[str, Any]) -> str | None:
    first = _day_text(card.get("startDate"))
    last = _day_text(card.get("endDate"))
    if first is None or last is None:
        return None
    return first if first == last else f"{first} to {last}"


def _subject(row: OutcomeRow) -> str:
    card = row.card
    dates = _dates_text(card)
    if row.action == "timeoff.request":
        if card.get("type") == "sick":
            what = "the card to record sick time"
        else:
            what = "the card to book PTO"
        return what if dates is None else f"{what} on {dates}"
    if row.action == "timeoff.decide":
        requester = card.get("requester")
        name = _plain_name(requester.get("name")) if isinstance(requester, Mapping) else None
        verb = "deny" if card.get("decision") == "deny" else "approve"
        what = f"the card to {verb} the request from {name or 'the requester'}"
        return what if dates is None else f"{what} for {dates}"
    what = "the card to cancel the request"
    return what if dates is None else f"{what} for {dates}"


def _after_confirm(row: OutcomeRow) -> str:
    card = row.card
    if row.action == "timeoff.request":
        if card.get("type") == "sick":
            return "and the time was recorded"
        approver = card.get("approver")
        name = _plain_name(approver.get("name")) if isinstance(approver, Mapping) else None
        return f"and the request is waiting for {name or 'approval'}"
    if row.action == "timeoff.decide":
        return f"and the request was {'denied' if card.get('decision') == 'deny' else 'approved'}"
    return "and the request was canceled"


def _predicate(row: OutcomeRow, status: str) -> str:
    outcome = row.outcome or {}
    if status == "executed":
        return f"was confirmed, {_after_confirm(row)}"
    if status == "failed":
        reason = _FAILURE_REASONS.get(str(outcome.get("code")))
        base = "was confirmed but did not go through"
        return base if reason is None else f"{base}, because {reason}"
    if status == "canceled":
        return _CANCELED_ENDINGS.get(
            str(outcome.get("reason")), "was canceled, so nothing was changed"
        )
    return "expired, so nothing was changed"


def outcomes_since(rows: Sequence[OutcomeRow], since: datetime, now: datetime) -> tuple[str, ...]:
    """What happened to the person's cards since `since` (the last turn), for the next turn's
    per-turn context (ADR 0013): no lines when nothing changed, otherwise ONE line, "Since the last
    message:" and then one sentence for each proposal that ended, oldest first.

    Made from structured fields only: the action, the status, the outcome's reason or code, the
    card's dates, and the approver's or requester's directory name (and that only if it is a plain
    name). Wording is fixed in the tables above. The outcome's stored text, a note, any other key,
    and anything unexpected in a field never reach a line. A pending proposal past its expiry
    counts as expired, at its `expires_at`, as `status_as_of` shows it (pass the database's clock
    as `now`). Only changes after `since` and up to `now` count. Nothing is added for a proposal
    still pending.
    """
    changes: list[tuple[datetime, str]] = []
    for row in rows:
        status = status_as_of(row, now)
        if status == "pending":
            continue
        # An expired card changed when its time ran out, however late something wrote that down.
        changed_at = row.expires_at if status == "expired" or row.ended_at is None else row.ended_at
        # A change after `now` (a confirm that began after this turn did and committed before the
        # rows were read) is left for the next turn, which reports it once.
        if changed_at <= since or changed_at > now:
            continue
        changes.append((changed_at, f"{_subject(row)} {_predicate(row, status)}."))
    if not changes:
        return ()
    sentences = [sentence for _, sentence in sorted(changes, key=lambda change: change[0])]
    # The first follows the prefix as it is; each later one starts a sentence of its own.
    joined = " ".join([sentences[0], *(s[0].upper() + s[1:] for s in sentences[1:])])
    return (OUTCOME_PREFIX + joined,)
