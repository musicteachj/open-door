"""PTO balances. Every expected value was worked out by hand from handbook 4.1 and the calendar.

Calendar anchors: 2026-01-01 is a Thursday, so 2026-03-10 is a Tuesday (Jan 1 + 68 days, and
68 mod 7 = 5) and 2026-10-05 is a Monday (Oct 1 is a Thursday). Month-ends are the last days of
their months. Salaried staff earn 600 a month with a ceiling of 600 * 12 * 3 / 2 = 10,800;
hourly staff earn 480 with a ceiling of 480 * 12 * 3 / 2 = 8,640.
"""

from datetime import date

from app.domain.timeoff.model import Opening, Person, Request, RequestStatus, Schedule
from app.domain.timeoff.pto import pto_balance
from app.domain.timeoff.rules import RULES

MON_TO_FRI = Schedule(weekdays=frozenset({1, 2, 3, 4, 5}))
SALARIED = Person("salaried", "TX", date(2020, 1, 6), MON_TO_FRI)
HOURLY = Person("hourly", "TX", date(2020, 1, 6), MON_TO_FRI)
JAN_1 = date(2026, 1, 1)


def pto(
    ident: str, start: date, end: date, status: RequestStatus, partial: int | None = None
) -> Request:
    return Request(ident, "pto", start, end, partial, status)


def test_nine_month_ends_before_october_20() -> None:
    # Month-ends Jan 31 to Sep 30 = 9 x 600 = 5,400. Balance before the last earning is
    # 4,800 + 8 x 600 = 9,600, under the ceiling, so every month earns the full 600.
    # Earned 4,800 + 5,400 = 10,200; nothing taken. Next earning Oct 31: balance 10,200, room 600.
    result = pto_balance(SALARIED, Opening(JAN_1, 4800), (), {}, date(2026, 10, 20))
    assert result.earned_minutes == 10200
    assert (result.taken_minutes, result.booked_minutes, result.pending_minutes) == (0, 0, 0)
    assert result.available_minutes == 10200
    assert result.ceiling_minutes == 10800
    assert result.next_earning == date(2026, 10, 31)
    assert result.next_earning_minutes == 600
    assert result.rules == (RULES["pto-earning"], RULES["pto-ceiling"], RULES["pto-available"])


def test_october_31_counts_and_then_earning_is_paused_at_the_ceiling() -> None:
    # Ten month-ends Jan 31 to Oct 31: earned 4,800 + 6,000 = 10,800, exactly the ceiling.
    # Next, Nov 30: balance 10,800, room 0, so paused: no next earning.
    result = pto_balance(SALARIED, Opening(JAN_1, 4800), (), {}, date(2026, 10, 31))
    assert result.earned_minutes == 10800
    assert result.next_earning is None
    assert result.next_earning_minutes == 0


def test_the_ceiling_limits_one_month_then_use_lets_earning_resume() -> None:
    # Opening 10,500. Approved Tue Mar 10 and Wed Mar 11 (2 x 480 = 960), taken by Apr 15.
    # Jan 31: balance 10,500, room 300, earn 300 (10,800). Feb 28: balance 10,800, earn 0.
    # Mar 31: balance 10,800 - 960 = 9,840, room 960, earn 600.
    # Earned 10,500 + 300 + 600 = 11,400. Taken 960. Available 11,400 - 960 = 10,440.
    # Next Apr 30: balance 11,400 - 960 = 10,440, room 360, earn 360.
    requests = (pto("a", date(2026, 3, 10), date(2026, 3, 11), "approved"),)
    result = pto_balance(SALARIED, Opening(JAN_1, 10500), requests, {}, date(2026, 4, 15))
    assert result.earned_minutes == 11400
    assert result.taken_minutes == 960
    assert result.available_minutes == 10440
    assert result.next_earning == date(2026, 4, 30)
    assert result.next_earning_minutes == 360


def test_a_pending_request_does_not_free_room_at_the_ceiling() -> None:
    # Same as above with the March request pending: Mar 31 balance stays 10,800, earn 0.
    # Earned 10,500 + 300 = 10,800. Pending 960. Available 10,800 - 960 = 9,840.
    # Next Apr 30: balance 10,800, room 0, so paused. Approving the request later would change
    # March's earning to 600: a past month's earning follows the approvals.
    requests = (pto("a", date(2026, 3, 10), date(2026, 3, 11), "pending"),)
    result = pto_balance(SALARIED, Opening(JAN_1, 10500), requests, {}, date(2026, 4, 15))
    assert result.earned_minutes == 10800
    assert result.taken_minutes == 0
    assert result.pending_minutes == 960
    assert result.available_minutes == 9840
    assert result.next_earning is None
    assert result.next_earning_minutes == 0


