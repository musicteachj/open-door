"""Reading people, inside the caller's tenant-scoped transaction.

Row-level security limits every query here to the actor's tenant. These functions add no tenant
filter of their own, and they never decide who may see what.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import Row, Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.db.models import Department, Location, Person
from app.modules.people.schemas import DepartmentRef, LocationRef, Me, PersonRef
from app.policy import Actor

_Manager = aliased(Person, name="manager")


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
