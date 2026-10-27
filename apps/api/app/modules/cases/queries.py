"""Reading and locking for the case service.

Row-level security limits every query here to the actor's tenant, and a case row to the person who
opened it and to HR. These functions never decide who may see what: the service asks the policy
layer first. A case's summary and timeline are HR's alone to read, so those queries return nothing
for anyone else.
"""

import base64
import json
from datetime import UTC, date, datetime, timedelta
from typing import Any, NamedTuple
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import ColumnElement, Date, case, cast, func, insert, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.guard import FLAGGED_CATEGORIES
from app.db.locks import CASE_PERSON_NS, lock_tenant_scoped
from app.db.models import (
    AiTurn,
    Case,
    CaseEvent,
    CaseSummary,
    Department,
    Holiday,
    Location,
    Person,
)
from app.domain.cases import HQ_LOCATION_CODE, HQ_TIMEZONE, hq_closed_days, reply_by

# Far enough past the sent day to cover two business days around any run of closures and a New
# Year's Day.
HOLIDAY_LOOKAHEAD = timedelta(days=21)

# The statuses that count against a person's limit of 5, and that HR's "open" filter shows. They
# are one list because both mean "HR has not finished with it".
WAITING_STATUSES = ("new", "in_review")
PAGE_SIZE = 25


async def lock_person(db: AsyncSession, tenant_id: UUID, person_id: UUID) -> None:
    """Take the person's case lock until the transaction ends, so two sends for one person run one
    after the other and the second sees the first (the waiting limit, the one case per turn)."""
    await lock_tenant_scoped(db, CASE_PERSON_NS, tenant_id, person_id)


async def _hq_location(db: AsyncSession, tenant_id: UUID) -> Any:
    """Denver HQ's location row (its ID and zone) in the sandbox, or None."""
    return (
        await db.execute(
            select(Location.id, Location.timezone).where(
                Location.tenant_id == tenant_id, func.lower(Location.code) == HQ_LOCATION_CODE
            )
        )
    ).one_or_none()


async def hq_zone_and_holidays(
    db: AsyncSession, tenant_id: UUID, sent_on: date
) -> tuple[ZoneInfo, frozenset[date]]:
    """Denver HQ's zone and its closed days from the sent day on, across the year's end.

    From the sandbox's own holiday table when the Denver location is there. A sandbox without it
    gets the company calendar for the sent year and the next, which is what the seed stores.
    """
    row = await _hq_location(db, tenant_id)
    if row is None:
        return ZoneInfo(HQ_TIMEZONE), hq_closed_days(sent_on.year, sent_on.year + 1)
    dates = await db.scalars(
        select(Holiday.holiday_date).where(
            Holiday.tenant_id == tenant_id,
            Holiday.location_id == row.id,
            Holiday.holiday_date >= sent_on - timedelta(days=1),
            Holiday.holiday_date <= sent_on + HOLIDAY_LOOKAHEAD,
        )
    )
    return ZoneInfo(row.timezone), frozenset(dates)


async def reply_by_at(db: AsyncSession, tenant_id: UUID, sent_at: datetime) -> date:
    """The date HR replies by for a case sent at `sent_at` (an aware instant)."""
    # The sent day in Denver is needed to bound the holidays; a day either side is harmless.
    provisional = sent_at.astimezone(UTC).date()
    zone, holidays = await hq_zone_and_holidays(db, tenant_id, provisional)
    return reply_by(sent_at, zone, holidays)


async def count_waiting(db: AsyncSession, tenant_id: UUID, person_id: UUID) -> int:
    return (
        await db.execute(
            select(func.count())
            .select_from(Case)
            .where(
                Case.tenant_id == tenant_id,
                Case.person_id == person_id,
                Case.status.in_(WAITING_STATUSES),
            )
        )
    ).scalar_one()


async def case_by_submission(
    db: AsyncSession, tenant_id: UUID, person_id: UUID, submission_id: UUID
) -> Case | None:
    return (
        await db.execute(
            select(Case).where(
                Case.tenant_id == tenant_id,
                Case.person_id == person_id,
                Case.submission_id == submission_id,
            )
        )
    ).scalar_one_or_none()


async def case_by_turn(
    db: AsyncSession, tenant_id: UUID, person_id: UUID, turn_id: UUID
) -> Case | None:
    return (
        await db.execute(
            select(Case).where(
                Case.tenant_id == tenant_id, Case.person_id == person_id, Case.turn_id == turn_id
            )
        )
    ).scalar_one_or_none()


