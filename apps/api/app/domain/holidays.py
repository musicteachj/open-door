"""The company holiday calendar: the days each location is closed, year by year.

Pure, like everything under app.domain: no framework imports, so the time-off engine can rely on
the same rules in Phase 5. The seed generator stores these dates in each sandbox's holidays table.

Every location closes on six holidays. One that falls on a Saturday is observed on the Friday
before, and one on a Sunday on the Monday after. Denver HQ also closes the day after Thanksgiving.

A year's calendar is the days the company is closed in that calendar year. When New Year's Day
falls on a Saturday, as on 2028-01-01, the company closes on Friday 2027-12-31, so that date is in
2027's calendar and 2028's has no New Year's Day. A stored calendar then never misses a closed
day, and never lists one outside its year.
"""

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

LOCATION_CODES = frozenset({"den", "oak", "aus", "atl"})
# The one difference between locations, so the time-off engine has a real one to get right.
CLOSED_THE_DAY_AFTER_THANKSGIVING = frozenset({"den"})


@dataclass(frozen=True, slots=True)
class CompanyHoliday:
    """A day the company is closed. `holiday_date` is the observed date, not the actual one."""

    holiday_date: date
    name: str


def holidays_for(location_code: str, year: int) -> tuple[CompanyHoliday, ...]:
    """The days the location is closed in `year`, in date order."""
    if location_code not in LOCATION_CODES:
        msg = f"Unknown location code {location_code!r}: expected one of {sorted(LOCATION_CODES)}"
        raise ValueError(msg)
    thanksgiving = _nth_weekday(year, 11, calendar.THURSDAY, 4)
    holidays = [
        _observed("New Year's Day", date(year, 1, 1)),
        _observed("Memorial Day", _last_weekday(year, 5, calendar.MONDAY)),
        _observed("Independence Day", date(year, 7, 4)),
        _observed("Labor Day", _nth_weekday(year, 9, calendar.MONDAY, 1)),
        _observed("Thanksgiving", thanksgiving),
        _observed("Christmas Day", date(year, 12, 25)),
        # Next year's New Year's Day is observed this year when it falls on a Saturday.
        _observed("New Year's Day", date(year + 1, 1, 1)),
    ]
    if location_code in CLOSED_THE_DAY_AFTER_THANKSGIVING:
        holidays.append(CompanyHoliday(thanksgiving + timedelta(days=1), "Day after Thanksgiving"))
    in_year = (holiday for holiday in holidays if holiday.holiday_date.year == year)
    return tuple(sorted(in_year, key=lambda holiday: holiday.holiday_date))


def _observed(name: str, actual: date) -> CompanyHoliday:
    """A Saturday holiday moves to the Friday before, and a Sunday one to the Monday after."""
    if actual.weekday() == calendar.SATURDAY:
        return CompanyHoliday(actual - timedelta(days=1), f"{name} (observed)")
    if actual.weekday() == calendar.SUNDAY:
        return CompanyHoliday(actual + timedelta(days=1), f"{name} (observed)")
    return CompanyHoliday(actual, name)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """The nth Monday, Tuesday, and so on of a month: Labor Day is the first Monday."""
    first = date(year, month, 1)
    return first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    """The last Monday, Tuesday, and so on of a month: Memorial Day is the last Monday."""
    last = date(year, month, calendar.monthrange(year, month)[1])
    return last - timedelta(days=(last.weekday() - weekday) % 7)
