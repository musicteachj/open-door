"""The budget ledger (ADR 0011): reserve before a call under a lock, settle after it.

The daily ledger is global and is never cleaned by a tenant's deletion, so these tests never assume
it is empty. They read today's sum first, set the caps relative to it, and put it back when they
finish (see `daily_baseline`).
"""

import asyncio
from collections.abc import AsyncIterator
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.ai.budget import (
    BUDGET_DAY_NS,
    BUDGET_TENANT_NS,
    MAX_RESERVATION_USD,
    TAKE_DAY_LOCK,
    TAKE_TENANT_LOCK,
    BudgetExceeded,
    Caps,
    Reservation,
    budget_state,
    reserve,
    settle,
)
from app.ai.pricing import IterationUsage, Usage, reservation_usd, turn_call_cost
from app.core.config import Settings
from app.db.engine import create_engine
from app.db.models import AiConversation, AiTurn
from app.db.tenancy import TenantContext, tenant_session
from tests.integration.conftest import MakeTenant, SampleTenant

pytestmark = pytest.mark.integration

TODAY = text("SELECT (now() AT TIME ZONE 'UTC')::date")
DAILY_SUM = text(
    "SELECT coalesce(sum(amount_usd), 0) FROM ai_spend_daily"
    " WHERE day = (now() AT TIME ZONE 'UTC')::date"
)
INSERT_YESTERDAYS_SPEND = text(
    "INSERT INTO ai_spend_daily (kind, amount_usd, day)"
    " VALUES ('settle', 9.5, (now() AT TIME ZONE 'UTC')::date - 1) RETURNING id"
)
LOTS = Decimal(1000)


async def daily_sum(owner_engine: AsyncEngine) -> Decimal:
    async with owner_engine.connect() as connection:
        return (await connection.execute(DAILY_SUM)).scalar_one()


async def sandbox_sum(owner_engine: AsyncEngine, tenant_id: UUID) -> Decimal:
    async with owner_engine.connect() as connection:
        return (
            await connection.execute(
                text("SELECT coalesce(sum(amount_usd), 0) FROM ai_spend WHERE tenant_id = :t"),
                {"t": tenant_id},
            )
        ).scalar_one()


async def daily_ids(owner_engine: AsyncEngine) -> list[UUID]:
    async with owner_engine.connect() as connection:
        return list((await connection.execute(text("SELECT id FROM ai_spend_daily"))).scalars())


async def delete_daily_rows_except(owner_engine: AsyncEngine, keep: list[UUID]) -> None:
    async with owner_engine.begin() as connection:
        await connection.execute(
            text("DELETE FROM ai_spend_daily WHERE NOT (id = ANY(CAST(:keep AS uuid[])))"),
            {"keep": keep},
        )


@pytest.fixture
async def daily_baseline(owner_engine: AsyncEngine) -> AsyncIterator[Decimal]:
    """Today's global sum when the test began.

    The daily ledger has no tenant, so deleting a test's tenant leaves its rows behind. This
    remembers which rows existed, and when the test ends deletes every other one, through the
    owner, the only login that can. So these tests leave the demo's real daily budget as they
    found it. They must not run at the same time as another run (another pytest, or a live
    session spending): that run's rows would be deleted, or counted against this one's caps.
    """
    existing = await daily_ids(owner_engine)
    before = await daily_sum(owner_engine)
    yield before
    await delete_daily_rows_except(owner_engine, existing)


async def test_the_test_cleanup_deletes_only_the_rows_a_test_added(
    owner_engine: AsyncEngine,
) -> None:
    existing = await daily_ids(owner_engine)
    async with owner_engine.begin() as connection:
        added: UUID = (
            await connection.execute(
                text(
                    "INSERT INTO ai_spend_daily (kind, amount_usd)"
                    " VALUES ('reserve', 0.01) RETURNING id"
                )
            )
        ).scalar_one()

    await delete_daily_rows_except(owner_engine, existing)

    remaining = await daily_ids(owner_engine)
    assert added not in remaining
    assert sorted(remaining) == sorted(existing)


@pytest.fixture
async def second_engine(database_settings: Settings) -> AsyncIterator[AsyncEngine]:
    """Another engine on the API's login, so two reservations run on two connections."""
    engine = create_engine(str(database_settings.database_url))
    yield engine
    await engine.dispose()