def flagged_turn_clause() -> ColumnElement[bool]:
    """The SQL form of `verdict_is_flagged`: the guard called the turn sensitive or crisis."""
    category: ColumnElement[str] = AiTurn.guard_verdict["category"].as_string()
    return category.in_(FLAGGED_CATEGORIES)


async def own_flagged_turn_conversation(
    db: AsyncSession, tenant_id: UUID, person_id: UUID, turn_id: UUID
) -> UUID | None:
    """The conversation of the person's own flagged turn, or None for a turn that does not exist,
    is someone else's, or was not flagged. The caller cannot tell the three apart."""
    return (
        await db.execute(
            select(AiTurn.conversation_id).where(
                AiTurn.tenant_id == tenant_id,
                AiTurn.id == turn_id,
                AiTurn.person_id == person_id,
                flagged_turn_clause(),
            )
        )
    ).scalar_one_or_none()


class OpenedCase(NamedTuple):
    """What a conversation's reload shows of a case: never its words or keys."""

    turn_id: UUID
    status: str
    reply_by: date


async def cases_by_turn(
    db: AsyncSession, tenant_id: UUID, person_id: UUID, conversation_id: UUID
) -> dict[UUID, OpenedCase]:
    """The person's own cases opened from a conversation's turns, by turn: one query for the whole
    conversation. Filtered by the person, though HR's session could read more."""
    rows = await db.execute(
        select(Case.turn_id, Case.status, Case.reply_by).where(
            Case.tenant_id == tenant_id,
            Case.person_id == person_id,
            Case.conversation_id == conversation_id,
            Case.turn_id.is_not(None),
        )
    )
    return {
        row.turn_id: OpenedCase(row.turn_id, row.status, row.reply_by)
        for row in rows
        if row.turn_id is not None
    }


async def load_case(db: AsyncSession, tenant_id: UUID, case_id: UUID) -> Case | None:
    """The case, if this transaction's person may read the row (its opener, or HR)."""
    return (
        await db.execute(select(Case).where(Case.tenant_id == tenant_id, Case.id == case_id))
    ).scalar_one_or_none()


async def load_case_by_id(db: AsyncSession, case_id: UUID) -> Case | None:
    """The case by ID alone, for work that has no actor: row-level security names the sandbox."""
    return (await db.execute(select(Case).where(Case.id == case_id))).scalar_one_or_none()


async def words_read_by(db: AsyncSession, tenant_id: UUID, case_id: UUID, actor_id: UUID) -> bool:
    return (
        await db.execute(
            select(CaseEvent.id)
            .where(
                CaseEvent.tenant_id == tenant_id,
                CaseEvent.case_id == case_id,
                CaseEvent.actor_person_id == actor_id,
                CaseEvent.kind == "text_read",
            )
            .limit(1)
        )
    ).first() is not None


async def add_event(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    case_id: UUID,
    actor_id: UUID | None,
    kind: str,
    from_status: str | None = None,
    to_status: str | None = None,
    event_id: UUID,
) -> None:
    """Add a timeline row. A Core insert with the ID made by the caller and nothing asked back:
    the person who opened a case cannot read its events, and Postgres checks RETURNING against the
    SELECT rule."""
    await db.execute(
        insert(CaseEvent).values(
            id=event_id,
            tenant_id=tenant_id,
            case_id=case_id,
            actor_person_id=actor_id,
            kind=kind,
            from_status=from_status,
            to_status=to_status,
        )
    )


