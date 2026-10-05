"""Reading people, inside the caller's tenant-scoped transaction.

Row-level security limits every query here to the actor's tenant, and the private-details rule
limits `person_private` to the person themselves and HR. These functions add no tenant filter of
their own, and they never decide who may see what: the routes ask the policy layer first.
"""

import base64
import binascii
import json
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, Row, Select, and_, func, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.db.models import Department, Location, Person, PersonPrivate
from app.modules.people.schemas import (
    DepartmentCount,
    DepartmentRef,
    DirectoryCard,
    DirectoryFacets,
    LocationCount,
    LocationRef,
    Me,
    PersonRef,
    PrivateDetails,
)
from app.policy import Actor

_Manager = aliased(Person, name="manager")

# The directory's order, which the cursor continues from. The index on
# (tenant_id, family_name, given_name, id) serves it.
_DIRECTORY_ORDER = (Person.family_name, Person.given_name, Person.id)


@dataclass(frozen=True, slots=True)
class DirectoryCursor:
    """Where the next page starts: just after this person in the directory's order."""

    family_name: str
    given_name: str
    person_id: UUID

    def encode(self) -> str:
        """Opaque to the client: base64 of the sort key.

        It names the last person read, so it reveals nothing a card doesn't only while every card
        is visible, as in Phase 1. See the backlog before hiding any card from the list.
        """
        key = json.dumps([self.family_name, self.given_name, str(self.person_id)])
        return base64.urlsafe_b64encode(key.encode()).decode().rstrip("=")

    @classmethod
    def decode(cls, cursor: str) -> "DirectoryCursor":
        """Raises ValueError for anything this API didn't issue.

        That includes a name Postgres couldn't compare, so a crafted cursor is a 422, not a 500.
        """
        try:
            raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
            key = json.loads(raw)
            if not (isinstance(key, list) and all(isinstance(part, str) for part in key)):
                raise TypeError
            family_name, given_name, person_id = key
            for name in (family_name, given_name):
                # Postgres text can't hold NUL, and UTF-8 can't encode a lone surrogate.
                if "\x00" in name:
                    raise ValueError
                name.encode()  # A lone surrogate raises UnicodeEncodeError, a ValueError.
            return cls(family_name, given_name, UUID(person_id))
        except (binascii.Error, UnicodeDecodeError, TypeError, ValueError) as exc:
            msg = "Not a directory cursor"
            raise ValueError(msg) from exc


@dataclass(frozen=True, slots=True)
class DirectoryResult:
    """One page of cards, and where the next page starts, if there is one."""

    cards: list[DirectoryCard]
    next_cursor: DirectoryCursor | None


@dataclass(frozen=True, slots=True)
class DirectoryFilters:
    """What narrows the directory. Every field that is set must match."""

    # Matches the full name ("given family"), the title, or the work email, anywhere in the text.
    q: str | None = None
    location_id: UUID | None = None
    department_id: UUID | None = None
    # None means no team filter. An empty set matches no one.
    team: frozenset[UUID] | None = None


# Frozen, so it is safe as a default argument.
NO_FILTERS = DirectoryFilters()


def _escape_like(text: str) -> str:
    """`text` as a LIKE pattern that matches itself, with `\\`, `%`, and `_` escaped."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _matches(filters: DirectoryFilters) -> list[ColumnElement[bool]]:
    """The conditions on a person's own row. Every one must hold."""
    conditions: list[ColumnElement[bool]] = []
    if filters.q is not None:
        pattern = f"%{_escape_like(filters.q)}%"
        conditions.append(
            or_(
                (Person.given_name + " " + Person.family_name).ilike(pattern, escape="\\"),
                Person.title.ilike(pattern, escape="\\"),
                Person.work_email.ilike(pattern, escape="\\"),
            )
        )
    if filters.location_id is not None:
        conditions.append(Person.location_id == filters.location_id)
    if filters.department_id is not None:
        conditions.append(Person.department_id == filters.department_id)
    if filters.team is not None:
        conditions.append(Person.id.in_(filters.team))
    return conditions


def _cards() -> Select[*tuple[Any, ...]]:
    """Exactly the columns a directory card shows, and nothing else of the person's."""
    return (
        select(
            Person.id,
            Person.given_name,
            Person.family_name,
            Person.title,
            Person.work_email,
            Department.id.label("department_id"),
            Department.name.label("department_name"),
            Location.id.label("location_id"),
            Location.name.label("location_name"),
            Location.state.label("location_state"),
            Location.timezone.label("location_timezone"),
            _Manager.id.label("manager_id"),
            _Manager.given_name.label("manager_given_name"),
            _Manager.family_name.label("manager_family_name"),
        )
        .join(Department, Department.id == Person.department_id)
        .join(Location, Location.id == Person.location_id)
        .outerjoin(_Manager, _Manager.id == Person.manager_id)
    )


