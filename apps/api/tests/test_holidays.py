"""The company holiday calendar. Every expected date was worked out by hand from a calendar."""

from datetime import date

import pytest

from app.domain.holidays import CompanyHoliday, holidays_for

# 2026: January 1 is a Thursday, and July 4 a Saturday, so it is observed on Friday July 3. May 31
# is a Sunday, so Memorial Day, the last Monday in May, is May 25. September 1 is a Tuesday, so
# Labor Day is September 7. November 1 is a Sunday, so the fourth Thursday is November 26.
# Christmas is a Friday.
OAKLAND_AND_AUSTIN_2026 = [
    CompanyHoliday(date(2026, 1, 1), "New Year's Day"),
    CompanyHoliday(date(2026, 5, 25), "Memorial Day"),
    CompanyHoliday(date(2026, 7, 3), "Independence Day (observed)"),
    CompanyHoliday(date(2026, 9, 7), "Labor Day"),
    CompanyHoliday(date(2026, 11, 26), "Thanksgiving"),
    CompanyHoliday(date(2026, 12, 25), "Christmas Day"),
]

DENVER_2026 = [
    CompanyHoliday(date(2026, 1, 1), "New Year's Day"),
    CompanyHoliday(date(2026, 5, 25), "Memorial Day"),
    CompanyHoliday(date(2026, 7, 3), "Independence Day (observed)"),
    CompanyHoliday(date(2026, 9, 7), "Labor Day"),
    CompanyHoliday(date(2026, 11, 26), "Thanksgiving"),
    CompanyHoliday(date(2026, 11, 27), "Day after Thanksgiving"),
    CompanyHoliday(date(2026, 12, 25), "Christmas Day"),
]

# 2027: July 4 is a Sunday, so it is observed on Monday July 5. Christmas is a Saturday, so it is
# observed on Friday December 24. January 1, 2028 is a Saturday, so New Year's Day 2028 is
# observed on Friday December 31, 2027.
DENVER_2027 = [
    CompanyHoliday(date(2027, 1, 1), "New Year's Day"),
    CompanyHoliday(date(2027, 5, 31), "Memorial Day"),
    CompanyHoliday(date(2027, 7, 5), "Independence Day (observed)"),
    CompanyHoliday(date(2027, 9, 6), "Labor Day"),
    CompanyHoliday(date(2027, 11, 25), "Thanksgiving"),
    CompanyHoliday(date(2027, 11, 26), "Day after Thanksgiving"),
    CompanyHoliday(date(2027, 12, 24), "Christmas Day (observed)"),
    CompanyHoliday(date(2027, 12, 31), "New Year's Day (observed)"),
]

# 2028, a leap year: its New Year's Day was observed in 2027, so it has none. July 4 is a Tuesday
# and Christmas a Monday, so neither moves.
DENVER_2028 = [
    CompanyHoliday(date(2028, 5, 29), "Memorial Day"),
    CompanyHoliday(date(2028, 7, 4), "Independence Day"),
    CompanyHoliday(date(2028, 9, 4), "Labor Day"),
    CompanyHoliday(date(2028, 11, 23), "Thanksgiving"),
    CompanyHoliday(date(2028, 11, 24), "Day after Thanksgiving"),
    CompanyHoliday(date(2028, 12, 25), "Christmas Day"),
]


def test_denver_closes_seven_days_in_2026() -> None:
    assert list(holidays_for("den", 2026)) == DENVER_2026


@pytest.mark.parametrize("location_code", ["oak", "aus", "atl"])
def test_oakland_austin_and_atlanta_close_six_days_in_2026(location_code: str) -> None:
    # Everything Denver closes except the day after Thanksgiving.
    assert list(holidays_for(location_code, 2026)) == OAKLAND_AND_AUSTIN_2026


def test_sunday_and_saturday_holidays_move_to_the_nearest_weekday_in_2027() -> None:
    assert list(holidays_for("den", 2027)) == DENVER_2027


def test_2028_has_no_new_years_day_because_2027_observed_it() -> None:
    assert list(holidays_for("den", 2028)) == DENVER_2028


@pytest.mark.parametrize("location_code", ["den", "oak", "aus", "atl"])
def test_an_observed_date_belongs_to_the_year_it_falls_in(location_code: str) -> None:
    in_2027 = holidays_for(location_code, 2027)
    in_2028 = holidays_for(location_code, 2028)

    assert in_2027[-1] == CompanyHoliday(date(2027, 12, 31), "New Year's Day (observed)")
    assert [holiday.name for holiday in in_2028 if "New Year" in holiday.name] == []


def test_an_unknown_location_is_an_error_not_an_empty_calendar() -> None:
    with pytest.raises(ValueError, match="Unknown location code 'nyc'"):
        holidays_for("nyc", 2026)
