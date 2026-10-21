"""The time-off service: every write to a person's requests goes through here, whether it comes
from a page or from a proposal a person confirmed.

A write:

1. takes the person's advisory lock (`queries.lock_person`) before it reads anything of theirs,
   so two writes for one person run one after the other and the second sees the first;
2. reads the person, their opening, their requests, and their location's holidays, and works out
   "today" at that location from `now` (passed in, never read from a clock here);
3. re-checks the policy and the request's status, now that nothing else can change them;
4. writes the change and its audit event in the same transaction.

The engine (`app.domain.timeoff`) counts and decides whether a request fits. The policy layer
(`app.policy`) decides who may act. This module only gathers inputs and writes the outcome.

A refusal is a value, `Refused`, never an exception. A caller that would have to explain a
problem to a person (a route, a confirm) maps its code. `not-found` is for a request or person the
actor can't read, and the routes answer it with a 404, never a 403, so a request that doesn't
exist and one the actor may not see look the same.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import insert, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.errors import constraint_name
from app.db.models import TimeOffRequest
from app.domain.timeoff.evaluate import Evaluation, NewRequest, evaluate
from app.domain.timeoff.pto import PtoBalance, pto_balance
from app.domain.timeoff.rules import Rule
from app.domain.timeoff.sick import SickYear, sick_years
from app.domain.timeoff.today import today_at
from app.modules.audit.service import record_event
from app.modules.timeoff import queries
from app.policy import Action, Actor, PersonResource, TimeOffRequestResource, can

# The name of the exclusion constraint that refuses two open requests for the same days. Matched by
# name, never by the message's text.
NO_OVERLAP_CONSTRAINT = "ex_time_off_requests_no_overlap"
MAX_NOTE_CHARACTERS = 300

type Via = Literal["ui", "assistant"]
type Decision = Literal["approve", "deny"]

_NOT_FOUND = "not-found"
_NOT_ALLOWED = "not-allowed"
_STATUS_CHANGED = "status-changed"
_ALREADY_STARTED = "already-started"
_OVERLAPS = "overlaps"


@dataclass(frozen=True, slots=True)
class RuleRef:
    """A handbook section an engine rule rests on, resolved for display: a source chip."""

    section_id: str
    rule: str
    title: str
    deep_link: str


@dataclass(frozen=True, slots=True)
class Balances:
    person_id: UUID
    # The date at the person's location. A manager reading a report's balances gets the report's.
    today: date
    pto: PtoBalance
    sick: tuple[SickYear, ...]
    rules: tuple[RuleRef, ...]


@dataclass(frozen=True, slots=True)
class Refused:
    """Why nothing was done.

    `code` is one of the engine's problem codes (`no-scheduled-days`, `too-long`, `out-of-range`,
    `bad-partial`, `overlaps`, `not-enough`) for a request that can't be made, or `not-found`,
    `not-allowed`, `status-changed`, or `already-started`. `evaluation` is the engine's answer,
    when there is one.
    """

    code: str
    evaluation: Evaluation | None = None


@dataclass(frozen=True, slots=True)
class Created:
    request_id: UUID
    status: Literal["pending", "recorded"]
    evaluation: Evaluation


@dataclass(frozen=True, slots=True)
class Decided:
    request_id: UUID
    status: Literal["approved", "denied"]


@dataclass(frozen=True, slots=True)
class Canceled:
    request_id: UUID


async def resolve_rules(
    db: AsyncSession, rules: Iterable[Rule], version_id: UUID | None
) -> tuple[RuleRef, ...]:
    """Each engine rule with its section's title and deep link in the pinned handbook version.

    Raises LookupError if the version lacks a section a rule names, so a test fails loudly if the
    engine and the handbook drift apart (invariant 4). The same rule given twice appears once.
    """
    unique = tuple(dict.fromkeys(rules))
    if not unique:
        return ()
    if version_id is None:
        msg = "This sandbox has no pinned handbook version, so no rule can cite a section"
        raise LookupError(msg)
    titles = await queries.section_titles(db, version_id, {rule.section_id for rule in unique})
    missing = sorted({rule.section_id for rule in unique} - set(titles))
    if missing:
        msg = f"The pinned handbook version has no section {', '.join(missing)}"
        raise LookupError(msg)
    return tuple(
        RuleRef(
            section_id=rule.section_id,
            rule=rule.rule,
            title=titles[rule.section_id],
            deep_link=f"/handbook/{rule.section_id}",
        )
        for rule in unique
    )


async def _facts(db: AsyncSession, tenant_id: UUID, person_id: UUID) -> queries.PersonFacts:
    facts = await queries.load_facts(db, tenant_id, person_id)
    if facts is None:
        msg = "The person is no longer in the sandbox"
        raise LookupError(msg)
    return facts


async def balances(
    db: AsyncSession, actor: Actor, person_id: UUID, now: datetime
) -> Balances | Refused:
    """The person's PTO balance and sick years, if the actor may read them.

    Someone the actor can't read, and someone who doesn't exist, are both `not-found`. Reading
    takes no lock and writes nothing.
    """
    if not can(actor, Action.TIMEOFF_READ, PersonResource(person_id)):
        return Refused(_NOT_FOUND)
    facts = await queries.load_facts(db, actor.tenant_id, person_id)
    if facts is None:
        return Refused(_NOT_FOUND)
    requests = await queries.load_requests(db, actor.tenant_id, person_id)
    today = today_at(facts.timezone, now)
    pto = pto_balance(facts.person, facts.opening, requests, facts.holidays, today)
    sick = sick_years(facts.person, requests, facts.holidays, today)
    cited = [*pto.rules, *(rule for year in sick for rule in year.rules)]
    return Balances(
        person_id=person_id,
        today=today,
        pto=pto,
        sick=sick,
        rules=await resolve_rules(db, cited, facts.handbook_version_id),
    )


async def check(db: AsyncSession, actor: Actor, new: NewRequest, now: datetime) -> Evaluation:
    """What the actor's own possible request would count, and whether it fits. No lock, no write.

    It is a preview: by the time the request is made, the answer can have changed, which is why
    `create` asks again under the lock. The policy rule for requesting is the actor's own person
    only, so a denial can't happen on any path the server builds: it raises PermissionError, a
    bug, not a refusal to explain.
    """
    _require_may_request(actor)
    facts = await _facts(db, actor.tenant_id, actor.person_id)
    requests = await queries.load_requests(db, actor.tenant_id, actor.person_id)
    today = today_at(facts.timezone, now)
    return evaluate(facts.person, facts.opening, requests, facts.holidays, new, today)


def _shape(type_: str, status: str, start: date, end: date) -> dict[str, str]:
    """What the audit log holds of a request: its status, type, and dates. Never a note."""
    return {
        "status": status,
        "type": type_,
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
    }


def _check_via(via: str, proposal_id: UUID | None) -> None:
    # The database holds the same rule in a check. This is the friendly version, for a caller's
    # mistake.
    if via not in ("ui", "assistant"):
        msg = f"A time-off write is made via 'ui' or 'assistant', not {via!r}"
        raise ValueError(msg)
    if (proposal_id is not None) != (via == "assistant"):
        msg = "A proposal goes with a request made by the assistant, and only with it"
        raise ValueError(msg)


def _may_request(actor: Actor) -> bool:
    return can(actor, Action.TIMEOFF_REQUEST, PersonResource(actor.person_id))


def _require_may_request(actor: Actor) -> None:
    if not _may_request(actor):
        msg = "The actor may not request time off for themselves"
        raise PermissionError(msg)


async def create(
    db: AsyncSession,
    actor: Actor,
    new: NewRequest,
    now: datetime,
    *,
    via: Via,
    proposal_id: UUID | None = None,
) -> Created | Refused:
    """Make the actor's own request: PTO as `pending`, sick time as `recorded`.

    The person's lock comes first. The new request is not among the stored ones the engine sees,
    so a request for exactly all that is available fits. If two requests race past the engine's
    overlap check (a path that took no lock), the database's exclusion constraint refuses the
    second, and it comes back as `overlaps` with the caller's transaction still usable.
    """
    _check_via(via, proposal_id)
    if not _may_request(actor):
        return Refused(_NOT_ALLOWED)
    await queries.lock_person(db, actor.tenant_id, actor.person_id)
    facts = await _facts(db, actor.tenant_id, actor.person_id)
    requests = await queries.load_requests(db, actor.tenant_id, actor.person_id)
    today = today_at(facts.timezone, now)
    evaluation = evaluate(facts.person, facts.opening, requests, facts.holidays, new, today)
    if not evaluation.ok or evaluation.amount_minutes is None:
        return Refused(evaluation.problems[0], evaluation)

    status: Literal["pending", "recorded"] = "pending" if new.type == "pto" else "recorded"
    try:
        # A savepoint, so a refused insert doesn't abort the caller's transaction.
        async with db.begin_nested():
            request_id: UUID = (
                await db.execute(
                    insert(TimeOffRequest)
                    .values(
                        tenant_id=actor.tenant_id,
                        person_id=actor.person_id,
                        type=new.type,
                        start_date=new.start,
                        end_date=new.end,
                        partial_minutes=new.partial_minutes,
                        amount_minutes=evaluation.amount_minutes,
                        status=status,
                        created_via=via,
                        proposal_id=proposal_id,
                    )
                    .returning(TimeOffRequest.id)
                )
            ).scalar_one()
    except IntegrityError as error:
        if constraint_name(error) == NO_OVERLAP_CONSTRAINT:
            return Refused(_OVERLAPS)
        raise
    await record_event(
        db,
        tenant_id=actor.tenant_id,
        actor_id=actor.person_id,
        action="timeoff.requested" if new.type == "pto" else "timeoff.recorded",
        target_type="time_off_request",
        target_id=request_id,
        after=_shape(new.type, status, new.start, new.end),
        via=via,
        proposal_id=proposal_id,
    )
    return Created(request_id, status, evaluation)


async def _lock_request(
    db: AsyncSession, actor: Actor, request_id: UUID
) -> queries.StoredRequest | Refused:
    """Find the request, take its person's lock, and read it again under the lock.

    The person can never change (no UPDATE grant), so the first read only says whose lock to take.
    An actor who can't read the person never reaches the lock, and a missing request looks the same
    as an unreadable one.
    """
    first = await queries.load_stored_request(db, actor.tenant_id, request_id)
    if first is None or not _may_read(actor, first):
        return Refused(_NOT_FOUND)
    await queries.lock_person(db, actor.tenant_id, first.person_id)
    now_stored = await queries.load_stored_request(db, actor.tenant_id, request_id)
    if now_stored is None or not _may_read(actor, now_stored):
        return Refused(_NOT_FOUND)
    return now_stored


def _may_read(actor: Actor, request: queries.StoredRequest) -> bool:
    return can(actor, Action.TIMEOFF_READ, _resource(request))


def _resource(request: queries.StoredRequest) -> TimeOffRequestResource:
    return TimeOffRequestResource(
        request.person_id, request.type, request.status, request.start_date
    )


async def decide(
    db: AsyncSession,
    actor: Actor,
    request_id: UUID,
    decision: Decision,
    note: str | None,
    now: datetime,
    *,
    via: Via,
    proposal_id: UUID | None = None,
) -> Decided | Refused:
    """Approve or deny a pending PTO request, as the person's direct manager.

    Under the person's lock, in this order: is the request readable (else `not-found`), is it still
    a pending PTO request (else `status-changed`), may the actor decide it (else `not-allowed`:
    HR, a manager further up, the person themselves, or a sick record). It doesn't run the engine
    again: a pending request already counts against what is available, so approving it changes
    nothing. A denial's note is kept on the request and never in the audit log.

    A note on an approval, a note over 300 characters, a `decision` that isn't `approve` or `deny`,
    or a `now` without a timezone raises ValueError: the routes' schema and clock prevent them.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        msg = "`now` must be timezone-aware"
        raise ValueError(msg)
    if decision not in ("approve", "deny"):
        msg = f"A decision is 'approve' or 'deny', not {decision!r}"
        raise ValueError(msg)
    note = note.strip() if note is not None else None
    if note and decision == "approve":
        msg = "Only a denial carries a note"
        raise ValueError(msg)
    if note is not None and len(note) > MAX_NOTE_CHARACTERS:
        msg = f"A note is at most {MAX_NOTE_CHARACTERS} characters"
        raise ValueError(msg)
    _check_via(via, proposal_id)

    found = await _lock_request(db, actor, request_id)
    if isinstance(found, Refused):
        return found
    # Sick time is recorded, never decided, whatever its status; a PTO request is decided only
    # while it is pending.
    if found.type == "pto" and found.status != "pending":
        return Refused(_STATUS_CHANGED)
    if not can(actor, Action.TIMEOFF_DECIDE, _resource(found)):
        return Refused(_NOT_ALLOWED)

    status: Literal["approved", "denied"] = "approved" if decision == "approve" else "denied"
    changed = (
        await db.execute(
            update(TimeOffRequest)
            .where(TimeOffRequest.id == request_id, TimeOffRequest.status == "pending")
            .values(
                status=status,
                decided_by=actor.person_id,
                decided_at=now,
                # An approval with a note has already been refused; a blank note is none.
                decision_note=note or None,
            )
            .returning(TimeOffRequest.id)
        )
    ).scalar_one_or_none()
    if changed is None:
        return Refused(_STATUS_CHANGED)
    await record_event(
        db,
        tenant_id=actor.tenant_id,
        actor_id=actor.person_id,
        action="timeoff.approved" if decision == "approve" else "timeoff.denied",
        target_type="time_off_request",
        target_id=request_id,
        before=_shape(found.type, found.status, found.start_date, found.end_date),
        after=_shape(found.type, status, found.start_date, found.end_date),
        via=via,
        proposal_id=proposal_id,
    )
    return Decided(request_id, status)


