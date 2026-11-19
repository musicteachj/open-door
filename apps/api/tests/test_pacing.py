"""The monthly budget's pacing: a pure calculation, so no database."""

from datetime import date, timedelta
from decimal import Decimal

from app.ai.pacing import MonthlyBudget, allowance_today_usd, days_left_in_month

MONTH = MonthlyBudget(budget_usd=Decimal("20"), multiplier=Decimal("3"), floor_usd=Decimal("1.00"))


def test_days_left_counts_today() -> None:
    assert days_left_in_month(date(2026, 11, 1)) == 30
    assert days_left_in_month(date(2026, 11, 30)) == 1
    assert days_left_in_month(date(2026, 12, 1)) == 31
    assert days_left_in_month(date(2027, 2, 1)) == 28
    assert days_left_in_month(date(2028, 2, 29)) == 1


def test_the_first_of_the_month_gets_three_even_shares() -> None:
    allowance = allowance_today_usd(
        MONTH, spent_before_today_usd=Decimal(0), today=date(2026, 11, 1)
    )
    assert allowance == Decimal("2.000000")


def test_the_share_rounds_down_to_the_ledgers_places() -> None:
    allowance = allowance_today_usd(
        MONTH, spent_before_today_usd=Decimal(0), today=date(2026, 12, 1)
    )
    assert allowance == Decimal("1.935483")


def test_the_floor_applies_when_the_share_is_small() -> None:
    allowance = allowance_today_usd(
        MONTH, spent_before_today_usd=Decimal("18.50"), today=date(2026, 11, 2)
    )
    assert allowance == Decimal("1.000000")


def test_never_more_than_is_left() -> None:
    allowance = allowance_today_usd(
        MONTH, spent_before_today_usd=Decimal("19.60"), today=date(2026, 11, 2)
    )
    assert allowance == Decimal("0.400000")


def test_the_last_day_may_spend_everything_left() -> None:
    allowance = allowance_today_usd(
        MONTH, spent_before_today_usd=Decimal("12.75"), today=date(2026, 11, 30)
    )
    assert allowance == Decimal("7.250000")


def test_an_overspent_month_allows_nothing() -> None:
    allowance = allowance_today_usd(
        MONTH, spent_before_today_usd=Decimal("20.30"), today=date(2026, 11, 9)
    )
    assert allowance == Decimal(0)


def test_a_zero_budget_allows_nothing() -> None:
    off = MonthlyBudget(Decimal(0), Decimal(3), Decimal("1.00"))
    assert allowance_today_usd(
        off, spent_before_today_usd=Decimal(0), today=date(2026, 11, 1)
    ) == Decimal(0)


def test_the_cleanup_rule_keeps_every_day_of_the_month() -> None:
    # The cleanup deletes rows with `day < today - 30` (app/jobs/cleanup.py:54-56).
    day = date(2024, 1, 1)
    while day <= date(2028, 12, 31):
        assert day.replace(day=1) >= day - timedelta(days=30)
        day += timedelta(days=1)
