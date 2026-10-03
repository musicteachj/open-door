"""A sandbox can't be given a lifetime longer than a day plus an hour of slack."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.integration

SET_TENANT = text("SELECT set_config('app.tenant_id', :tenant_id, true)")
INSERT_TENANT = text(
    "INSERT INTO tenants (id, expires_at, anchor_date)"
    " VALUES (:tenant_id, now() + make_interval(hours => :lifetime_hours), current_date)"
)
INSERT_TENANT_WITH_DATES = text(
    "INSERT INTO tenants (id, created_at, expires_at, anchor_date)"
    " VALUES (:tenant_id, :created_at, :expires_at, current_date)"
)
READ_CREATED_AT = text("SELECT created_at, now() FROM tenants WHERE id = :tenant_id")

FAR_FUTURE = datetime(9999, 1, 1, tzinfo=UTC)
LONG_AGO = datetime(2000, 1, 1, tzinfo=UTC)


async def insert_tenant_expiring_in(engine: AsyncEngine, lifetime_hours: int) -> None:
    """Insert as the API's login, with the tenant context set. Nothing is ever committed."""
    tenant_id = str(uuid4())
    async with engine.connect() as connection:
        transaction = await connection.begin()
        try:
            await connection.execute(SET_TENANT, {"tenant_id": tenant_id})
            await connection.execute(
                INSERT_TENANT, {"tenant_id": tenant_id, "lifetime_hours": lifetime_hours}
            )
        finally:
            await transaction.rollback()


async def insert_tenant_with_dates(
    engine: AsyncEngine, created_at: datetime, expires_at: datetime
) -> tuple[datetime, datetime]:
    """Insert with a chosen created_at. Return the stored created_at and the transaction's now()."""
    tenant_id = str(uuid4())
    async with engine.connect() as connection:
        transaction = await connection.begin()
        try:
            await connection.execute(SET_TENANT, {"tenant_id": tenant_id})
            await connection.execute(
                INSERT_TENANT_WITH_DATES,
                {"tenant_id": tenant_id, "created_at": created_at, "expires_at": expires_at},
            )
            stored_created_at, now = (
                await connection.execute(READ_CREATED_AT, {"tenant_id": tenant_id})
            ).one()
            return stored_created_at, now
        finally:
            await transaction.rollback()


@pytest.mark.parametrize("lifetime_hours", [1, 24, 25])
async def test_a_lifetime_up_to_25_hours_is_accepted(
    app_engine: AsyncEngine, lifetime_hours: int
) -> None:
    await insert_tenant_expiring_in(app_engine, lifetime_hours)


@pytest.mark.parametrize("lifetime_hours", [26, 24 * 365])
async def test_a_longer_lifetime_is_refused(app_engine: AsyncEngine, lifetime_hours: int) -> None:
    with pytest.raises(IntegrityError, match="ck_tenants_lifetime"):
        await insert_tenant_expiring_in(app_engine, lifetime_hours)


async def test_a_chosen_created_at_cannot_be_used_to_stretch_the_lifetime(
    app_engine: AsyncEngine,
) -> None:
    # The cap compares expires_at with created_at, so a created_at the caller picks would defeat
    # it. A trigger overwrites created_at with the current time.
    with pytest.raises(IntegrityError, match="ck_tenants_lifetime"):
        await insert_tenant_with_dates(app_engine, created_at=FAR_FUTURE, expires_at=FAR_FUTURE)


async def test_a_chosen_created_at_is_replaced_with_the_current_time(
    app_engine: AsyncEngine,
) -> None:
    created_at, now = await insert_tenant_with_dates(
        app_engine, created_at=LONG_AGO, expires_at=LONG_AGO + timedelta(hours=12)
    )

    assert created_at == now


async def test_the_trigger_is_enabled_and_its_function_is_safe(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as connection:
        triggers = (
            await connection.execute(
                text(
                    "SELECT t.tgname, t.tgenabled::text, p.proname,"
                    " p.pronamespace::regnamespace::text, p.prosecdef, p.proconfig"
                    " FROM pg_trigger t JOIN pg_proc p ON p.oid = t.tgfoid"
                    " WHERE t.tgrelid = 'tenants'::regclass AND NOT t.tgisinternal"
                )
            )
        ).all()

    # Enabled ('O'), not SECURITY DEFINER, and its search_path pinned so no other schema can supply
    # the names it uses.
    assert [tuple(row) for row in triggers] == [
        (
            "stamp_created_at",
            "O",
            "stamp_tenant_created_at",
            "app",
            False,
            ["search_path=pg_catalog, pg_temp"],
        )
    ]