def test_an_opening_above_the_ceiling_earns_nothing_and_is_not_reduced() -> None:
    # Opening 12,000 is over 10,800. Jan 31: room is negative, earn 0. Same for Feb 28.
    result = pto_balance(SALARIED, Opening(JAN_1, 12000), (), {}, date(2026, 2, 15))
    assert result.earned_minutes == 12000
    assert result.available_minutes == 12000
    assert result.next_earning is None


def test_hourly_earns_480_and_reaches_its_ceiling_of_8640() -> None:
    # Opening 480, today Mar 15: month-ends Jan 31 and Feb 28 = 2 x 480. Earned 1,440.
    # Next Mar 31: balance 1,440, earn 480.
    result = pto_balance(HOURLY, Opening(JAN_1, 480), (), {}, date(2026, 3, 15))
    assert result.earned_minutes == 1440
    assert result.ceiling_minutes == 8640
    assert result.next_earning == date(2026, 3, 31)
    assert result.next_earning_minutes == 480


def test_hourly_earning_stops_at_the_ceiling() -> None:
    # Opening 8,000. Jan 31: balance 8,000, room 640, earn 480 (8,480).
    # Feb 28: room 8,640 - 8,480 = 160, earn 160 (8,640). Earned 8,640.
    # Next Mar 31: balance 8,640, room 0, paused.
    result = pto_balance(HOURLY, Opening(JAN_1, 8000), (), {}, date(2026, 3, 15))
    assert result.earned_minutes == 8640
    assert result.next_earning is None


def test_a_june_30_hire_earns_on_june_30() -> None:
    # Hired Tue Jun 30 2026, opening 0 as of that date. Jun 30 >= Jun 30, so it earns 600.
    # Today Jul 15: earned 600. Next Jul 31: 600.
    person = Person("salaried", "TX", date(2026, 6, 30), MON_TO_FRI)
    result = pto_balance(person, Opening(date(2026, 6, 30), 0), (), {}, date(2026, 7, 15))
    assert result.earned_minutes == 600
    assert result.next_earning == date(2026, 7, 31)
    assert result.next_earning_minutes == 600


def test_a_july_1_hire_first_earns_on_july_31() -> None:
    # Hired Jul 1 2026, opening 0 as of that date. Today Jul 15: no month-end yet, earned 0.
    # Today Aug 1: Jul 31 has passed, earned 600, next Aug 31.
    person = Person("salaried", "TX", date(2026, 7, 1), MON_TO_FRI)
    opening = Opening(date(2026, 7, 1), 0)
    early = pto_balance(person, opening, (), {}, date(2026, 7, 15))
    assert early.earned_minutes == 0
    assert early.next_earning == date(2026, 7, 31)
    later = pto_balance(person, opening, (), {}, date(2026, 8, 1))
    assert later.earned_minutes == 600
    assert later.next_earning == date(2026, 8, 31)


def test_taken_booked_and_pending_split_by_status_and_date() -> None:
    # Today Wed Oct 7 2026; earned 4,800 + 9 x 600 = 10,200 (Jan 31 to Sep 30).
    # Approved Mon Oct 5 to Fri Oct 9: Oct 5, 6, 7 are on or before today, 3 x 480 = 1,440 taken;
    # Oct 8 and 9 are after, 2 x 480 = 960 booked.
    # Approved half day Wed Oct 14: 240 booked, so booked 1,200.
    # Pending Mon Nov 2 and Tue Nov 3: 960 pending, whatever the dates.
    # Available 10,200 - 1,440 - 1,200 - 960 = 6,600.
    # Next Oct 31: balance 10,200 - (1,440 + 960 + 240) = 7,560, room 3,240, earn 600.
    requests = (
        pto("a", date(2026, 10, 5), date(2026, 10, 9), "approved"),
        pto("b", date(2026, 10, 14), date(2026, 10, 14), "approved", 240),
        pto("c", date(2026, 11, 2), date(2026, 11, 3), "pending"),
    )
    result = pto_balance(SALARIED, Opening(JAN_1, 4800), requests, {}, date(2026, 10, 7))
    assert result.earned_minutes == 10200
    assert result.taken_minutes == 1440
    assert result.booked_minutes == 1200
    assert result.pending_minutes == 960
    assert result.available_minutes == 6600
    assert result.next_earning == date(2026, 10, 31)
    assert result.next_earning_minutes == 600


def test_denied_and_canceled_count_nowhere() -> None:
    requests = (
        pto("a", date(2026, 10, 5), date(2026, 10, 9), "denied"),
        pto("b", date(2026, 10, 12), date(2026, 10, 13), "canceled"),
    )
    result = pto_balance(SALARIED, Opening(JAN_1, 4800), requests, {}, date(2026, 10, 7))
    assert (result.taken_minutes, result.booked_minutes, result.pending_minutes) == (0, 0, 0)
    assert result.available_minutes == 10200


def test_today_counts_as_taken() -> None:
    # Approved on Wed Oct 7 only, today Oct 7: taken 480, booked 0.
    requests = (pto("a", date(2026, 10, 7), date(2026, 10, 7), "approved"),)
    result = pto_balance(SALARIED, Opening(JAN_1, 4800), requests, {}, date(2026, 10, 7))
    assert (result.taken_minutes, result.booked_minutes) == (480, 0)


