"""Loading the actor: who the signed-in person is, and whom they manage.

Being a manager is derived, never stored. A person's reports, direct and indirect, come from a
recursive query on manager_id, run fresh for every request. A change to the org chart therefore
takes effect on the next request, without anyone signing in again. The people who report straight
to the person are loaded with them: deciding a time-off request needs the direct manager.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Person
from app.policy import Actor


async def load_actor(session: AsyncSession, tenant_id: UUID, person_id: UUID) -> Actor | None:
    """The actor for `person_id`, or None if there is no such person in `tenant_id`.

    The actor's tenant is the one on the person's own row, never the caller's value. Row-level
    security shows this transaction only its own tenant's people, and a `tenant_id` that doesn't
    match the row finds no person, so an actor never carries a tenant its person isn't in.
    """
    row = (
        await session.execute(
            select(Person.tenant_id, Person.is_hr_admin).where(
                Person.id == person_id, Person.tenant_id == tenant_id
            )
        )
    ).one_or_none()
    if row is None:
        return None
    reports = (
        select(Person.id, Person.manager_id)
        .where(Person.manager_id == person_id)
        .cte(recursive=True)
    )
    # UNION, not UNION ALL: a person already found is never walked again, so even a loop in the
    # org chart would end. Each person has one manager_id, so carrying it changes nothing there.
    reports = reports.union(
        select(Person.id, Person.manager_id).join(reports, Person.manager_id == reports.c.id)
    )
    # One statement, so the direct reports always come from the same snapshot as the rest.
    found = (await session.execute(select(reports.c.id, reports.c.manager_id))).all()
    # A person who manages themself, or sits in a loop, is found among their own reports. They
    # are never their own report, or they could count as their own manager.
    report_ids = frozenset(row.id for row in found) - {person_id}
    direct = frozenset(row.id for row in found if row.manager_id == person_id) - {person_id}
    return Actor(
        person_id,
        row.tenant_id,
        is_hr_admin=row.is_hr_admin,
        report_ids=report_ids,
        direct_report_ids=direct,
    )
