"""The cleanup login deletes expired tenants, and only those. Their rows go with them."""

from uuid import UUID

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.base import Base
from app.db.models import Tenant
from app.db.tenancy import TenantContext, tenant_session
from tests.integration.conftest import MakeTenant
from tests.integration.test_row_level_security import PERMISSIVE_POLICIES, squeezed

pytestmark = pytest.mark.integration

TABLES_WITH_A_TENANT = [table for table in Base.metadata.sorted_tables if "tenant_id" in table.c]


async def rows_left(owner_engine: AsyncEngine, tenant_id: UUID) -> dict[str, int]:
    """Every table's row count for one tenant. The owner sees all rows in development and CI,
    because it is a superuser, and a superuser bypasses row-level security."""
    counts: dict[str, int] = {}
    async with owner_engine.connect() as connection:
        tenants = select(func.count()).where(Tenant.id == tenant_id)
        counts["tenants"] = (await connection.execute(tenants)).scalar_one()
        for table in TABLES_WITH_A_TENANT:
            rows = select(func.count()).select_from(table).where(table.c.tenant_id == tenant_id)
            counts[table.name] = (await connection.execute(rows)).scalar_one()
    return counts


async def delete_tenant(cleanup_engine: AsyncEngine, tenant_id: UUID) -> int:
    async with cleanup_engine.begin() as connection:
        result = await connection.execute(delete(Tenant).where(Tenant.id == tenant_id))
        return result.rowcount


async def test_the_cleanup_login_deletes_an_expired_tenant_with_all_its_rows(
    cleanup_engine: AsyncEngine, owner_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    expired = await make_tenant(expired=True)
    before = await rows_left(owner_engine, expired.id)

    deleted = await delete_tenant(cleanup_engine, expired.id)

    assert all(count > 0 for count in before.values()), before
    assert deleted == 1
    assert await rows_left(owner_engine, expired.id) == dict.fromkeys(before, 0)


async def test_the_cleanup_login_can_neither_see_nor_delete_a_live_tenant(
    cleanup_engine: AsyncEngine, owner_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    live, expired = await make_tenant(), await make_tenant(expired=True)
    async with cleanup_engine.connect() as connection:
        visible = set(
            await connection.scalars(select(Tenant.id).where(Tenant.id.in_([live.id, expired.id])))
        )

    deleted = await delete_tenant(cleanup_engine, live.id)

    assert visible == {expired.id}
    assert deleted == 0
    assert (await rows_left(owner_engine, live.id))["tenants"] == 1


async def test_the_api_cannot_see_another_tenants_expired_row(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    mine, expired = await make_tenant(), await make_tenant(expired=True)

    async with tenant_session(app_engine, TenantContext(mine.id, mine.employee_id)) as session:
        visible = set((await session.execute(select(Tenant.id))).scalars())

    # cleanup_select is written TO od_cleanup, so the API's login never inherits it.
    assert visible == {mine.id}
    assert expired.id not in visible


async def test_an_unfiltered_delete_by_the_cleanup_login_removes_only_expired_tenants(
    cleanup_engine: AsyncEngine, owner_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    # No WHERE clause, so no column is read, and Postgres applies only cleanup_delete's own rule.
    await make_tenant()
    await make_tenant(expired=True)
    async with owner_engine.connect() as connection:
        expired = select(func.count()).where(Tenant.expires_at < func.now())
        expired_count = (await connection.execute(expired)).scalar_one()
        everyone = select(func.count()).select_from(Tenant)
        tenant_count = (await connection.execute(everyone)).scalar_one()

    # Rolled back, so whatever else the database holds is left alone.
    async with cleanup_engine.connect() as connection:
        deleted = (await connection.execute(text("DELETE FROM tenants"))).rowcount
        await connection.rollback()

    # There is at least one live tenant, so deleting everything would not equal the expired count.
    assert 0 < expired_count < tenant_count
    assert deleted == expired_count


async def test_the_cleanup_login_has_exactly_two_policies_and_each_matches_only_expired_tenants(
    cleanup_engine: AsyncEngine,
) -> None:
    async with cleanup_engine.connect() as connection:
        rows = (await connection.execute(text(PERMISSIVE_POLICIES))).all()

    found = [
        (table, policy, command, squeezed(using), squeezed(with_check))
        for table, policy, command, using, with_check in rows
    ]
    assert found == [
        ("tenants", "cleanup_delete", "d", "(expires_at < now())", ""),
        ("tenants", "cleanup_select", "r", "(expires_at < now())", ""),
    ]
