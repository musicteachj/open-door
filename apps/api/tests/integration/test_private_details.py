"""A private-details row is visible only to its own person and to HR, even to a raw query."""

from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.tenancy import TenantContext, set_is_hr, tenant_session
from tests.integration.conftest import MakeTenant

pytestmark = pytest.mark.integration

# Raw SQL, not the policy layer: the database applies the rule on its own.
PRIVATE_ROWS = text("SELECT person_id FROM person_private")
ONE_PRIVATE_ROW = text("SELECT count(*) FROM person_private WHERE person_id = :person_id")


async def private_rows(session: AsyncSession) -> set[UUID]:
    return set((await session.execute(PRIVATE_ROWS)).scalars())


async def test_an_employee_sees_only_their_own_private_row(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()

    context = TenantContext(tenant.id, tenant.employee_id)
    async with tenant_session(app_engine, context) as session:
        visible = await private_rows(session)
        colleagues = await session.scalar(ONE_PRIVATE_ROW, {"person_id": tenant.colleague_id})

    assert visible == {tenant.employee_id}
    assert colleagues == 0


async def test_hr_sees_every_private_row_in_its_own_tenant(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant, other_tenant = await make_tenant(), await make_tenant()

    async with tenant_session(app_engine, TenantContext(tenant.id, tenant.hr_id)) as session:
        await set_is_hr(session, True)
        visible = await private_rows(session)

    assert visible == {tenant.employee_id, tenant.colleague_id, tenant.hr_id}
    assert other_tenant.employee_id not in visible


async def test_the_hr_flag_lasts_only_until_the_transaction_ends(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    context = TenantContext(tenant.id, tenant.hr_id)

    async with AsyncSession(app_engine, info={"tenant": context}) as session:
        async with session.begin():
            await set_is_hr(session, True)
            during = await private_rows(session)
        async with session.begin():
            after = await private_rows(session)

    assert len(during) == 3
    assert after == {tenant.hr_id}


async def test_the_hr_flag_survives_a_savepoint(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()

    async with tenant_session(app_engine, TenantContext(tenant.id, tenant.hr_id)) as session:
        await set_is_hr(session, True)
        before = await private_rows(session)
        # The statement matters: an empty begin_nested() emits no SAVEPOINT at all.
        async with session.begin_nested():
            await session.execute(text("SELECT 1"))
        after = await private_rows(session)

    assert before == {tenant.employee_id, tenant.colleague_id, tenant.hr_id}
    assert after == before
