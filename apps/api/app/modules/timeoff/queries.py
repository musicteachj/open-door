"""Reading what the time-off service needs, and taking the lock that guards a person's balance.

Row-level security limits every query to the actor's tenant, and these functions never decide who
may see what: the service asks the policy layer first. Time-off requests and openings have the
tenant rule only, so a manager's session reads a report's rows.
"""

from collections.abc import Collection
from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import ColumnElement, SQLColumnExpression, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.db.models import (
    HandbookSection,
    Holiday,
    Location,
    Person,
    Tenant,
    TimeOffOpening,
    TimeOffRequest,
)
from app.domain.timeoff.model import Opening, Request, Schedule
from app.domain.timeoff.model import Person as EnginePerson

# The two-integer form of pg_advisory_xact_lock takes a namespace and a key. 4401 and 4402 are the
# AI budget's (app/ai/budget.py). This one is a person's time-off balance. The key is the tenant
# and the person together, so two sandboxes never wait for each other.
TIMEOFF_PERSON_NS = 4403
TAKE_PERSON_LOCK = text(
    f"SELECT pg_advisory_xact_lock({TIMEOFF_PERSON_NS},"
    " hashtext(CAST(:tenant_id AS text) || ':' || CAST(:person_id AS text)))"
)


async def lock_person(db: AsyncSession, tenant_id: UUID, person_id: UUID) -> None:
    """Take the person's balance lock until the transaction ends.

    Every write that can change what a person has available takes it BEFORE it reads their
    requests, so two writes for one person run one after the other, and the second sees the
    first. It is a transaction-scoped lock (released at commit or rollback), so it stays correct
    behind a connection pooler. Taking it again in the same transaction does nothing.
    """
    await db.execute(TAKE_PERSON_LOCK, {"tenant_id": str(tenant_id), "person_id": str(person_id)})


@dataclass(frozen=True, slots=True)
class PersonFacts:
    """What the engine needs to know about a person, and where and when they are."""

    person: EnginePerson
    opening: Opening
    # Every holiday at the person's location, which covers every year a request can touch.
    holidays: dict[date, str]
    # The location's IANA zone: "today" is the date there.
    timezone: str
    # The handbook version the person's sandbox answers from; None only for a sandbox made before
    # migration 0004.
    handbook_version_id: UUID | None
    # Whether the person has a manager. Only a direct manager decides PTO, so without one a PTO
    # request could never be decided.
    has_manager: bool


async def load_facts(db: AsyncSession, tenant_id: UUID, person_id: UUID) -> PersonFacts | None:
    """The person's facts, or None if there is no such person in the tenant.

    A person with no opening row (a sandbox made before migration 0009) gets an opening of 0
    minutes as of the sandbox's anchor date. That is conservative: it can only make less available.
    """
    row = (
        await db.execute(
            select(
                Person.employment_type,
                Person.hire_date,
                Person.manager_id,
                Person.scheduled_weekdays,
                Location.id.label("location_id"),
                Location.state,
                Location.timezone,
                Tenant.anchor_date,
                Tenant.handbook_version_id,
            )
            .join(
                Location,
                (Location.tenant_id == Person.tenant_id) & (Location.id == Person.location_id),
            )
            .join(Tenant, Tenant.id == Person.tenant_id)
            .where(Person.id == person_id, Person.tenant_id == tenant_id)
        )
    ).one_or_none()
    if row is None:
        return None
    opening_row = (
        await db.execute(
            select(TimeOffOpening.as_of, TimeOffOpening.amount_minutes).where(
                TimeOffOpening.tenant_id == tenant_id, TimeOffOpening.person_id == person_id
            )
        )
    ).one_or_none()
    opening = (
        Opening(as_of=row.anchor_date, amount_minutes=0)
        if opening_row is None
        else Opening(as_of=opening_row.as_of, amount_minutes=opening_row.amount_minutes)
    )
    holidays = {
        holiday_date: name
        for holiday_date, name in (
            await db.execute(
                select(Holiday.holiday_date, Holiday.name).where(
                    Holiday.tenant_id == tenant_id, Holiday.location_id == row.location_id
                )
            )
        )
    }
    person = EnginePerson(
        employment_type=row.employment_type,
        state=row.state,
        hire_date=row.hire_date,
        schedule=Schedule(frozenset(row.scheduled_weekdays)),
    )
    return PersonFacts(
        person,
        opening,
        holidays,
        row.timezone,
        row.handbook_version_id,
        has_manager=row.manager_id is not None,
    )


