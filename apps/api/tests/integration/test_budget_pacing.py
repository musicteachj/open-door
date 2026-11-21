"""The monthly budget, paced by day, on the daily ledger (ADR 0011, amendment of 2026-11-19).

The daily ledger is shared by every test, so each test reads the month's sums first and sets its
budget relative to them. A multiplier of 0 makes the allowance `min(left, floor)`, so the tests
don't depend on today's date (`MonthlyBudget` doesn't validate; `Settings` does). Every row a test
adds is deleted in `finally`.
"""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.ai.budget import (
    TAKE_DAY_LOCK,
    TAKE_TENANT_LOCK,
    BudgetExceeded,
    Caps,
    Reservation,
    budget_state,
    reserve,
)
from app.ai.pacing import MonthlyBudget
from app.db.tenancy import tenant_session
from tests.integration.conftest import MakeTenant, SampleTenant, insert_dated_spend
from tests.integration.test_budget import (
    LOTS,
    add_turn,
    context_of,
    daily_ids,
    delete_daily_rows_except,
    sandbox_sum,
    second_engine,  # noqa: F401  (a fixture)
    wait_for_waiters,
)

# The same SQL as `MONTH_SUMS` in app/ai/budget.py, read as the owner.
MONTH_SUMS = text(
    "WITH today AS (SELECT (now() AT TIME ZONE 'UTC')::date AS d)"
    " SELECT coalesce(sum(s.amount_usd) FILTER (WHERE s.day < today.d), 0),"
    " coalesce(sum(s.amount_usd) FILTER (WHERE s.day = today.d), 0)"
    " FROM today LEFT JOIN ai_spend_daily s"
    " ON s.day >= date_trunc('month', today.d)::date AND s.day <= today.d"
    " GROUP BY today.d"
)
RESERVE_AMOUNT = Decimal("0.50")


async def month_sums(owner_engine: AsyncEngine) -> tuple[Decimal, Decimal]:
    """(the month's rows before today, today's rows)."""
    async with owner_engine.connect() as connection:
        before, today = (await connection.execute(MONTH_SUMS)).one()
    return Decimal(before), Decimal(today)


def month_of(budget_usd: Decimal, floor_usd: Decimal, multiplier: int = 0) -> MonthlyBudget:
    return MonthlyBudget(budget_usd, Decimal(multiplier), floor_usd)


@pytest.fixture
async def ledger_restored(owner_engine: AsyncEngine) -> AsyncIterator[None]:
    """Delete every daily-ledger row the test added, whatever its date."""
    existing = await daily_ids(owner_engine)
    yield
    await delete_daily_rows_except(owner_engine, existing)


pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("ledger_restored")]


async def reserve_amount(
    app_engine: AsyncEngine, tenant: SampleTenant, caps: Caps, amount: Decimal
) -> Reservation:
    turn_id = await add_turn(app_engine, tenant)
    return await reserve(
        app_engine, context_of(tenant), turn_id=turn_id, amount_usd=amount, caps=caps
    )


