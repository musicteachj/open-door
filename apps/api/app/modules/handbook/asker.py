"""Build the handbook's `Asker` from the signed-in person.

The actor carries who the person is, not where they work, so this reads their location's state and
code and their employment type from the database. The asker comes only from the server session's
actor, never from a request (invariant 1).
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Location, Person
from app.domain.handbook.applicability import Asker
from app.policy import Actor


async def load_asker(session: AsyncSession, actor: Actor) -> Asker:
    """The asker for `actor`. `session` is in the actor's tenant, so row-level security shows it
    the person and their location."""
    row = (
        await session.execute(
            select(Location.state, Person.employment_type, Location.code)
            .join(
                Location,
                (Location.tenant_id == Person.tenant_id) & (Location.id == Person.location_id),
            )
            .where(Person.id == actor.person_id, Person.tenant_id == actor.tenant_id)
        )
    ).one_or_none()
    if row is None:
        msg = "The actor's person or location is not visible in this session's tenant"
        raise LookupError(msg)
    return Asker(state=row.state, employment_type=row.employment_type, location_code=row.code)