async def load_requests(db: AsyncSession, tenant_id: UUID, person_id: UUID) -> tuple[Request, ...]:
    """Every request the person has, in any status, as the engine's `Request`s.

    The engine decides which statuses count. A request being made is never among them: the engine
    would count it twice.
    """
    rows = await db.execute(
        select(
            TimeOffRequest.id,
            TimeOffRequest.type,
            TimeOffRequest.start_date,
            TimeOffRequest.end_date,
            TimeOffRequest.partial_minutes,
            TimeOffRequest.status,
        )
        .where(TimeOffRequest.tenant_id == tenant_id, TimeOffRequest.person_id == person_id)
        .order_by(TimeOffRequest.start_date, TimeOffRequest.id)
    )
    return tuple(
        Request(
            id=str(row.id),
            type=row.type,
            start=row.start_date,
            end=row.end_date,
            partial_minutes=row.partial_minutes,
            status=row.status,
        )
        for row in rows
    )


@dataclass(frozen=True, slots=True)
class StoredRequest:
    id: UUID
    person_id: UUID
    type: str
    status: str
    start_date: date
    end_date: date


async def load_stored_request(
    db: AsyncSession, tenant_id: UUID, request_id: UUID
) -> StoredRequest | None:
    """One request as it stands now, or None if the actor's tenant has no such request.

    Columns, not an entity, so a second read in the same transaction (under the lock) is never
    answered from the session's cache.
    """
    row = (
        await db.execute(
            select(
                TimeOffRequest.id,
                TimeOffRequest.person_id,
                TimeOffRequest.type,
                TimeOffRequest.status,
                TimeOffRequest.start_date,
                TimeOffRequest.end_date,
            ).where(TimeOffRequest.tenant_id == tenant_id, TimeOffRequest.id == request_id)
        )
    ).one_or_none()
    if row is None:
        return None
    return StoredRequest(row.id, row.person_id, row.type, row.status, row.start_date, row.end_date)


async def section_titles(db: AsyncSession, version_id: UUID, keys: set[str]) -> dict[str, str]:
    """The titles of the handbook version's sections whose keys are given."""
    return {
        key: title
        for key, title in (
            await db.execute(
                select(HandbookSection.section_key, HandbookSection.title).where(
                    HandbookSection.version_id == version_id,
                    HandbookSection.section_key.in_(keys),
                )
            )
        )
    }


async def timezone_of(db: AsyncSession, tenant_id: UUID, person_id: UUID) -> str | None:
    """The IANA zone of the person's location: where their "today" is."""
    return (
        await db.execute(
            select(Location.timezone)
            .join(
                Person,
                (Location.tenant_id == Person.tenant_id) & (Location.id == Person.location_id),
            )
            .where(Person.id == person_id, Person.tenant_id == tenant_id)
        )
    ).scalar_one_or_none()


@dataclass(frozen=True, slots=True)
class RequestRow:
    """A request as a page shows it: the stored row with the names of the person and the decider."""

    id: UUID
    person_id: UUID
    person_name: str
    person_title: str
    type: str
    status: str
    start_date: date
    end_date: date
    partial_minutes: int | None
    amount_minutes: int
    created_at: datetime
    created_via: str
    decided_by_name: str | None
    decided_at: datetime | None
    decision_note: str | None
    canceled_at: datetime | None


def _name(
    given_name: SQLColumnExpression[str], family_name: SQLColumnExpression[str]
) -> ColumnElement[str]:
    # `||`, not concat(): a missing decider is a missing name, never a blank one.
    return given_name + " " + family_name


