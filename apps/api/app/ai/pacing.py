"""The monthly AI budget, paced by day.

Each UTC day may spend a share of what is left of the month, so one busy day can't use the whole
month and a quiet month still has room at its end:

    left_this_month = budget - every ledger row dated earlier this month (settled costs and open
                      reservations)
    allowance_today = min(left_this_month,
                          max(multiplier * left_this_month / days_left_including_today, floor))

The multiplier lets a day spend more than an even share (a busy day is expected), and the floor
keeps the last days of a nearly spent month usable. The allowance is rounded down to the ledger's
six places, so it never admits more than the formula.

Days and months are UTC. The caller passes the database's date (`now() AT TIME ZONE 'UTC'`), never
the application's clock, so the date matches the one the ledger rows carry.
"""

from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_FLOOR, Decimal

from app.ai.pricing import LEDGER_PLACES


@dataclass(frozen=True)
class MonthlyBudget:
    budget_usd: Decimal
    multiplier: Decimal
    floor_usd: Decimal


def days_left_in_month(today: date) -> int:
    """The days from `today` to the month's last day, today included."""
    return monthrange(today.year, today.month)[1] - today.day + 1


def allowance_today_usd(
    budget: MonthlyBudget, *, spent_before_today_usd: Decimal, today: date
) -> Decimal:
    """What today's rows may add up to, from the month's rows dated before today."""
    left = budget.budget_usd - spent_before_today_usd
    if left <= 0:
        return Decimal(0)
    paced = budget.multiplier * left / days_left_in_month(today)
    return min(left, max(paced, budget.floor_usd)).quantize(LEDGER_PLACES, rounding=ROUND_FLOOR)