async def cancel(
    db: AsyncSession,
    actor: Actor,
    request_id: UUID,
    now: datetime,
    *,
    via: Via,
    proposal_id: UUID | None = None,
) -> Canceled | Refused:
    """Cancel the actor's own request: a pending one any time, an approved or recorded one only
    before its first day, by the person's own calendar.

    Under the person's lock, in this order: readable (else `not-found`), still open (else
    `status-changed`, for a denied or canceled one), the actor's own (else `not-allowed`), and not
    yet started (else `already-started`).
    """
    _check_via(via, proposal_id)
    found = await _lock_request(db, actor, request_id)
    if isinstance(found, Refused):
        return found
    if found.status not in ("pending", "approved", "recorded"):
        return Refused(_STATUS_CHANGED)
    facts = await _facts(db, actor.tenant_id, found.person_id)
    today = today_at(facts.timezone, now)
    if not can(actor, Action.TIMEOFF_CANCEL, _resource(found), today=today):
        if found.person_id != actor.person_id:
            return Refused(_NOT_ALLOWED)
        return Refused(_ALREADY_STARTED)

    changed = (
        await db.execute(
            update(TimeOffRequest)
            .where(TimeOffRequest.id == request_id, TimeOffRequest.status == found.status)
            .values(status="canceled", canceled_at=now)
            .returning(TimeOffRequest.id)
        )
    ).scalar_one_or_none()
    if changed is None:
        return Refused(_STATUS_CHANGED)
    await record_event(
        db,
        tenant_id=actor.tenant_id,
        actor_id=actor.person_id,
        action="timeoff.canceled",
        target_type="time_off_request",
        target_id=request_id,
        before=_shape(found.type, found.status, found.start_date, found.end_date),
        after=_shape(found.type, "canceled", found.start_date, found.end_date),
        via=via,
        proposal_id=proposal_id,
    )
    return Canceled(request_id)
