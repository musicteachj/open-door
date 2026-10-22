"""What a time-off proposal stores: its payload (what confirming will run) and its card (what the
person is shown), and the builders that make a card from the time-off service's and the engine's
results.

Both are typed, so a proposal can't be stored with a field the confirm doesn't understand, and the
web client gets the card's shape from the schema. Both are stored as JSONB in camelCase.

**The card is built by the server, never from the model's words.** Every figure is a pair of
minutes and the one label the whole product uses. Names are the directory's. The card never holds
a note or any text a person wrote (a denial's note is the confirm's one input, and goes only onto
the request). A decision card's team coverage is context for the person deciding and is never sent
to the model (invariant 5).
"""

from dataclasses import replace
from datetime import date, datetime
from typing import Annotated, Any, Literal, cast
from uuid import UUID

from pydantic import ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import CamelModel
from app.domain.timeoff.charges import request_charge_minutes
from app.domain.timeoff.evaluate import NewRequest
from app.domain.timeoff.labels import label
from app.domain.timeoff.pto import pto_balance
from app.domain.timeoff.rules import RULES, sick_grant_rule
from app.domain.timeoff.today import today_at
from app.modules.timeoff import queries, service
from app.modules.timeoff.coverage import CoverageRequest, team_coverage
from app.modules.timeoff.schemas import (
    CoverageOut,
    LeaveTypeName,
    NameOut,
    PersonOut,
    RuleRefOut,
    SkippedDay,
)
from app.modules.timeoff.service import Preview, Refused
from app.policy import Actor

type ProposalAction = Literal["timeoff.request", "timeoff.decide", "timeoff.cancel"]


class _Stored(CamelModel):
    """Stored JSON: nothing but the declared fields."""

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------------------------
# Payloads: the validated tool input, and all the confirm will run


class RequestPayload(_Stored):
    type: LeaveTypeName
    start_date: date
    end_date: date
    partial_minutes: int | None = None


class DecidePayload(_Stored):
    request_id: UUID
    decision: Literal["approve", "deny"]


class CancelPayload(_Stored):
    request_id: UUID


type Payload = RequestPayload | DecidePayload | CancelPayload

PAYLOAD_TYPES: dict[str, type[Payload]] = {
    "timeoff.request": RequestPayload,
    "timeoff.decide": DecidePayload,
    "timeoff.cancel": CancelPayload,
}


# ---------------------------------------------------------------------------------------------
# Cards


class RequestCard(_Stored):
    """A card to book PTO or record sick time."""

    # What the card is, so a reader can tell the three apart.
    kind: Literal["request"]

    type: LeaveTypeName
    start_date: date
    end_date: date
    partial_minutes: int | None
    # The same names and shapes as the check route's answer, so one component renders both.
    counted_days: list[date]
    skipped_days: list[SkippedDay]
    # Every figure is minutes for a program and the product's one label for a person.
    amount_minutes: int
    amount_label: str
    # For sick time that spans two years, the first year's: where the request starts.
    available_before_minutes: int
    available_before_label: str
    available_after_minutes: int
    available_after_label: str
    # Codes, such as "short-notice". The web app writes the sentence.
    warnings: list[str]
    # The direct manager for PTO. Null for sick time, which needs no approval.
    approver: NameOut | None
    rules: list[RuleRefOut]


class DecideCard(_Stored):
    """A card to approve or deny a request, for its person's direct manager."""

    # What the card is, so a reader can tell the three apart.
    kind: Literal["decide"]

    requester: PersonOut
    type: LeaveTypeName
    start_date: date
    end_date: date
    partial_minutes: int | None
    amount_minutes: int
    amount_label: str
    # The person's available PTO as it stands: a waiting request already counts against it.
    available_after_minutes: int | None
    available_after_label: str | None
    # Who else on the team is off. Context only: plain facts, never ranked or recommended.
    coverage: list[CoverageOut]
    decision: Literal["approve", "deny"]
    rules: list[RuleRefOut]