async def newest_summary(db: AsyncSession, tenant_id: UUID, case_id: UUID) -> CaseSummary | None:
    return (
        await db.execute(
            select(CaseSummary)
            .where(CaseSummary.tenant_id == tenant_id, CaseSummary.case_id == case_id)
            .order_by(CaseSummary.created_at.desc(), CaseSummary.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


class TimelineRow(NamedTuple):
    kind: str
    occurred_at: datetime
    actor_person_id: UUID | None
    given_name: str | None
    family_name: str | None
    from_status: str | None
    to_status: str | None


class PersonCard(NamedTuple):
    given_name: str
    family_name: str
    title: str
    work_email: str
    department_name: str
    location_name: str


async def timeline(db: AsyncSession, tenant_id: UUID, case_id: UUID) -> list[TimelineRow]:
    return list(
        TimelineRow(*row)
        for row in (
            await db.execute(
                select(
                    CaseEvent.kind,
                    CaseEvent.occurred_at,
                    CaseEvent.actor_person_id,
                    Person.given_name,
                    Person.family_name,
                    CaseEvent.from_status,
                    CaseEvent.to_status,
                )
                .outerjoin(
                    Person,
                    (Person.tenant_id == CaseEvent.tenant_id)
                    & (Person.id == CaseEvent.actor_person_id),
                )
                .where(CaseEvent.tenant_id == tenant_id, CaseEvent.case_id == case_id)
                .order_by(CaseEvent.occurred_at, CaseEvent.id)
            )
        ).all()
    )


async def person_card(db: AsyncSession, tenant_id: UUID, person_id: UUID) -> PersonCard | None:
    row = (
        await db.execute(
            select(
                Person.given_name,
                Person.family_name,
                Person.title,
                Person.work_email,
                Department.name.label("department_name"),
                Location.name.label("location_name"),
            )
            .join(
                Department,
                (Department.tenant_id == Person.tenant_id)
                & (Department.id == Person.department_id),
            )
            .join(
                Location,
                (Location.tenant_id == Person.tenant_id) & (Location.id == Person.location_id),
            )
            .where(Person.tenant_id == tenant_id, Person.id == person_id)
        )
    ).one_or_none()
    return None if row is None else PersonCard(*row)


# --- the queue ---

# New cases come first, by reply-by date; everything else follows, oldest first. The sort key is
# four columns, so a cursor is those four values of the last row.
_NEW_FIRST = case((Case.status == "new", 0), else_=1)
_REPLY_KEY = case((Case.status == "new", Case.reply_by), else_=date(1970, 1, 1))


def encode_cursor(row: Case) -> str:
    key = [
        0 if row.status == "new" else 1,
        (row.reply_by if row.status == "new" else date(1970, 1, 1)).isoformat(),
        row.created_at.isoformat(),
        str(row.id),
    ]
    return base64.urlsafe_b64encode(json.dumps(key).encode()).decode()


def decode_cursor(cursor: str) -> tuple[int, date, datetime, UUID]:
    """The sort key a cursor names. Raises ValueError for anything that is not one of ours."""
    try:
        key = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        if not isinstance(key, list) or len(key) != 4:
            raise ValueError
        group, reply, created, case_id = key
        # A bool is an int in Python, and a number is not a date or an ID: check the types.
        if type(group) is not int or group not in (0, 1):
            raise ValueError
        if not (isinstance(reply, str) and isinstance(created, str) and isinstance(case_id, str)):
            raise ValueError
        parsed_created = datetime.fromisoformat(created)
        if parsed_created.tzinfo is None:
            raise ValueError
        return group, date.fromisoformat(reply), parsed_created, UUID(case_id)
    except (ValueError, TypeError, KeyError, AttributeError):
        raise ValueError("not a cursor") from None


def status_clause(status: str | None) -> ColumnElement[bool] | None:
    if status is None:
        return None
    if status == "open":
        return Case.status.in_(WAITING_STATUSES)
    return Case.status == status


async def queue_rows(
    db: AsyncSession,
    tenant_id: UUID,
    status: str | None,
    cursor: tuple[int, date, datetime, UUID] | None,
    limit: int,
) -> list[Any]:
    query = (
        select(
            Case,
            Person.given_name,
            Person.family_name,
            Person.title,
            Location.name.label("location_name"),
        )
        .join(Person, (Person.tenant_id == Case.tenant_id) & (Person.id == Case.person_id))
        .join(
            Location,
            (Location.tenant_id == Person.tenant_id) & (Location.id == Person.location_id),
        )
        .where(Case.tenant_id == tenant_id)
        .order_by(_NEW_FIRST, _REPLY_KEY, Case.created_at, Case.id)
        .limit(limit + 1)
    )
    clause = status_clause(status)
    if clause is not None:
        query = query.where(clause)
    if cursor is not None:
        query = query.where(
            tuple_(_NEW_FIRST, _REPLY_KEY, Case.created_at, Case.id) > tuple_(*cursor)
        )
    return list((await db.execute(query)).all())


async def counts(
    db: AsyncSession, tenant_id: UUID, hr_id: UUID, today: date | None = None
) -> tuple[int, int]:
    """New cases, and the new ones whose reply is due today or already late, in one query.

    Today is Denver HQ's date by the database's clock, unless the caller names a day (a test of
    seeded data). HR's own cases are left out: they cannot act on them.
    """
    hq_zone = func.coalesce(
        select(Location.timezone)
        .where(Location.tenant_id == tenant_id, func.lower(Location.code) == HQ_LOCATION_CODE)
        .scalar_subquery(),
        HQ_TIMEZONE,
    )
    due_by: Any = cast(func.timezone(hq_zone, func.now()), Date) if today is None else today
    row = (
        await db.execute(
            select(
                func.count().label("new"),
                func.count().filter(Case.reply_by <= due_by).label("due"),
            ).where(Case.tenant_id == tenant_id, Case.status == "new", Case.person_id != hr_id)
        )
    ).one()
    return row.new, row.due
