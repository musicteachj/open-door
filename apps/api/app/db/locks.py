"""Transaction-scoped advisory locks, and the one list of their namespaces.

pg_advisory_xact_lock takes two integers: a namespace and a key. Every use in the API has its own
namespace so no two can collide. Pick the next free number below for a new use and list it here.

    4401  the AI budget, one per sandbox      (app/ai/budget.py)
    4402  the AI budget, one per UTC day      (app/ai/budget.py)
    4403  a person's time-off balance         (app/modules/timeoff/queries.py)
    4404  a conversation's proposals          (app/ai/proposals.py)
    4405  a person's waiting cases             (app/modules/cases/queries.py)

The locks are released at commit or rollback, so they stay correct behind a connection pooler.
Taking one again in the same transaction does nothing.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

BUDGET_TENANT_NS = 4401
BUDGET_DAY_NS = 4402
TIMEOFF_PERSON_NS = 4403
CONVERSATION_PROPOSALS_NS = 4404
CASE_PERSON_NS = 4405


async def lock_tenant_scoped(
    db: AsyncSession, namespace: int, tenant_id: UUID, key_id: UUID
) -> None:
    """Take the lock for one row-like thing (a person, a conversation) of one sandbox. The key is
    the tenant and the ID together, so two sandboxes never wait for each other."""
    # The namespace is one of the constants above, never input, so it is written into the text.
    statement = text(
        f"SELECT pg_advisory_xact_lock({int(namespace)},"
        " hashtext(CAST(:tenant_id AS text) || ':' || CAST(:key_id AS text)))"
    )
    await db.execute(statement, {"tenant_id": str(tenant_id), "key_id": str(key_id)})


async def database_now(db: AsyncSession) -> datetime:
    """The transaction's `now()`, the clock the database's own triggers and defaults use."""
    return (await db.execute(select(func.now()))).scalar_one()
