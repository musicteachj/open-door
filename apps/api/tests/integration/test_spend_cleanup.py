"""Removing a sandbox together with its daily-ledger rows, in one transaction. Both the assistant
eval and the proxy check clean up through this."""

import importlib.util
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.ai.budget import Caps, reserve
from app.core.config import Settings
from app.db.spend_cleanup import SpendRow, remove_sandboxes, spend_rows_of
from app.db.tenancy import TenantContext
from tests.integration.conftest import MakeTenant
from tests.integration.test_budget import add_turn, daily_ids, delete_daily_rows_except

pytestmark = pytest.mark.integration

SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "proxy-check" / "check.py"
LOTS = Caps(Decimal(1000), Decimal(100000))


async def tenant_exists(owner_engine: AsyncEngine, tenant_id: UUID) -> bool:
    async with owner_engine.connect() as connection:
        found = await connection.scalar(
            text("SELECT count(*) FROM tenants WHERE id = :id"), {"id": tenant_id}
        )
    return bool(found == 1)


async def reserved_sandbox(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, make_tenant: MakeTenant
) -> tuple[UUID, list[SpendRow]]:
    """A sandbox with one reservation, and its spend rows as the cleanup reads them."""
    tenant = await make_tenant()
    turn_id = await add_turn(app_engine, tenant)
    await reserve(
        app_engine,
        TenantContext(tenant.id, tenant.employee_id),
        turn_id=turn_id,
        amount_usd=Decimal("0.08"),
        caps=LOTS,
    )
    async with owner_engine.connect() as connection:
        return tenant.id, await spend_rows_of(connection, [tenant.id])


async def test_the_daily_rows_and_the_tenant_go_together(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    before = await daily_ids(owner_engine)
    tenant_id, rows = await reserved_sandbox(app_engine, owner_engine, make_tenant)
    assert len(rows) == 2, "the sample tenant's own spend row, and the reservation"
    assert len(await daily_ids(owner_engine)) == len(before) + 1

    await remove_sandboxes(owner_engine, [tenant_id], rows)

    assert not await tenant_exists(owner_engine, tenant_id)
    assert sorted(await daily_ids(owner_engine)) == sorted(before)


async def test_a_failure_in_the_daily_delete_leaves_the_tenant_in_place(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    before = await daily_ids(owner_engine)
    tenant_id, rows = await reserved_sandbox(app_engine, owner_engine, make_tenant)
    # The second row cannot be bound as a number, so the delete fails after the first one ran.
    broken: list[Any] = [*rows, ("settle", "not a number", datetime.now(UTC))]
    try:
        with pytest.raises(DBAPIError):
            await remove_sandboxes(owner_engine, [tenant_id], broken)

        assert await tenant_exists(owner_engine, tenant_id)
        assert len(await daily_ids(owner_engine)) == len(before) + 1, "the first delete rolled back"
    finally:
        await delete_daily_rows_except(owner_engine, before)


async def test_the_proxy_checks_cleanup_removes_its_sandbox_and_ledger_rows(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    make_tenant: MakeTenant,
    database_settings: Settings,
) -> None:
    spec = importlib.util.spec_from_file_location("proxy_check_script", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    url = str(database_settings.migration_database_url)
    before = await daily_ids(owner_engine)
    started_at = await script.database_now(url)
    tenant_id, _rows = await reserved_sandbox(app_engine, owner_engine, make_tenant)

    await script.clean_up_database(url, [str(tenant_id)], started_at)

    assert not await tenant_exists(owner_engine, tenant_id)
    assert sorted(await daily_ids(owner_engine)) == sorted(before)


async def test_an_identical_daily_row_that_is_not_the_sandboxs_survives(
    owner_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    before = await daily_ids(owner_engine)
    tenant = await make_tenant()
    # Two daily rows of one kind, amount, and instant (one transaction, so one now()); only one
    # belongs to the sandbox being removed.
    async with owner_engine.begin() as connection:
        stamps = [
            await connection.scalar(
                text(
                    "INSERT INTO ai_spend_daily (kind, amount_usd) VALUES ('reserve', 0.07)"
                    " RETURNING created_at"
                )
            )
            for _ in range(2)
        ]
    try:
        assert len(await daily_ids(owner_engine)) == len(before) + 2

        await remove_sandboxes(owner_engine, [tenant.id], [("reserve", Decimal("0.07"), stamps[0])])

        assert not await tenant_exists(owner_engine, tenant.id)
        assert len(await daily_ids(owner_engine)) == len(before) + 1, "one of the two went"
    finally:
        await delete_daily_rows_except(owner_engine, before)
