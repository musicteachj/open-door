"""The AI budget ledger (ADR 0011): reserve before each model call, settle after it.

Two insert-only ledgers hold the money. `ai_spend` is the sandbox's own, under row-level security.
`ai_spend_daily` is every sandbox together, for one UTC day. A reservation is the most a call could
cost; it is added only if both ledgers' sums stay under their caps. After the call, a `settle` row
of (actual - reserved) brings both sums to the real cost. A task that crashes never settles, so its
reservation stays counted, which errs toward spending less.

Two transaction-scoped advisory locks make "sum, then insert" atomic across API tasks: the sandbox's
key first, then the day's, always in that order so two reservations can't wait on each other. They
are released at commit or rollback, so they stay correct behind a connection pooler. A session-level
advisory lock would stay on its pooled connection for the next user, so none is used here.

A monthly budget (`Caps.monthly`, from AI_MONTHLY_BUDGET_USD) paces the daily ledger. Today's room
is `min(AI_DAILY_BUDGET_USD, allowance_today)`, where the allowance (app/ai/pacing.py) is a share
of what the month's earlier rows leave. The month's rows are the same insert-only `ai_spend_daily`
rows, settled costs and open reservations alike, so a reservation that is never settled counts at
its full amount for the rest of the month. Without a monthly budget only the daily cap applies.

The day lock stays the only lock. A reservation made just after UTC midnight can miss the
reservations still waiting on the previous day's lock (one per request in flight at midnight), each
within that day's allowance, so the month's sum can be short by those (ADR 0011).
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from sqlalchemy import insert, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from app.ai.pacing import MonthlyBudget, allowance_today_usd
from app.core.config import Settings
from app.db.locks import BUDGET_DAY_NS, BUDGET_TENANT_NS
from app.db.models import AiSpend, AiSpendDaily
from app.db.tenancy import TenantContext, tenant_session

# The locks' namespaces are listed in one place, app/db/locks.py.
# Both are computed in SQL, from the same clock as the daily table's default and its check, so the
# lock's key, the sum, and the row all name the same UTC day. `now()` is the transaction's start,
# so it can't change between them.
TAKE_TENANT_LOCK = text(
    f"SELECT pg_advisory_xact_lock({BUDGET_TENANT_NS}, hashtext(CAST(:tenant_id AS text)))"
)
TAKE_DAY_LOCK = text(
    f"SELECT pg_advisory_xact_lock({BUDGET_DAY_NS},"
    " (now() AT TIME ZONE 'UTC')::date - DATE '1970-01-01')"
)
SANDBOX_SUM = text("SELECT coalesce(sum(amount_usd), 0) FROM ai_spend WHERE tenant_id = :tenant_id")
DAY_SUM = text(
    "SELECT coalesce(sum(amount_usd), 0) FROM ai_spend_daily"
    " WHERE day = (now() AT TIME ZONE 'UTC')::date"
)
# The month's rows dated before today, and today's, with today's date, all from the database's UTC
# clock. An empty month still returns one row (the join is on `today`), with zeros.
MONTH_SUMS = text(
    """
    WITH today AS (SELECT (now() AT TIME ZONE 'UTC')::date AS d)
    SELECT today.d,
           coalesce(sum(s.amount_usd) FILTER (WHERE s.day < today.d), 0),
           coalesce(sum(s.amount_usd) FILTER (WHERE s.day = today.d), 0)
    FROM today LEFT JOIN ai_spend_daily s
      ON s.day >= date_trunc('month', today.d)::date AND s.day <= today.d
    GROUP BY today.d
    """
)


# The most one ledger row may hold: both ledgers check `amount_usd BETWEEN -10 AND 10` (migration
# 0008). The caps have no upper bound, so without this a larger reservation would fail with a raw
# integrity error. It is refused as over budget instead. One call's worst case is under $1.
MAX_RESERVATION_USD = Decimal(10)


@dataclass(frozen=True)
class Caps:
    sandbox_usd: Decimal
    daily_usd: Decimal
    monthly: MonthlyBudget | None = None

    @classmethod
    def from_settings(cls, settings: Settings) -> "Caps":
        monthly = (
            None
            if settings.ai_monthly_budget_usd is None
            else MonthlyBudget(
                budget_usd=settings.ai_monthly_budget_usd,
                multiplier=settings.ai_pacing_multiplier,
                floor_usd=settings.ai_daily_floor_usd,
            )
        )
        return cls(
            sandbox_usd=settings.ai_sandbox_budget_usd,
            daily_usd=settings.ai_daily_budget_usd,
            monthly=monthly,
        )


@dataclass(frozen=True)
class DayRoom:
    """What today's rows may add up to, what they add up to now, and what the month has left."""

    limit_usd: Decimal
    spent_today_usd: Decimal
    # None when there is no monthly budget.
    month_remaining_usd: Decimal | None


async def day_room(db: AsyncSession | AsyncConnection, caps: Caps) -> DayRoom:
    """Read today's room: the one reading `reserve`, `budget_state`, and the availability flag
    share. The limit is the daily cap, or the paced allowance when that is lower."""
    today, before_usd, today_usd = (await db.execute(MONTH_SUMS)).one()
    if caps.monthly is None:
        return DayRoom(caps.daily_usd, today_usd, None)
    allowance = allowance_today_usd(caps.monthly, spent_before_today_usd=before_usd, today=today)
    return DayRoom(
        limit_usd=min(caps.daily_usd, allowance),
        spent_today_usd=today_usd,
        month_remaining_usd=caps.monthly.budget_usd - before_usd - today_usd,
    )


class BudgetExceeded(Exception):  # noqa: N818
    """The reservation would take the sandbox, or the demo's day, over its cap."""

    def __init__(self, scope: Literal["sandbox", "daily"]) -> None:
        super().__init__(f"the {scope} budget is used up")
        self.scope = scope