async def caps_with_room(
    owner_engine: AsyncEngine,
    tenant_id: UUID,
    *,
    sandbox_room: Decimal = LOTS,
    daily_room: Decimal = LOTS,
) -> Caps:
    """Caps that leave exactly this much room above what is already spent."""
    return Caps(
        sandbox_usd=await sandbox_sum(owner_engine, tenant_id) + sandbox_room,
        daily_usd=await daily_sum(owner_engine) + daily_room,
    )


async def add_turn(engine: AsyncEngine, tenant: SampleTenant) -> UUID:
    """A committed turn for the employee: spend rows point at one."""
    context = TenantContext(tenant.id, tenant.employee_id)
    conversation_id, turn_id = uuid4(), uuid4()
    async with tenant_session(engine, context) as session:
        session.add(
            AiConversation(
                id=conversation_id,
                tenant_id=tenant.id,
                person_id=tenant.employee_id,
                model="claude-opus-5-5",
                guard_model="claude-haiku-5-5",
                effort="medium",
                prompt_version="test",
                toolset_version="test",
            )
        )
        await session.flush()
        session.add(
            AiTurn(
                id=turn_id,
                tenant_id=tenant.id,
                person_id=tenant.employee_id,
                conversation_id=conversation_id,
                question="How much sick leave do I get?",
                status="completed",
            )
        )
    return turn_id


def context_of(tenant: SampleTenant) -> TenantContext:
    return TenantContext(tenant.id, tenant.employee_id)


def test_caps_come_from_the_settings() -> None:
    settings = Settings(ai_sandbox_budget_usd=Decimal("1.25"), ai_daily_budget_usd=Decimal("4"))

    assert Caps.from_settings(settings) == Caps(Decimal("1.25"), Decimal("4"))


async def test_a_reservation_is_recorded_in_both_ledgers(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    make_tenant: MakeTenant,
    daily_baseline: Decimal,
) -> None:
    tenant = await make_tenant()
    turn_id = await add_turn(app_engine, tenant)
    caps = await caps_with_room(owner_engine, tenant.id)
    sandbox_before = await sandbox_sum(owner_engine, tenant.id)

    reservation = await reserve(
        app_engine, context_of(tenant), turn_id=turn_id, amount_usd=Decimal("0.08"), caps=caps
    )

    assert reservation.turn_id == turn_id
    assert reservation.tenant_id == tenant.id
    assert reservation.amount_usd == Decimal("0.08")
    assert await sandbox_sum(owner_engine, tenant.id) == sandbox_before + Decimal("0.08")
    assert await daily_sum(owner_engine) == daily_baseline + Decimal("0.08")
    async with owner_engine.connect() as connection:
        today: date = (await connection.execute(TODAY)).scalar_one()
    assert reservation.day == today


async def test_settling_brings_both_ledgers_to_the_actual_cost(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    make_tenant: MakeTenant,
    daily_baseline: Decimal,
) -> None:
    tenant = await make_tenant()
    turn_id = await add_turn(app_engine, tenant)
    caps = await caps_with_room(owner_engine, tenant.id)
    sandbox_before = await sandbox_sum(owner_engine, tenant.id)
    reservation = await reserve(
        app_engine, context_of(tenant), turn_id=turn_id, amount_usd=Decimal("0.08"), caps=caps
    )

    await settle(app_engine, context_of(tenant), reservation, actual_usd=Decimal("0.0312"))

    assert await sandbox_sum(owner_engine, tenant.id) == sandbox_before + Decimal("0.0312")
    assert await daily_sum(owner_engine) == daily_baseline + Decimal("0.0312")


async def test_a_settle_may_be_positive_when_the_call_cost_more_than_reserved(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    make_tenant: MakeTenant,
    daily_baseline: Decimal,
) -> None:
    # A fallback model priced higher than the one reserved for.
    tenant = await make_tenant()
    turn_id = await add_turn(app_engine, tenant)
    caps = await caps_with_room(owner_engine, tenant.id)
    sandbox_before = await sandbox_sum(owner_engine, tenant.id)
    reservation = await reserve(
        app_engine, context_of(tenant), turn_id=turn_id, amount_usd=Decimal("0.02"), caps=caps
    )

    await settle(app_engine, context_of(tenant), reservation, actual_usd=Decimal("0.05"))

    assert await sandbox_sum(owner_engine, tenant.id) == sandbox_before + Decimal("0.05")
    assert await daily_sum(owner_engine) == daily_baseline + Decimal("0.05")


