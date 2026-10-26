"""Tenants can't see or write each other's rows, even on a reused database connection."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Table, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, create_async_engine

from app.core.config import Settings
from app.db.base import Base
from app.db.models import Department, PersonPrivate
from app.db.tenancy import NO_TENANT, TenantContext, set_is_hr, tenant_session
from tests.integration.conftest import MakeTenant

pytestmark = pytest.mark.integration

TENANTS = Base.metadata.tables["tenants"]
PEOPLE = Base.metadata.tables["people"]
# Every table with a tenant_id except sessions, which row-level security doesn't cover.
TENANT_TABLES = [
    table
    for table in Base.metadata.sorted_tables
    if "tenant_id" in table.c and table.name != "sessions"
]
# The assistant's tables a person owns, proposals included. A second, restrictive rule shows each
# row only to that person, HR included, so a read as HR finds none of them. ai_spend is the
# sandbox's own ledger and has no such rule, and the time-off tables carry the tenant rule only.
PERSON_OWNED = [
    table for table in TENANT_TABLES if table.name.startswith("ai_") and "person_id" in table.c
]


async def tenants_seen(session: AsyncSession | AsyncConnection, table: Table) -> set[UUID]:
    """The tenants whose rows in `table` are visible."""
    column = table.c.id if table.name == "tenants" else table.c.tenant_id
    return set((await session.execute(select(column).distinct())).scalars())


async def backend_pid(session: AsyncSession | AsyncConnection) -> int:
    pid: int = (await session.execute(text("SELECT pg_backend_pid()"))).scalar_one()
    return pid


@asynccontextmanager
async def one_connection_engine(settings: Settings) -> AsyncIterator[AsyncEngine]:
    """An engine whose pool holds exactly one connection, so every use reuses it."""
    engine = create_async_engine(str(settings.database_url), pool_size=1, max_overflow=0)
    try:
        yield engine
    finally:
        await engine.dispose()


async def test_a_tenant_sees_its_own_rows_and_none_of_another_tenants(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    mine = await make_tenant()
    await make_tenant()  # Another tenant, with rows in every table too.

    async with tenant_session(app_engine, TenantContext(mine.id, mine.hr_id)) as session:
        # As HR, so the private-details rule shows every private row in the tenant.
        await set_is_hr(session, True)
        seen = {
            table.name: await tenants_seen(session, table)
            for table in [TENANTS, *TENANT_TABLES]
            if table not in PERSON_OWNED
        }
    # The assistant's rows belong to the employee who wrote them, so only they can read them.
    async with tenant_session(app_engine, TenantContext(mine.id, mine.employee_id)) as session:
        for table in PERSON_OWNED:
            seen[table.name] = await tenants_seen(session, table)

    assert len(PERSON_OWNED) == 5
    # Seeing its own rows at all proves the od_app policies reach the login through its
    # membership: with row-level security forced and no policy that applies, Postgres shows nothing.
    assert seen == {name: {mine.id} for name in seen}


async def test_with_no_tenant_every_table_is_empty(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    await make_tenant()

    async with tenant_session(app_engine, NO_TENANT) as session:
        seen = {
            table.name: await tenants_seen(session, table) for table in [TENANTS, *TENANT_TABLES]
        }

    assert seen == {name: set() for name in seen}


async def test_a_reused_connection_carries_nothing_from_one_tenant_to_the_next(
    database_settings: Settings, make_tenant: MakeTenant
) -> None:
    first, second = await make_tenant(), await make_tenant()
    async with one_connection_engine(database_settings) as engine:
        async with tenant_session(engine, TenantContext(first.id, first.employee_id)) as session:
            pid = await backend_pid(session)
            assert await tenants_seen(session, PEOPLE) == {first.id}

        # A bare connection, which no hook touches. Postgres now holds '' for app.tenant_id, not
        # NULL, and that must read as "no tenant" instead of raising.
        async with engine.connect() as connection:
            assert await backend_pid(connection) == pid
            leftover = await connection.scalar(
                text("SELECT current_setting('app.tenant_id', true)")
            )
            assert leftover == ""
            assert await tenants_seen(connection, PEOPLE) == set()

        async with tenant_session(engine, NO_TENANT) as session:
            assert await backend_pid(session) == pid
            assert await tenants_seen(session, PEOPLE) == set()

        async with tenant_session(engine, TenantContext(second.id, second.employee_id)) as session:
            assert await backend_pid(session) == pid
            assert await tenants_seen(session, PEOPLE) == {second.id}


async def test_the_hook_overrides_settings_left_behind_on_a_connection(
    database_settings: Settings, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    leave_behind = text(
        "SELECT set_config('app.tenant_id', :tenant_id, false),"
        " set_config('app.person_id', :person_id, false),"
        " set_config('app.is_hr', 'true', false)"
    )

    async with one_connection_engine(database_settings) as engine:
        # set_config(..., false) lasts for the whole connection, past every transaction.
        async with engine.connect() as connection:
            await connection.execute(
                leave_behind,
                {"tenant_id": str(tenant.id), "person_id": str(tenant.employee_id)},
            )
            await connection.commit()

        async with tenant_session(engine, NO_TENANT) as session:
            nothing = await tenants_seen(session, PEOPLE)

        async with tenant_session(engine, TenantContext(tenant.id, tenant.colleague_id)) as session:
            private = set((await session.execute(select(PersonPrivate.person_id))).scalars())

    assert nothing == set()
    # The hook cleared app.is_hr, so the colleague sees only their own private row.
    assert private == {tenant.colleague_id}


async def test_the_hr_flag_does_not_outlive_its_transaction_on_a_reused_connection(
    database_settings: Settings, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()

    async with one_connection_engine(database_settings) as engine:
        async with tenant_session(engine, TenantContext(tenant.id, tenant.hr_id)) as session:
            pid = await backend_pid(session)
            await set_is_hr(session, True)

        # A bare connection, which no hook touches. A flag set for the whole connection instead of
        # the transaction would still read 'true' here, and the next user would be HR.
        async with engine.connect() as connection:
            assert await backend_pid(connection) == pid
            leftover = await connection.scalar(text("SELECT current_setting('app.is_hr', true)"))

    assert leftover == ""


async def test_a_tenant_cannot_write_a_row_into_another_tenant(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    mine, theirs = await make_tenant(), await make_tenant()

    with pytest.raises(DBAPIError, match="violates row-level security policy"):
        async with tenant_session(app_engine, TenantContext(mine.id, mine.hr_id)) as session:
            session.add(Department(id=uuid4(), tenant_id=theirs.id, name="Smuggled"))