class CancelCard(_Stored):
    """A card to cancel a request of the person's own."""

    # What the card is, so a reader can tell the three apart.
    kind: Literal["cancel"]

    type: LeaveTypeName
    start_date: date
    end_date: date
    partial_minutes: int | None
    # Where the request stands: pending, approved, or recorded.
    status: Literal["pending", "approved", "recorded"]
    # For PTO, what the engine charges for it now (a holiday added since it was booked changes it).
    amount_minutes: int
    amount_label: str
    # What goes back into the balance, and the balance after: PTO only. Null for sick time.
    returns_minutes: int | None
    returns_label: str | None
    available_after_minutes: int | None
    available_after_label: str | None
    rules: list[RuleRefOut]


type Card = Annotated[RequestCard | DecideCard | CancelCard, Field(discriminator="kind")]

CARD_TYPES: dict[str, type[RequestCard | DecideCard | CancelCard]] = {
    "timeoff.request": RequestCard,
    "timeoff.decide": DecideCard,
    "timeoff.cancel": CancelCard,
}


def stored_json(model: _Stored) -> dict[str, Any]:
    """The model as the JSON a proposal stores: camelCase, dates as ISO strings."""
    return model.model_dump(mode="json", by_alias=True)


# ---------------------------------------------------------------------------------------------
# Builders

_NOT_FOUND = "not-found"


def request_card(new: NewRequest, preview: Preview, approver_name: str | None) -> RequestCard:
    """The card for a request the engine says can be made. `approver_name` is the person's direct
    manager for PTO, and None for sick time.

    Raises ValueError for a preview with problems: only a request that fits is ever proposed.
    """
    evaluation = preview.evaluation
    if not preview.ok or evaluation.amount_minutes is None or not evaluation.draws:
        msg = "A card is made only for a request the engine accepts"
        raise ValueError(msg)
    # PTO has one draw. Sick time has one per calendar year it touches, and the card shows the
    # first: the year the request starts in.
    draw = evaluation.draws[0]
    return RequestCard(
        kind="request",
        type=new.type,
        start_date=new.start,
        end_date=new.end,
        partial_minutes=new.partial_minutes,
        counted_days=list(evaluation.counted),
        skipped_days=[SkippedDay(day=item.day, reason=item.reason) for item in evaluation.skipped],
        amount_minutes=evaluation.amount_minutes,
        amount_label=label(evaluation.amount_minutes),
        available_before_minutes=draw.available_before_minutes,
        available_before_label=label(draw.available_before_minutes),
        available_after_minutes=draw.available_after_minutes,
        available_after_label=label(draw.available_after_minutes),
        warnings=list(evaluation.warnings),
        approver=None if approver_name is None else NameOut(name=approver_name),
        rules=[RuleRefOut.of(rule) for rule in preview.rules],
    )


async def request_card_for(
    db: AsyncSession, actor: Actor, new: NewRequest, now: datetime
) -> RequestCard | Preview:
    """The card for the actor's own possible request, or the engine's preview if it can't be made
    (its problems say why). Reads only."""
    preview = await service.preview(db, actor, new, now)
    if not preview.ok:
        return preview
    approver = None
    if new.type == "pto":
        approver = await queries.manager_name(db, actor.tenant_id, actor.person_id)
    return request_card(new, preview, approver)


