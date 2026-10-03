"""The tenant context that row-level security reads, set at the start of every transaction.

Postgres policies compare each row's tenant_id with app.current_tenant_id(), which reads the
`app.tenant_id` setting. A listener on every ORM session sets that setting and `app.person_id`,
and clears `app.is_hr`, as each transaction begins. It uses set_config(..., true), so the values
end with the transaction and never reach the next user of a pooled connection. A session with no
context gets empty values, which the policies read as "no tenant", so it sees no rows in any table
that has row-level security. The exception is `sessions`, which has none by design: a session is
looked up by its token before the tenant is known, so a context-less session can read it.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import event, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Session, SessionTransaction


@dataclass(frozen=True, slots=True)
class TenantContext:
    """Whose transaction this is. Both come from the server session, never from request input."""

    tenant_id: UUID | None
    person_id: UUID | None


NO_TENANT = TenantContext(tenant_id=None, person_id=None)

SET_CONTEXT = text(
    "SELECT set_config('app.tenant_id', :tenant_id, true),"
    " set_config('app.person_id', :person_id, true),"
    " set_config('app.is_hr', '', true)"
)
SET_IS_HR = text("SELECT set_config('app.is_hr', :is_hr, true)")


def _setting(value: UUID | None) -> str:
    return "" if value is None else str(value)


def apply_tenant_context(
    session: Session, transaction: SessionTransaction, connection: Connection
) -> None:
    """Scope the transaction that just began to the session's tenant, or to no tenant at all."""
    # The outer transaction set the context; re-running it in a savepoint would clear app.is_hr.
    if transaction.nested:
        return
    context = session.info.get("tenant")
    if not isinstance(context, TenantContext):
        context = NO_TENANT
    connection.execute(
        SET_CONTEXT,
        {"tenant_id": _setting(context.tenant_id), "person_id": _setting(context.person_id)},
    )


# On the Session class, so it covers every ORM session, including the one inside each
# AsyncSession. A module runs once per process, so the listener is registered once.
event.listen(Session, "after_begin", apply_tenant_context)


@asynccontextmanager
async def tenant_session(
    engine: AsyncEngine, context: TenantContext
) -> AsyncIterator[AsyncSession]:
    """A session in one transaction scoped to `context`. It commits if the block succeeds and
    rolls back if it raises."""
    async with (
        AsyncSession(engine, info={"tenant": context}, expire_on_commit=False) as session,
        session.begin(),
    ):
        yield session


async def set_is_hr(session: AsyncSession, value: bool) -> None:
    """Tell the private-details policy whether the actor is HR, until the transaction ends."""
    await session.execute(SET_IS_HR, {"is_hr": "true" if value else "false"})