async def test_a_settle_lands_on_the_day_of_its_reservation(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    make_tenant: MakeTenant,
    daily_baseline: Decimal,
) -> None:
    # A turn that crosses midnight: reserved yesterday, settled today. The settle row is dated by
    # the reservation, which the table allows for a settle by one day.
    tenant = await make_tenant()
    turn_id = await add_turn(app_engine, tenant)
    async with owner_engine.connect() as connection:
        today: date = (await connection.execute(TODAY)).scalar_one()
    yesterday = today - timedelta(days=1)
    reservation = Reservation(turn_id, tenant.id, Decimal("0.08"), yesterday)

    await settle(app_engine, context_of(tenant), reservation, actual_usd=Decimal("0.03"))

    try:
        async with owner_engine.connect() as connection:
            days = (
                await connection.execute(
                    text(
                        "SELECT day, amount_usd FROM ai_spend_daily"
                        " WHERE day = :yesterday AND kind = 'settle' AND amount_usd = -0.05"
                    ),
                    {"yesterday": yesterday},
                )
            ).all()
        assert len(days) >= 1
        assert await daily_sum(owner_engine) == daily_baseline
    finally:
        async with owner_engine.begin() as connection:
            await connection.execute(
                text(
                    "DELETE FROM ai_spend_daily"
                    " WHERE day = :yesterday AND kind = 'settle' AND amount_usd = -0.05"
                ),
                {"yesterday": yesterday},
            )


async def test_a_reservation_over_the_sandbox_cap_is_refused_and_writes_nothing(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    make_tenant: MakeTenant,
    daily_baseline: Decimal,
) -> None:
    tenant = await make_tenant()
    turn_id = await add_turn(app_engine, tenant)
    caps = await caps_with_room(owner_engine, tenant.id, sandbox_room=Decimal("0.05"))
    sandbox_before = await sandbox_sum(owner_engine, tenant.id)

    with pytest.raises(BudgetExceeded) as raised:
        await reserve(
            app_engine, context_of(tenant), turn_id=turn_id, amount_usd=Decimal("0.08"), caps=caps
        )

    assert raised.value.scope == "sandbox"
    assert await sandbox_sum(owner_engine, tenant.id) == sandbox_before
    assert await daily_sum(owner_engine) == daily_baseline


async def test_a_reservation_that_just_fits_is_allowed(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    make_tenant: MakeTenant,
    daily_baseline: Decimal,
) -> None:
    tenant = await make_tenant()
    turn_id = await add_turn(app_engine, tenant)
    caps = await caps_with_room(
        owner_engine, tenant.id, sandbox_room=Decimal("0.08"), daily_room=Decimal("0.08")
    )

    await reserve(
        app_engine, context_of(tenant), turn_id=turn_id, amount_usd=Decimal("0.08"), caps=caps
    )

    assert await sandbox_sum(owner_engine, tenant.id) == caps.sandbox_usd
    assert await daily_sum(owner_engine) == caps.daily_usd


async def test_the_daily_cap_counts_every_sandbox(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    make_tenant: MakeTenant,
    daily_baseline: Decimal,
) -> None:
    first, second = await make_tenant(), await make_tenant()
    first_turn = await add_turn(app_engine, first)
    second_turn = await add_turn(app_engine, second)
    # Plenty of room in each sandbox, $0.10 in the demo's day.
    first_caps = await caps_with_room(owner_engine, first.id, daily_room=Decimal("0.10"))
    second_caps = Caps(
        sandbox_usd=await sandbox_sum(owner_engine, second.id) + LOTS,
        daily_usd=first_caps.daily_usd,
    )
    await reserve(
        app_engine,
        context_of(first),
        turn_id=first_turn,
        amount_usd=Decimal("0.08"),
        caps=first_caps,
    )

    with pytest.raises(BudgetExceeded) as raised:
        await reserve(
            app_engine,
            context_of(second),
            turn_id=second_turn,
            amount_usd=Decimal("0.08"),
            caps=second_caps,
        )

    assert raised.value.scope == "daily"


