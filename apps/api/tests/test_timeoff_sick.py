"""Sick leave years. Every expected value was worked out by hand from handbook 4.3 and addenda.

Calendar anchors: 2026-01-01 is a Thursday, so Oct 1 2026 is a Thursday, Mon Oct 19, Tue Oct 20
(today in the used-and-booked fixture), Wed Dec 30 and Thu Dec 31 2026; Fri Jan 1 2027, Sat Jan 2,
Sun Jan 3, Mon Jan 4 2027. Grants: TX and GA 2,400; CA the larger of 2,400 and 5 x 480 = 2,400;
CO 2,880.
"""

from datetime import date

import pytest

from app.domain.timeoff.model import Person, Request, RequestStatus, Schedule, State
from app.domain.timeoff.rules import RULES, Rule
from app.domain.timeoff.sick import sick_balance, sick_years

MON_TO_FRI = Schedule(weekdays=frozenset({1, 2, 3, 4, 5}))


def person(state: State = "TX", hire: date = date(2020, 1, 6)) -> Person:
    return Person("salaried", state, hire, MON_TO_FRI)


def sick(
    ident: str,
    start: date,
    end: date,
    status: RequestStatus = "recorded",
    partial: int | None = None,
) -> Request:
    return Request(ident, "sick", start, end, partial, status)


@pytest.mark.parametrize(
    ("state", "grant", "section"),
    [("TX", 2400, "4.3"), ("GA", 2400, "4.3"), ("CO", 2880, "CO-4.3"), ("CA", 2400, "CA-4.3")],
)
def test_the_yearly_grant_by_state(state: State, grant: int, section: str) -> None:
    # TX/GA 40 hours = 2,400 (4.3); CO 48 hours = 2,880 (CO-4.3); CA max(2,400, 5 x 480 = 2,400).
    result = sick_balance(person(state), (), {}, 2026, date(2026, 10, 20))
    assert result.year == 2026
    assert result.granted_minutes == grant
    assert result.available_minutes == grant
    assert result.rules == (Rule(section, "sick-grant"),)


def test_a_mid_year_hire_gets_the_grant_in_the_hire_year_and_nothing_before() -> None:
    # Hired Mon Jun 1 2026: 2026 grant 2,400 on the hire date; 2025 is before the hire year, 0;
    # 2027 is a full year, 2,400.
    hire = person("TX", date(2026, 6, 1))
    today = date(2026, 10, 20)
    assert sick_balance(hire, (), {}, 2026, today).granted_minutes == 2400
    assert sick_balance(hire, (), {}, 2025, today).granted_minutes == 0
    assert sick_balance(hire, (), {}, 2027, today).granted_minutes == 2400


def test_used_and_booked_around_today_with_today_counted_as_used() -> None:
    # Today Tue Oct 20 2026. Recorded Mon Oct 19 and Tue Oct 20: 2 x 480 = 960 used (today
    # counts). Recorded Wed Oct 21 and Thu Oct 22: 960 booked. Recorded 120 partial on Mon Oct 26:
    # 120 booked, so booked 1,080. Canceled Wed Oct 28 counts nowhere.
    # Available 2,400 - 960 - 1,080 = 360.
    requests = (
        sick("a", date(2026, 10, 19), date(2026, 10, 20)),
        sick("b", date(2026, 10, 21), date(2026, 10, 22)),
        sick("c", date(2026, 10, 26), date(2026, 10, 26), partial=120),
        sick("d", date(2026, 10, 28), date(2026, 10, 28), "canceled"),
    )
    result = sick_balance(person(), requests, {}, 2026, date(2026, 10, 20))
    assert result.used_minutes == 960
    assert result.booked_minutes == 1080
    assert result.available_minutes == 360


def test_pto_requests_do_not_touch_sick_leave() -> None:
    requests = (Request("p", "pto", date(2026, 10, 19), date(2026, 10, 20), None, "approved"),)
    result = sick_balance(person(), requests, {}, 2026, date(2026, 10, 20))
    assert (result.used_minutes, result.booked_minutes) == (0, 0)


def test_a_request_across_december_31_is_split_by_year() -> None:
    # Wed Dec 30 2026 to Mon Jan 4 2027, Monday to Friday, Jan 1 a holiday.
    # Dec 30 and 31 count in 2026 (960); Jan 1 holiday; Jan 2 and 3 not scheduled; Jan 4 counts in
    # 2027 (480). Today Tue Dec 15 2026: all booked. 2026 available 2,400 - 960 = 1,440;
    # 2027 available 2,400 - 480 = 1,920.
    holidays = {date(2027, 1, 1): "New Year's Day"}
    requests = (sick("a", date(2026, 12, 30), date(2027, 1, 4)),)
    today = date(2026, 12, 15)
    y2026 = sick_balance(person(), requests, holidays, 2026, today)
    y2027 = sick_balance(person(), requests, holidays, 2027, today)
    assert (y2026.used_minutes, y2026.booked_minutes, y2026.available_minutes) == (0, 960, 1440)
    assert (y2027.used_minutes, y2027.booked_minutes, y2027.available_minutes) == (0, 480, 1920)
    assert tuple(y.year for y in sick_years(person(), requests, holidays, today)) == (2026, 2027)


def test_sick_years_is_one_year_when_no_day_falls_next_year() -> None:
    # Wed Dec 30 and Thu Dec 31 2026 only: nothing in 2027.
    requests = (sick("a", date(2026, 12, 30), date(2026, 12, 31)),)
    years = sick_years(person(), requests, {}, date(2026, 12, 15))
    assert tuple(y.year for y in years) == (2026,)


def test_sick_years_ignores_next_year_days_that_do_not_count() -> None:
    # Fri Jan 1 2027 is a holiday and Sat Jan 2 is not scheduled: nothing counts in 2027.
    requests = (sick("a", date(2027, 1, 1), date(2027, 1, 2)),)
    years = sick_years(person(), requests, {date(2027, 1, 1): "New Year's Day"}, date(2026, 12, 15))
    assert tuple(y.year for y in years) == (2026,)


def test_sick_years_ignores_canceled_next_year_requests() -> None:
    requests = (sick("a", date(2027, 1, 4), date(2027, 1, 4), "canceled"),)
    assert tuple(y.year for y in sick_years(person(), requests, {}, date(2026, 12, 15))) == (2026,)


def test_rules_cite_the_state_section() -> None:
    years = sick_years(person("CO"), (), {}, date(2026, 10, 20))
    assert years[0].rules == (Rule("CO-4.3", "sick-grant"),)
    assert RULES["scheduled-days"].section_id == "3.1"


def test_used_time_splits_by_year_across_a_year_boundary() -> None:
    # Recorded Wed 2026-12-30 to Mon 2027-01-04 (Jan 1 a holiday, Jan 2-3 not scheduled), today
    # Mon 2027-01-11: Dec 30, 31 = 960 used in 2026; Jan 4 = 480 used in 2027; nothing booked.
    requests = (sick("a", date(2026, 12, 30), date(2027, 1, 4)),)
    holidays = {date(2027, 1, 1): "New Year's Day"}
    today = date(2027, 1, 11)
    y2026 = sick_balance(person(), requests, holidays, 2026, today)
    y2027 = sick_balance(person(), requests, holidays, 2027, today)
    assert (y2026.used_minutes, y2026.booked_minutes, y2026.available_minutes) == (960, 0, 1440)
    assert (y2027.used_minutes, y2027.booked_minutes, y2027.available_minutes) == (480, 0, 1920)