async def test_the_floor_bounds_today(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    before, today = await month_sums(owner_engine)
    caps = Caps(LOTS, LOTS, month_of(before + today + 100, today + RESERVE_AMOUNT))

    await reserve_amount(app_engine, tenant, caps, RESERVE_AMOUNT)
    with pytest.raises(BudgetExceeded) as refused:
        await reserve_amount(app_engine, tenant, caps, Decimal("0.01"))

    assert refused.value.scope == "daily"


async def test_spend_earlier_this_month_counts(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    today_date = datetime.now(UTC).date()
    if today_date.day == 1:
        pytest.skip("there is no earlier day this month on the 1st")
    tenant = await make_tenant()
    before, today = await month_sums(owner_engine)
    await insert_dated_spend(owner_engine, days_ago=1, amount_usd=Decimal("0.30"))
    caps = Caps(LOTS, LOTS, month_of(before + today + RESERVE_AMOUNT, Decimal(100)))

    with pytest.raises(BudgetExceeded) as refused:
        await reserve_amount(app_engine, tenant, caps, Decimal("0.25"))
    await reserve_amount(app_engine, tenant, caps, Decimal("0.20"))

    assert refused.value.scope == "daily"


async def test_last_months_rows_do_not_count(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    before, today = await month_sums(owner_engine)
    await insert_dated_spend(
        owner_engine, days_ago=datetime.now(UTC).date().day, amount_usd=Decimal("9.00")
    )
    caps = Caps(LOTS, LOTS, month_of(before + today + RESERVE_AMOUNT, Decimal(100)))

    reservation = await reserve_amount(app_engine, tenant, caps, RESERVE_AMOUNT)

    assert reservation.amount_usd == RESERVE_AMOUNT


async def test_the_daily_ceiling_still_applies(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    before, today = await month_sums(owner_engine)
    caps = Caps(LOTS, today + Decimal("0.30"), month_of(before + today + 1000, Decimal(1000), 3))

    with pytest.raises(BudgetExceeded) as refused:
        await reserve_amount(app_engine, tenant, caps, RESERVE_AMOUNT)

    assert refused.value.scope == "daily"


async def test_a_zero_monthly_budget_refuses_everything(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    caps = Caps(LOTS, LOTS, MonthlyBudget(Decimal(0), Decimal(3), Decimal(1)))
    ids_before = await daily_ids(owner_engine)
    sandbox_before = await sandbox_sum(owner_engine, tenant.id)

    with pytest.raises(BudgetExceeded) as refused:
        await reserve_amount(app_engine, tenant, caps, Decimal("0.000001"))

    assert refused.value.scope == "daily"
    assert await daily_ids(owner_engine) == ids_before
    assert await sandbox_sum(owner_engine, tenant.id) == sandbox_before


async def test_two_reservations_race_for_the_last_paced_room(
    app_engine: AsyncEngine,
    second_engine: AsyncEngine,  # noqa: F811
    owner_engine: AsyncEngine,
    make_tenant: MakeTenant,
) -> None:
    tenant = await make_tenant()
    first_turn = await add_turn(app_engine, tenant)
    second_turn = await add_turn(app_engine, tenant)
    before, today = await month_sums(owner_engine)
    # Room for one $0.08 reservation, not two.
    caps = Caps(LOTS, LOTS, month_of(before + today + 100, today + Decimal("0.10")))

    async with app_engine.connect() as holder:
        await holder.execute(TAKE_TENANT_LOCK, {"tenant_id": str(tenant.id)})
        await holder.execute(TAKE_DAY_LOCK)
        attempts = [
            asyncio.create_task(
                reserve(
                    engine,
                    context_of(tenant),
                    turn_id=turn_id,
                    amount_usd=Decimal("0.08"),
                    caps=caps,
                )
            )
            for engine, turn_id in ((app_engine, first_turn), (second_engine, second_turn))
        ]
        try:
            await wait_for_waiters(owner_engine, 2)
        finally:
            await holder.rollback()
    results = await asyncio.gather(*attempts, return_exceptions=True)

    assert len([r for r in results if isinstance(r, Reservation)]) == 1
    refusals = [r for r in results if isinstance(r, BudgetExceeded)]
    assert len(refusals) == 1
    assert refusals[0].scope == "daily"


async def test_the_budget_state_reports_the_paced_room(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    before, today = await month_sums(owner_engine)
    monthly = month_of(before + today + 5, today + Decimal("2"))
    caps = Caps(LOTS, LOTS, monthly)

    async with tenant_session(app_engine, context_of(tenant)) as session:
        state = await budget_state(session, caps)

    # The multiplier is 0, so the allowance is the floor: today's rows plus 2.
    assert state.daily_remaining_usd == Decimal("2")
    assert state.month_remaining_usd == Decimal("5")


async def test_without_a_monthly_budget_nothing_changes(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    _, today = await month_sums(owner_engine)
    caps = Caps(LOTS, today + RESERVE_AMOUNT)

    await reserve_amount(app_engine, tenant, caps, RESERVE_AMOUNT)
    with pytest.raises(BudgetExceeded) as refused:
        await reserve_amount(app_engine, tenant, caps, Decimal("0.01"))
    async with tenant_session(app_engine, context_of(tenant)) as session:
        state = await budget_state(session, caps)

    assert refused.value.scope == "daily"
    assert state.month_remaining_usd is None
    assert state.daily_remaining_usd == Decimal(0)