# What a ledger row paid for. Only a turn's row has a turn_id (migration 0013).
type SpendPurpose = Literal["turn", "case_screen", "case_summary"]


@dataclass(frozen=True)
class Reservation:
    # None for a case's screening or summary: the ledger tells no one which case it was for.
    turn_id: UUID | None
    tenant_id: UUID
    amount_usd: Decimal
    # The UTC day the reservation was dated. Its settle goes on the same day, even past midnight.
    day: date
    purpose: SpendPurpose = "turn"


@dataclass(frozen=True)
class BudgetState:
    """How much room is left. A settle that cost more than its reservation can take a remaining
    amount below zero."""

    sandbox_remaining_usd: Decimal
    daily_remaining_usd: Decimal
    # None when there is no monthly budget.
    month_remaining_usd: Decimal | None = None

    @property
    def sandbox_reached(self) -> bool:
        return self.sandbox_remaining_usd <= 0

    @property
    def daily_reached(self) -> bool:
        return self.daily_remaining_usd <= 0


async def reserve(
    engine: AsyncEngine,
    ctx: TenantContext,
    *,
    turn_id: UUID | None,
    amount_usd: Decimal,
    caps: Caps,
    purpose: SpendPurpose = "turn",
) -> Reservation:
    """Reserve `amount_usd` in both ledgers, or raise BudgetExceeded and write nothing.

    A turn's reservation needs its turn, which must already be committed: the spend rows point at
    it. A case's (`case_screen`, `case_summary`) has no turn and no case ID.
    """
    if ctx.tenant_id is None:
        raise ValueError("a reservation needs a tenant")
    if (purpose == "turn") != (turn_id is not None):
        raise ValueError("only a turn's reservation has a turn")
    if amount_usd <= 0:
        raise ValueError("a reservation must be positive")
    if amount_usd > MAX_RESERVATION_USD:
        # More than the ledger can hold in one row is more than any sandbox may spend on one call.
        raise BudgetExceeded("sandbox")
    tenant_id = ctx.tenant_id
    async with tenant_session(engine, ctx) as session:
        await session.execute(TAKE_TENANT_LOCK, {"tenant_id": str(tenant_id)})
        await session.execute(TAKE_DAY_LOCK)
        sandbox_spent: Decimal = (
            await session.execute(SANDBOX_SUM, {"tenant_id": tenant_id})
        ).scalar_one()
        room = await day_room(session, caps)
        # The sandbox is checked first, so a visitor at their own cap is told so, not that the
        # demo is full.
        if sandbox_spent + amount_usd > caps.sandbox_usd:
            raise BudgetExceeded("sandbox")
        if room.spent_today_usd + amount_usd > room.limit_usd:
            raise BudgetExceeded("daily")
        await session.execute(
            insert(AiSpend).values(
                tenant_id=tenant_id,
                turn_id=turn_id,
                purpose=purpose,
                kind="reserve",
                amount_usd=amount_usd,
            )
        )
        day = (
            await session.execute(
                insert(AiSpendDaily)
                .values(kind="reserve", amount_usd=amount_usd)
                .returning(AiSpendDaily.day)
            )
        ).scalar_one()
    return Reservation(
        turn_id=turn_id, tenant_id=tenant_id, amount_usd=amount_usd, day=day, purpose=purpose
    )


async def settle(
    engine: AsyncEngine,
    ctx: TenantContext,
    reservation: Reservation,
    *,
    actual_usd: Decimal,
) -> None:
    """Add a `settle` row of (actual - reserved) to both ledgers.

    It can be positive, when a fallback model cost more than the one reserved for. It takes no
    lock: it adds a difference, and a call that has already been paid for can't be refused.
    """
    if ctx.tenant_id != reservation.tenant_id:
        raise ValueError("a reservation can be settled only in the sandbox that made it")
    difference_usd = actual_usd - reservation.amount_usd
    async with tenant_session(engine, ctx) as session:
        await session.execute(
            insert(AiSpend).values(
                tenant_id=reservation.tenant_id,
                turn_id=reservation.turn_id,
                purpose=reservation.purpose,
                kind="settle",
                amount_usd=difference_usd,
            )
        )
        # Dated by the reservation, not by now: a turn that crosses midnight settles on the day it
        # reserved on. The table's check allows a settle dated yesterday, and nothing older.
        await session.execute(
            insert(AiSpendDaily).values(
                kind="settle", amount_usd=difference_usd, day=reservation.day
            )
        )


async def _session_tenant_id(db: AsyncSession) -> UUID:
    tenant_id: UUID | None = (await db.execute(text("SELECT app.current_tenant_id()"))).scalar_one()
    if tenant_id is None:
        raise ValueError("the budget state needs a session scoped to a tenant")
    return tenant_id


async def sandbox_spent_usd(db: AsyncSession) -> Decimal:
    """What the session's sandbox has spent, as one sum of its ledger. It reads no daily ledger."""
    tenant_id = await _session_tenant_id(db)
    spent: Decimal = (await db.execute(SANDBOX_SUM, {"tenant_id": tenant_id})).scalar_one()
    return spent


async def budget_state(db: AsyncSession, caps: Caps) -> BudgetState:
    """The room left in the sandbox (the session's tenant) and in today's demo-wide budget.

    A session with no tenant sees no spend, which would read as a full budget, so it fails.
    """
    sandbox_spent = await sandbox_spent_usd(db)
    room = await day_room(db, caps)
    return BudgetState(
        sandbox_remaining_usd=caps.sandbox_usd - sandbox_spent,
        daily_remaining_usd=room.limit_usd - room.spent_today_usd,
        month_remaining_usd=room.month_remaining_usd,
    )
