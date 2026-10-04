"""Reading people, inside the caller's tenant-scoped transaction.

Row-level security limits every query here to the actor's tenant, and the private-details rule
limits `person_private` to the person themselves and HR. These functions add no tenant filter of
their own, and they never decide who may see what: the routes ask the policy layer first.
"""

import base64
import binascii
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Row, Select, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.db.models import Department, Location, Person, PersonPrivate
from app.modules.people.schemas import (
    DepartmentRef,
    DirectoryCard,
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
            id=row.location_id, name=row.location_name, state=row.location_state
        ),
        "manager": manager,
        "work_email": row.work_email,
    }


async def list_directory(
    session: AsyncSession, *, limit: int, after: DirectoryCursor | None
) -> DirectoryResult:
    """One page of the directory, ordered by family name, given name, then ID."""
    query = _cards().order_by(*_DIRECTORY_ORDER).limit(limit + 1)
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