async def load_request_rows(
    db: AsyncSession,
    tenant_id: UUID,
    *,
    person_ids: Collection[UUID],
    overlapping: tuple[date, date] | None = None,
    pending_pto_only: bool = False,
    request_id: UUID | None = None,
    limit: int | None = None,
) -> list[RequestRow]:
    """Requests of the given people, as pages show them.

    `overlapping` keeps requests whose dates meet [from, to]. `pending_pto_only` keeps what waits
    for a decision and orders it oldest sent first; otherwise the order is by first day. Who may
    see which rows is the caller's to ask the policy: these functions only read.
    """
    decider = aliased(Person)
    query = (
        select(
            TimeOffRequest.id,
            TimeOffRequest.person_id,
            _name(Person.given_name, Person.family_name).label("person_name"),
            Person.title.label("person_title"),
            TimeOffRequest.type,
            TimeOffRequest.status,
            TimeOffRequest.start_date,
            TimeOffRequest.end_date,
            TimeOffRequest.partial_minutes,
            TimeOffRequest.amount_minutes,
            TimeOffRequest.created_at,
            TimeOffRequest.created_via,
            _name(decider.given_name, decider.family_name).label("decided_by_name"),
            TimeOffRequest.decided_at,
            TimeOffRequest.decision_note,
            TimeOffRequest.canceled_at,
        )
        .join(
            Person,
            (Person.tenant_id == TimeOffRequest.tenant_id)
            & (Person.id == TimeOffRequest.person_id),
        )
        .outerjoin(
            decider,
            (decider.tenant_id == TimeOffRequest.tenant_id)
            & (decider.id == TimeOffRequest.decided_by),
        )
        .where(TimeOffRequest.tenant_id == tenant_id, TimeOffRequest.person_id.in_(person_ids))
    )
    if request_id is not None:
        query = query.where(TimeOffRequest.id == request_id)
    if overlapping is not None:
        first, last = overlapping
        query = query.where(TimeOffRequest.start_date <= last, TimeOffRequest.end_date >= first)
    if pending_pto_only:
        query = query.where(TimeOffRequest.type == "pto", TimeOffRequest.status == "pending")
        query = query.order_by(TimeOffRequest.created_at, TimeOffRequest.id)
    else:
        query = query.order_by(TimeOffRequest.start_date, TimeOffRequest.id)
    if limit is not None:
        query = query.limit(limit)
    return [
        RequestRow(
            id=row.id,
            person_id=row.person_id,
            person_name=row.person_name,
            person_title=row.person_title,
            type=row.type,
            status=row.status,
            start_date=row.start_date,
            end_date=row.end_date,
            partial_minutes=row.partial_minutes,
            amount_minutes=row.amount_minutes,
            created_at=row.created_at,
            created_via=row.created_via,
            decided_by_name=row.decided_by_name,
            decided_at=row.decided_at,
            decision_note=row.decision_note,
            canceled_at=row.canceled_at,
        )
        for row in await db.execute(query)
    ]


@dataclass(frozen=True, slots=True)
class OffRequest:
    """A person's approved or recorded time off: the facts team coverage needs."""

    person_id: UUID
    person_name: str
    type: str
    start_date: date
    end_date: date
    # Set only for a one-day request: 240 for half a day of PTO, or whole hours of sick time.
    partial_minutes: int | None


async def load_time_off(
    db: AsyncSession,
    tenant_id: UUID,
    person_ids: Collection[UUID],
    first: date,
    last: date,
) -> list[OffRequest]:
    """Approved and recorded requests of these people that meet [first, last]. A pending request
    is not time off yet, and a denied or canceled one never was."""
    rows = await db.execute(
        select(
            TimeOffRequest.person_id,
            _name(Person.given_name, Person.family_name).label("person_name"),
            TimeOffRequest.type,
            TimeOffRequest.start_date,
            TimeOffRequest.end_date,
            TimeOffRequest.partial_minutes,
        )
        .join(
            Person,
            (Person.tenant_id == TimeOffRequest.tenant_id)
            & (Person.id == TimeOffRequest.person_id),
        )
        .where(
            TimeOffRequest.tenant_id == tenant_id,
            TimeOffRequest.person_id.in_(person_ids),
            TimeOffRequest.status.in_(("approved", "recorded")),
            TimeOffRequest.start_date <= last,
            TimeOffRequest.end_date >= first,
        )
        .order_by(Person.family_name, Person.given_name, TimeOffRequest.start_date)
    )
    return [
        OffRequest(
            row.person_id,
            row.person_name,
            row.type,
            row.start_date,
            row.end_date,
            row.partial_minutes,
        )
        for row in rows
    ]


async def manager_name(db: AsyncSession, tenant_id: UUID, person_id: UUID) -> str | None:
    """The name of the person's direct manager, or None if they have none."""
    manager = aliased(Person)
    return (
        await db.execute(
            select(_name(manager.given_name, manager.family_name))
            .join(
                Person,
                (Person.tenant_id == manager.tenant_id) & (Person.manager_id == manager.id),
            )
            .where(Person.id == person_id, Person.tenant_id == tenant_id)
        )
    ).scalar_one_or_none()


async def count_requests(
    db: AsyncSession,
    tenant_id: UUID,
    person_ids: Collection[UUID],
    *,
    status: str,
    type_: str | None = None,
) -> int:
    """How many requests these people have in `status` (of `type_`, if given)."""
    query = select(func.count()).where(
        TimeOffRequest.tenant_id == tenant_id,
        TimeOffRequest.person_id.in_(person_ids),
        TimeOffRequest.status == status,
    )
    if type_ is not None:
        query = query.where(TimeOffRequest.type == type_)
    return (await db.execute(query)).scalar_one()