def test_days_before_the_opening_are_ignored() -> None:
    # Approved Mon Dec 29 to Wed Dec 31 2025, before the Jan 1 2026 opening: already reflected.
    requests = (pto("a", date(2025, 12, 29), date(2025, 12, 31), "approved"),)
    result = pto_balance(SALARIED, Opening(JAN_1, 4800), requests, {}, date(2026, 10, 20))
    assert result.taken_minutes == 0
    assert result.available_minutes == 10200


def test_holidays_and_unscheduled_days_charge_nothing() -> None:
    # Approved Sat Oct 10, Sun Oct 11, Mon Oct 12 (a holiday): nothing counts, so nothing is
    # booked from today Oct 7.
    requests = (pto("a", date(2026, 10, 10), date(2026, 10, 12), "approved"),)
    result = pto_balance(
        SALARIED, Opening(JAN_1, 4800), requests, {date(2026, 10, 12): "Holiday"}, date(2026, 10, 7)
    )
    assert result.booked_minutes == 0
    assert result.available_minutes == 10200


def test_sick_requests_are_ignored() -> None:
    requests = (Request("s", "sick", date(2026, 10, 5), date(2026, 10, 9), None, "recorded"),)
    result = pto_balance(SALARIED, Opening(JAN_1, 4800), requests, {}, date(2026, 10, 7))
    assert (result.taken_minutes, result.booked_minutes, result.pending_minutes) == (0, 0, 0)
    assert result.available_minutes == 10200


def test_the_hire_date_sets_when_earning_starts() -> None:
    # Hired Tue Jun 30 2026 but the opening is 0 as of Jan 1: Jan 31 to May 31 are before the hire
    # and earn nothing. Jun 30 earns 600 (today Jul 15), so earned 600. Next Jul 31.
    person = Person("salaried", "TX", date(2026, 6, 30), MON_TO_FRI)
    result = pto_balance(person, Opening(JAN_1, 0), (), {}, date(2026, 7, 15))
    assert result.earned_minutes == 600
    assert result.next_earning == date(2026, 7, 31)


def test_pto_on_a_month_end_counts_against_that_months_check() -> None:
    # Opening 10,500. Approved Tue Mar 31 2026 (Mar 10 is a Tuesday, +21 days), 480, taken by
    # Apr 15. Jan 31: earn 300 (10,800). Feb 28: 0.
    # Mar 31: balance 10,800 - 480 = 10,320, room 480, earn 480.
    # Earned 10,500 + 300 + 480 = 11,280. Taken 480. Available 10,800.
    # Next Apr 30: balance 11,280 - 480 = 10,800, room 0, paused.
    requests = (pto("a", date(2026, 3, 31), date(2026, 3, 31), "approved"),)
    result = pto_balance(SALARIED, Opening(JAN_1, 10500), requests, {}, date(2026, 4, 15))
    assert result.earned_minutes == 11280
    assert result.taken_minutes == 480
    assert result.available_minutes == 10800
    assert result.next_earning is None


def test_earning_rolls_over_the_year_end() -> None:
    # Opening 0 as of Nov 1 2026, today Feb 15 2027: Nov 30, Dec 31, Jan 31 = 3 x 600 = 1,800.
    # Next Feb 28 2027 (not a leap year).
    result = pto_balance(SALARIED, Opening(date(2026, 11, 1), 0), (), {}, date(2027, 2, 15))
    assert result.earned_minutes == 1800
    assert result.next_earning == date(2027, 2, 28)


def test_february_29_in_a_leap_year_earns() -> None:
    # 2028 is a leap year. Opening 0 as of Feb 1 2028. Today Feb 28: nothing earned yet, next is
    # Feb 29. Today Mar 1: Feb 29 earned 600, next Mar 31.
    opening = Opening(date(2028, 2, 1), 0)
    before = pto_balance(SALARIED, opening, (), {}, date(2028, 2, 28))
    assert before.earned_minutes == 0
    assert before.next_earning == date(2028, 2, 29)
    after = pto_balance(SALARIED, opening, (), {}, date(2028, 3, 1))
    assert after.earned_minutes == 600
    assert after.next_earning == date(2028, 3, 31)


def test_pto_exactly_on_the_opening_date_counts() -> None:
    # Approved Thu Jan 1 2026 (the opening date), today Jan 20: taken 480. No holidays are passed,
    # so New Year's Day counts here; the test is about the opening boundary only. No month-end
    # yet, so earned stays 4,800 and available is 4,320.
    requests = (pto("a", date(2026, 1, 1), date(2026, 1, 1), "approved"),)
    result = pto_balance(SALARIED, Opening(JAN_1, 4800), requests, {}, date(2026, 1, 20))
    assert result.taken_minutes == 480
    assert result.available_minutes == 4320
