"""Counting a request's days. Every expected value was worked out by hand from a calendar."""

from collections.abc import Iterable
from datetime import date

import pytest

from app.domain.holidays import holidays_for
from app.domain.timeoff.counting import Skipped, count_days
from app.domain.timeoff.model import Person, Schedule
from app.domain.timeoff.rules import Rule

MON_TO_FRI = Schedule(weekdays=frozenset({1, 2, 3, 4, 5}))
WED_TO_SUN = Schedule(weekdays=frozenset({3, 4, 5, 6, 7}))


def person(schedule: Schedule = MON_TO_FRI) -> Person:
    return Person(
        employment_type="salaried", state="CA", hire_date=date(2020, 1, 6), schedule=schedule
    )


def holiday_map(code: str, *years: int) -> dict[date, str]:
    return {h.holiday_date: h.name for year in years for h in holidays_for(code, year)}


def rule_pairs(counted_rules: Iterable[Rule]) -> set[tuple[str, str]]:
    return {(rule.section_id, rule.rule) for rule in counted_rules}


def test_a_week_with_a_monday_holiday_counts_four() -> None:
    # September 2026: the 7th is a Monday (Labor Day), so the 7th to the 11th is Mon to Fri.
    # Mon is a holiday, Tue 8 to Fri 11 count: 4 days.
    result = count_days(
        person(), date(2026, 9, 7), date(2026, 9, 11), {date(2026, 9, 7): "Labor Day"}
    )
    assert result.counted == (
        date(2026, 9, 8),
        date(2026, 9, 9),
        date(2026, 9, 10),
        date(2026, 9, 11),
    )
    assert result.skipped == (Skipped(day=date(2026, 9, 7), reason="Labor Day"),)
    assert rule_pairs(result.rules) == {("3.1", "scheduled-days"), ("4.2", "holidays-not-charged")}


def test_a_wednesday_to_sunday_schedule_counts_five_in_a_week() -> None:
    # October 2026: the 12th is a Monday. Mon 12 and Tue 13 are not scheduled; Wed 14 to Sun 18
    # are: 5 days. No holiday that week.
    result = count_days(person(WED_TO_SUN), date(2026, 10, 12), date(2026, 10, 18), {})
    assert result.counted == tuple(date(2026, 10, d) for d in (14, 15, 16, 17, 18))
    assert result.skipped == (
        Skipped(day=date(2026, 10, 12), reason="not scheduled"),
        Skipped(day=date(2026, 10, 13), reason="not scheduled"),
    )
    assert rule_pairs(result.rules) == {("3.1", "scheduled-days")}


def test_thanksgiving_week_in_denver_counts_three() -> None:
    # November 2026: the 23rd is a Monday; Thanksgiving is Thu 26, and Denver also closes Fri 27.
    # Mon 23, Tue 24, Wed 25 count: 3 days.
    holidays = {date(2026, 11, 26): "Thanksgiving", date(2026, 11, 27): "Day after Thanksgiving"}
    result = count_days(person(), date(2026, 11, 23), date(2026, 11, 27), holidays)
    assert result.counted == (date(2026, 11, 23), date(2026, 11, 24), date(2026, 11, 25))
    assert result.skipped == (
        Skipped(day=date(2026, 11, 26), reason="Thanksgiving"),
        Skipped(day=date(2026, 11, 27), reason="Day after Thanksgiving"),
    )
    assert ("4.2", "holidays-not-charged") in rule_pairs(result.rules)


def test_thanksgiving_week_in_oakland_counts_four() -> None:
    # Same week, one closure (Thu 26): Mon 23, Tue 24, Wed 25, Fri 27 count: 4 days.
    result = count_days(
        person(), date(2026, 11, 23), date(2026, 11, 27), {date(2026, 11, 26): "Thanksgiving"}
    )
    assert result.counted == (
        date(2026, 11, 23),
        date(2026, 11, 24),
        date(2026, 11, 25),
        date(2026, 11, 27),
    )
    assert result.skipped == (Skipped(day=date(2026, 11, 26), reason="Thanksgiving"),)


def test_the_observed_new_years_day_across_the_year_end_is_skipped_by_name() -> None:
    # January 1, 2028 is a Saturday, so New Year's Day is observed on Friday, December 31, 2027.
    # December 27, 2027 is a Monday. Mon 27 to Thu 30 count: 4 days. Fri 31 is the holiday.
    # Sat Jan 1 and Sun Jan 2 are not scheduled.
    holidays = holiday_map("oak", 2027, 2028)
    result = count_days(person(), date(2027, 12, 27), date(2028, 1, 2), holidays)
    assert result.counted == tuple(date(2027, 12, d) for d in (27, 28, 29, 30))
    assert result.skipped == (
        Skipped(day=date(2027, 12, 31), reason="New Year's Day (observed)"),
        Skipped(day=date(2028, 1, 1), reason="not scheduled"),
        Skipped(day=date(2028, 1, 2), reason="not scheduled"),
    )
    assert rule_pairs(result.rules) == {
        ("3.1", "scheduled-days"),
        ("4.2", "holidays-not-charged"),
    }


def test_a_holiday_on_an_unscheduled_day_reads_not_scheduled() -> None:
    # Memorial Day 2026 is Monday, May 25, and Leo (Wed to Sun) does not work Mondays. Only Mon.
    result = count_days(
        person(WED_TO_SUN),
        date(2026, 5, 25),
        date(2026, 5, 25),
        {date(2026, 5, 25): "Memorial Day"},
    )
    assert result.counted == ()
    assert result.skipped == (Skipped(day=date(2026, 5, 25), reason="not scheduled"),)
    assert rule_pairs(result.rules) == {("3.1", "scheduled-days")}


def test_a_range_with_no_counted_day_is_empty() -> None:
    # October 17, 2026 is a Saturday and the 18th a Sunday: neither is a Mon to Fri day.
    result = count_days(person(), date(2026, 10, 17), date(2026, 10, 18), {})
    assert result.counted == ()
    assert [s.day for s in result.skipped] == [date(2026, 10, 17), date(2026, 10, 18)]


def test_a_one_day_range_on_a_scheduled_day_counts_one() -> None:
    # October 14, 2026 is a Wednesday.
    result = count_days(person(), date(2026, 10, 14), date(2026, 10, 14), {})
    assert result.counted == (date(2026, 10, 14),)
    assert result.skipped == ()


def test_an_end_before_the_start_is_refused() -> None:
    with pytest.raises(ValueError, match="before it starts"):
        count_days(person(), date(2026, 10, 15), date(2026, 10, 14), {})