async def test_the_sandbox_cap_is_reported_before_the_daily_one(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    make_tenant: MakeTenant,
    daily_baseline: Decimal,
) -> None:
    tenant = await make_tenant()
    turn_id = await add_turn(app_engine, tenant)
    caps = await caps_with_room(
        owner_engine, tenant.id, sandbox_room=Decimal("0.01"), daily_room=Decimal("0.01")
    )

    with pytest.raises(BudgetExceeded) as raised:
        await reserve(
            app_engine, context_of(tenant), turn_id=turn_id, amount_usd=Decimal("0.08"), caps=caps
        )

    assert raised.value.scope == "sandbox"


async def test_a_new_utc_day_starts_at_zero(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    make_tenant: MakeTenant,
    daily_baseline: Decimal,
) -> None:
    tenant = await make_tenant()
    turn_id = await add_turn(app_engine, tenant)
    caps = await caps_with_room(owner_engine, tenant.id, daily_room=Decimal("0.10"))
    # Yesterday was a very expensive day. A settle is the one kind the table lets us date
    # yesterday, and it is enough to prove that only today's rows count.
    async with owner_engine.begin() as connection:
        marker: UUID = (await connection.execute(INSERT_YESTERDAYS_SPEND)).scalar_one()

    try:
        await reserve(
            app_engine, context_of(tenant), turn_id=turn_id, amount_usd=Decimal("0.08"), caps=caps
        )
    finally:
        async with owner_engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM ai_spend_daily WHERE id = :id"), {"id": marker}
            )

    assert await daily_sum(owner_engine) == daily_baseline + Decimal("0.08")


async def test_the_budget_state_reports_both_ledgers(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    make_tenant: MakeTenant,
    daily_baseline: Decimal,
) -> None:
    tenant = await make_tenant()
    turn_id = await add_turn(app_engine, tenant)
    caps = await caps_with_room(
        owner_engine, tenant.id, sandbox_room=Decimal("0.30"), daily_room=Decimal("0.10")
    )
    await reserve(
        app_engine, context_of(tenant), turn_id=turn_id, amount_usd=Decimal("0.08"), caps=caps
    )

    async with tenant_session(app_engine, context_of(tenant)) as session:
        state = await budget_state(session, caps)

    assert state.sandbox_remaining_usd == Decimal("0.22")
    assert state.daily_remaining_usd == Decimal("0.02")
    assert not state.sandbox_reached
    assert not state.daily_reached

    turn_id = await add_turn(app_engine, tenant)
    await reserve(
        app_engine, context_of(tenant), turn_id=turn_id, amount_usd=Decimal("0.02"), caps=caps
    )
    async with tenant_session(app_engine, context_of(tenant)) as session:
        state = await budget_state(session, caps)

    assert state.daily_remaining_usd == Decimal("0")
    assert state.daily_reached
    assert not state.sandbox_reached


async def test_the_sandbox_is_reached_when_its_room_is_gone(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    make_tenant: MakeTenant,
    daily_baseline: Decimal,
) -> None:
    tenant = await make_tenant()
    caps = await caps_with_room(owner_engine, tenant.id, sandbox_room=Decimal("0"))

    async with tenant_session(app_engine, context_of(tenant)) as session:
        state = await budget_state(session, caps)

    assert state.sandbox_reached
    assert not state.daily_reached


async def test_the_budget_state_needs_a_tenant(app_engine: AsyncEngine) -> None:
    # Without a tenant, row-level security shows no spend, which would read as a full budget.
    caps = Caps(sandbox_usd=Decimal("1.00"), daily_usd=Decimal("3.00"))

    async with tenant_session(app_engine, TenantContext(None, None)) as session:
        with pytest.raises(ValueError, match="tenant"):
            await budget_state(session, caps)


async def advisory_locks(owner_engine: AsyncEngine, *, granted: bool) -> int:
    """How many budget locks are held (or waited for). Other advisory locks are not counted."""
    async with owner_engine.connect() as connection:
        return (
            await connection.execute(
                text(
                    "SELECT count(*) FROM pg_locks"
                    " WHERE locktype = 'advisory' AND granted = :granted"
                    " AND classid::bigint IN (:tenant_namespace, :day_namespace)"
                ),
                {
                    "granted": granted,
                    "tenant_namespace": BUDGET_TENANT_NS,
                    "day_namespace": BUDGET_DAY_NS,
                },
            )
        ).scalar_one()