async def decide_card(
    db: AsyncSession,
    actor: Actor,
    request_id: UUID,
    decision: Literal["approve", "deny"],
    now: datetime,
) -> DecideCard | Refused:
    """The card for the actor deciding a request, or why they can't: `not-found` for a request they
    can't read, `status-changed` for one that isn't a waiting PTO request, `not-allowed` when they
    aren't the person's direct manager. Reads only; the confirm checks all of it again."""
    stored = await queries.load_stored_request(db, actor.tenant_id, request_id)
    if stored is None:
        return Refused(_NOT_FOUND)
    if (refused := service.decide_precheck(actor, stored)) is not None:
        return refused
    rows = await queries.load_request_rows(
        db, actor.tenant_id, person_ids=[stored.person_id], request_id=request_id
    )
    if not rows:
        return Refused(_NOT_FOUND)
    row = rows[0]
    # The person's facts are read once, for the coverage, the balance, and the handbook version.
    facts = await queries.load_facts(db, actor.tenant_id, row.person_id)
    coverage = await team_coverage(
        db,
        actor,
        [CoverageRequest(row.id, row.person_id, row.start_date, row.end_date)],
        facts={row.person_id: facts},
    )
    available = await service.pto_available_minutes(db, actor, row.person_id, now, facts=facts)
    version_id = None if facts is None else facts.handbook_version_id
    rules = await service.resolve_rules(db, [RULES["pto-available"]], version_id)
    return DecideCard(
        kind="decide",
        requester=PersonOut(id=row.person_id, name=row.person_name, title=row.person_title),
        type=cast("LeaveTypeName", row.type),
        start_date=row.start_date,
        end_date=row.end_date,
        partial_minutes=row.partial_minutes,
        amount_minutes=row.amount_minutes,
        amount_label=label(row.amount_minutes),
        available_after_minutes=available,
        available_after_label=None if available is None else label(available),
        coverage=[CoverageOut.of(entry) for entry in coverage.get(row.id, ())],
        decision=decision,
        rules=[RuleRefOut.of(rule) for rule in rules],
    )


async def cancel_card(
    db: AsyncSession, actor: Actor, request_id: UUID, now: datetime
) -> CancelCard | Refused:
    """The card for the actor canceling a request of their own, or why they can't (the service's
    own refusals: `not-found`, `status-changed`, `not-allowed`, `already-started`). Reads only."""
    stored = await queries.load_stored_request(db, actor.tenant_id, request_id)
    if stored is None:
        return Refused(_NOT_FOUND)
    facts = await queries.load_facts(db, actor.tenant_id, stored.person_id)
    if facts is None:
        return Refused(_NOT_FOUND)
    today = today_at(facts.timezone, now)
    if (refused := service.cancel_precheck(actor, stored, today)) is not None:
        return refused
    rows = await queries.load_request_rows(
        db, actor.tenant_id, person_ids=[stored.person_id], request_id=request_id
    )
    if not rows:
        return Refused(_NOT_FOUND)
    row = rows[0]
    amount = row.amount_minutes
    returns: int | None = None
    after: int | None = None
    if row.type == "pto":
        # The engine works out the balance with and without this request, never the amount stored
        # when it was made.
        stored_requests = await queries.load_requests(db, actor.tenant_id, row.person_id)
        before = pto_balance(
            facts.person, facts.opening, stored_requests, facts.holidays, today
        ).available_minutes
        without = tuple(
            replace(item, status="canceled") if item.id == str(row.id) else item
            for item in stored_requests
        )
        after = pto_balance(
            facts.person, facts.opening, without, facts.holidays, today
        ).available_minutes
        # The request's own amount is its charge today; what goes back is the balance's change,
        # which can be less (days before the balance began were never part of it).
        amount = request_charge_minutes(
            facts.person, row.start_date, row.end_date, row.partial_minutes, facts.holidays
        )
        returns = after - before
        cited = [RULES["pto-available"]]
    else:
        cited = [sick_grant_rule(facts.person.state)]
    rules = await service.resolve_rules(db, cited, facts.handbook_version_id)
    return CancelCard(
        kind="cancel",
        type=cast("LeaveTypeName", row.type),
        start_date=row.start_date,
        end_date=row.end_date,
        partial_minutes=row.partial_minutes,
        status=cast("Literal['pending', 'approved', 'recorded']", row.status),
        amount_minutes=amount,
        amount_label=label(amount),
        returns_minutes=returns,
        returns_label=None if returns is None else label(returns),
        available_after_minutes=after,
        available_after_label=None if after is None else label(after),
        rules=[RuleRefOut.of(rule) for rule in rules],
    )
