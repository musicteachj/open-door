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
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from sqlalchemy import insert, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

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


# The most one ledger row may hold: both ledgers check `amount_usd BETWEEN -10 AND 10` (migration
# 0008). The caps have no upper bound, so without this a larger reservation would fail with a raw
# integrity error. It is refused as over budget instead. One call's worst case is under $1.
MAX_RESERVATION_USD = Decimal(10)


@dataclass(frozen=True)
class Caps:
    sandbox_usd: Decimal
    daily_usd: Decimal

    @classmethod
    def from_settings(cls, settings: Settings) -> "Caps":
        return cls(
            sandbox_usd=settings.ai_sandbox_budget_usd, daily_usd=settings.ai_daily_budget_usd
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
        daily_spent: Decimal = (await session.execute(DAY_SUM)).scalar_one()
        # The sandbox is checked first, so a visitor at their own cap is told so, not that the
        # demo is full.
        if sandbox_spent + amount_usd > caps.sandbox_usd:
            raise BudgetExceeded("sandbox")
        if daily_spent + amount_usd > caps.daily_usd:
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


async def budget_state(db: AsyncSession, caps: Caps) -> BudgetState:
    """The room left in the sandbox (the session's tenant) and in today's demo-wide budget.

    A session with no tenant sees no spend, which would read as a full budget, so it fails.
    """
    tenant_id: UUID | None = (await db.execute(text("SELECT app.current_tenant_id()"))).scalar_one()
    if tenant_id is None:
        raise ValueError("the budget state needs a session scoped to a tenant")
    sandbox_spent: Decimal = (await db.execute(SANDBOX_SUM, {"tenant_id": tenant_id})).scalar_one()
    daily_spent: Decimal = (await db.execute(DAY_SUM)).scalar_one()
    return BudgetState(
        sandbox_remaining_usd=caps.sandbox_usd - sandbox_spent,
        daily_remaining_usd=caps.daily_usd - daily_spent,
    )