def _card_fields(row: Row[Any]) -> dict[str, Any]:
    """A directory card's fields, from one row of `_cards()`."""
    manager = None
    if row.manager_id is not None:
        manager = PersonRef(
            id=row.manager_id,
            given_name=row.manager_given_name,
            family_name=row.manager_family_name,
        )
    return {
        "id": row.id,
        "given_name": row.given_name,
        "family_name": row.family_name,
        "title": row.title,
        "department": DepartmentRef(id=row.department_id, name=row.department_name),
        "location": LocationRef(
            id=row.location_id,
            name=row.location_name,
            state=row.location_state,
            timezone=row.location_timezone,
        ),
        "manager": manager,
        "work_email": row.work_email,
    }


async def list_directory(
    session: AsyncSession,
    *,
    limit: int,
    after: DirectoryCursor | None,
    filters: DirectoryFilters = NO_FILTERS,
) -> DirectoryResult:
    """One page of the people the filters match, ordered by family name, given name, then ID."""
    query = _cards().where(*_matches(filters)).order_by(*_DIRECTORY_ORDER).limit(limit + 1)
    if after is not None:
        query = query.where(
            tuple_(*_DIRECTORY_ORDER) > tuple_(after.family_name, after.given_name, after.person_id)
        )
    rows: Sequence[Row[Any]] = (await session.execute(query)).all()
    page = rows[:limit]
    next_cursor = None
    if len(rows) > limit:
        last = page[-1]
        next_cursor = DirectoryCursor(last.family_name, last.given_name, last.id)
    return DirectoryResult([DirectoryCard(**_card_fields(row)) for row in page], next_cursor)


async def directory_facets(
    session: AsyncSession, *, filters: DirectoryFilters, team_ids: frozenset[UUID]
) -> DirectoryFacets:
    """The header's counts and each filter menu's counts, by the faceted-search rule.

    An option's count is how many people the list would show if that option were chosen, keeping
    every other active filter. So a menu's own filter is dropped from its counts, and the option
    takes its place. `my_team` follows the same rule: the list's length with `team_ids` as the team
    filter and the search, location, and department kept. It is None when `team_ids` is empty.
    """
    total = await session.scalar(select(func.count(Person.id)))
    matching = await session.scalar(select(func.count(Person.id)).where(*_matches(filters)))
    # Each menu starts from its options, not from people, and outer-joins the people who match the
    # other filters, so an option nobody matches still appears, with a count of zero.
    other_than_location = _matches(replace(filters, location_id=None))
    locations = await session.execute(
        select(Location.id, Location.name, Location.state, func.count(Person.id).label("count"))
        .outerjoin(Person, and_(Person.location_id == Location.id, *other_than_location))
        .group_by(Location.id)
        .order_by(Location.name, Location.id)
    )
    other_than_department = _matches(replace(filters, department_id=None))
    departments = await session.execute(
        select(Department.id, Department.name, func.count(Person.id).label("count"))
        .outerjoin(Person, and_(Person.department_id == Department.id, *other_than_department))
        .group_by(Department.id)
        .order_by(Department.name, Department.id)
    )
    my_team = None
    if team_ids:
        my_team = await session.scalar(
            select(func.count(Person.id)).where(*_matches(replace(filters, team=team_ids)))
        )
    return DirectoryFacets(
        total=total or 0,
        matching=matching or 0,
        locations=[LocationCount(**row._mapping) for row in locations],
        departments=[DepartmentCount(**row._mapping) for row in departments],
        my_team=my_team,
    )


async def get_card(session: AsyncSession, person_id: UUID) -> DirectoryCard | None:
    row = (await session.execute(_cards().where(Person.id == person_id))).one_or_none()
    return None if row is None else DirectoryCard(**_card_fields(row))


async def get_me(session: AsyncSession, actor: Actor, tenant_expires_at: datetime) -> Me:
    """The actor's own card, with the fields only they see."""
    query = _cards().add_columns(Person.employment_type, Person.persona_key)
    row = (await session.execute(query.where(Person.id == actor.person_id))).one()
    return Me(
        **_card_fields(row),
        employment_type=row.employment_type,
        is_manager=actor.is_manager,
        is_hr_admin=actor.is_hr_admin,
        persona_key=row.persona_key,
        tenant_expires_at=tenant_expires_at,
    )


async def get_private_details(session: AsyncSession, person_id: UUID) -> PrivateDetails | None:
    """The person's private details, or None if the private-details rule hides them.

    Only a SELECT: the rule applies to reads, so a RETURNING on this table would be refused too.
    """
    query = select(
        PersonPrivate.personal_email,
        PersonPrivate.phone,
        PersonPrivate.home_address,
        PersonPrivate.date_of_birth,
    ).where(PersonPrivate.person_id == person_id)
    row = (await session.execute(query)).one_or_none()
    if row is None:
        return None
    return PrivateDetails(
        personal_email=row.personal_email,
        phone=row.phone,
        home_address=row.home_address,
        date_of_birth=row.date_of_birth,
    )