async def test_no_lock_outlives_the_transaction(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    make_tenant: MakeTenant,
    daily_baseline: Decimal,
) -> None:
    # A session-level advisory lock would stay on its pooled connection for the next user.
    tenant = await make_tenant()
    turn_id = await add_turn(app_engine, tenant)
    caps = await caps_with_room(owner_engine, tenant.id, sandbox_room=Decimal("0.10"))
    await reserve(
        app_engine, context_of(tenant), turn_id=turn_id, amount_usd=Decimal("0.05"), caps=caps
    )
    with pytest.raises(BudgetExceeded):
        await reserve(
            app_engine, context_of(tenant), turn_id=turn_id, amount_usd=Decimal("0.08"), caps=caps
        )

    assert await advisory_locks(owner_engine, granted=True) == 0


async def test_the_lock_count_ignores_other_advisory_locks(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    async with app_engine.connect() as other:
        # Namespace 1 is nobody's budget.
        await other.execute(text("SELECT pg_advisory_xact_lock(1, 1)"))

        assert await advisory_locks(owner_engine, granted=True) == 0

        await other.rollback()


async def wait_for_waiters(owner_engine: AsyncEngine, count: int) -> None:
    for _ in range(100):
        if await advisory_locks(owner_engine, granted=False) >= count:
            return
        await asyncio.sleep(0.05)
    pytest.fail(f"fewer than {count} reservations are waiting for the budget lock")


async def test_two_reservations_wait_for_each_other_and_only_one_fits(
    app_engine: AsyncEngine,
    second_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    make_tenant: MakeTenant,
    daily_baseline: Decimal,
) -> None:
    # $0.10 of room, two reservations of $0.08. A third connection holds the locks, so both are
    # known to be waiting when it lets go: the first to get them must win, and the second must
    # then see its row.
    tenant = await make_tenant()
    first_turn = await add_turn(app_engine, tenant)
    second_turn = await add_turn(app_engine, tenant)
    caps = await caps_with_room(
        owner_engine, tenant.id, sandbox_room=Decimal("0.10"), daily_room=Decimal("0.10")
    )
    sandbox_before = await sandbox_sum(owner_engine, tenant.id)

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

    wins = [r for r in results if isinstance(r, Reservation)]
    refusals = [r for r in results if isinstance(r, BudgetExceeded)]
    assert len(wins) == 1
    assert len(refusals) == 1
    assert refusals[0].scope in {"sandbox", "daily"}
    assert await sandbox_sum(owner_engine, tenant.id) == sandbox_before + Decimal("0.08")
    assert await daily_sum(owner_engine) == daily_baseline + Decimal("0.08")


async def test_concurrent_reservations_never_both_fit_over_many_races(
    app_engine: AsyncEngine,
    second_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    make_tenant: MakeTenant,
    daily_baseline: Decimal,
) -> None:
    tenant = await make_tenant()
    for _ in range(8):
        first_turn = await add_turn(app_engine, tenant)
        second_turn = await add_turn(app_engine, tenant)
        caps = await caps_with_room(
            owner_engine, tenant.id, sandbox_room=Decimal("0.10"), daily_room=Decimal("0.10")
        )

        results = await asyncio.gather(
            reserve(
                app_engine,
                context_of(tenant),
                turn_id=first_turn,
                amount_usd=Decimal("0.08"),
                caps=caps,
            ),
            reserve(
                second_engine,
                context_of(tenant),
                turn_id=second_turn,
                amount_usd=Decimal("0.08"),
                caps=caps,
            ),
            return_exceptions=True,
        )

        assert sum(isinstance(r, Reservation) for r in results) == 1
        assert sum(isinstance(r, BudgetExceeded) for r in results) == 1


async def test_a_reservation_and_its_settle_sum_to_exactly_the_cost_in_the_database(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    make_tenant: MakeTenant,
    daily_baseline: Decimal,
) -> None:
    # Awkward token counts, so the unrounded prices have more than the ledgers' six places.
    model = "claude-haiku-5-5"
    reserved = reservation_usd(model, estimated_input_tokens=12_347, max_tokens=1_001)
    cost = turn_call_cost(
        [
            IterationUsage(
                model,
                Usage(
                    input_tokens=1_003,
                    output_tokens=77,
                    cache_read_tokens=9_999,
                    cache_write_tokens=1_345,
                ),
            )
        ]
    )
    tenant = await make_tenant()
    turn_id = await add_turn(app_engine, tenant)
    caps = await caps_with_room(owner_engine, tenant.id)
    sandbox_before = await sandbox_sum(owner_engine, tenant.id)

    reservation = await reserve(
        app_engine, context_of(tenant), turn_id=turn_id, amount_usd=reserved, caps=caps
    )
    await settle(app_engine, context_of(tenant), reservation, actual_usd=cost)

    assert await sandbox_sum(owner_engine, tenant.id) == sandbox_before + cost
    assert await daily_sum(owner_engine) == daily_baseline + cost


async def test_a_settle_from_another_sandbox_is_refused(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    make_tenant: MakeTenant,
    daily_baseline: Decimal,
) -> None:
    mine, other = await make_tenant(), await make_tenant()
    turn_id = await add_turn(app_engine, mine)
    caps = await caps_with_room(owner_engine, mine.id)
    reservation = await reserve(
        app_engine, context_of(mine), turn_id=turn_id, amount_usd=Decimal("0.08"), caps=caps
    )
    sandbox_before = await sandbox_sum(owner_engine, mine.id)
    daily_before = await daily_sum(owner_engine)

    with pytest.raises(ValueError, match="sandbox"):
        await settle(app_engine, context_of(other), reservation, actual_usd=Decimal("0.01"))

    assert await sandbox_sum(owner_engine, mine.id) == sandbox_before
    assert await daily_sum(owner_engine) == daily_before


@pytest.mark.parametrize("amount", ["0", "-0.01"])
async def test_a_reservation_that_isnt_positive_is_a_mistake_and_writes_nothing(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    make_tenant: MakeTenant,
    daily_baseline: Decimal,
    amount: str,
) -> None:
    tenant = await make_tenant()
    turn_id = await add_turn(app_engine, tenant)
    caps = await caps_with_room(owner_engine, tenant.id, sandbox_room=Decimal(50))
    sandbox_before = await sandbox_sum(owner_engine, tenant.id)

    with pytest.raises(ValueError, match="positive"):
        await reserve(
            app_engine, context_of(tenant), turn_id=turn_id, amount_usd=Decimal(amount), caps=caps
        )

    assert await sandbox_sum(owner_engine, tenant.id) == sandbox_before
    assert await daily_sum(owner_engine) == daily_baseline


@pytest.mark.parametrize("amount", ["10.000001", "12"])
async def test_a_reservation_the_ledger_cannot_hold_is_refused_as_over_budget(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    make_tenant: MakeTenant,
    daily_baseline: Decimal,
    amount: str,
) -> None:
    # A call this large is refused like any other over the cap, so the turn ends with the budget
    # message rather than an internal error, however large the configured caps are.
    tenant = await make_tenant()
    turn_id = await add_turn(app_engine, tenant)
    caps = await caps_with_room(owner_engine, tenant.id, sandbox_room=Decimal(50))
    sandbox_before = await sandbox_sum(owner_engine, tenant.id)

    with pytest.raises(BudgetExceeded) as refused:
        await reserve(
            app_engine, context_of(tenant), turn_id=turn_id, amount_usd=Decimal(amount), caps=caps
        )

    assert refused.value.scope == "sandbox"
    assert await sandbox_sum(owner_engine, tenant.id) == sandbox_before
    assert await daily_sum(owner_engine) == daily_baseline


async def test_the_largest_amount_the_ledger_holds_is_accepted(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    make_tenant: MakeTenant,
    daily_baseline: Decimal,
) -> None:
    tenant = await make_tenant()
    turn_id = await add_turn(app_engine, tenant)
    caps = await caps_with_room(owner_engine, tenant.id, sandbox_room=Decimal(50))

    reservation = await reserve(
        app_engine, context_of(tenant), turn_id=turn_id, amount_usd=MAX_RESERVATION_USD, caps=caps
    )

    assert reservation.amount_usd == Decimal(10)
