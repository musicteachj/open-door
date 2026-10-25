"""Evaluating a new request. Every expected value was worked out by hand from the handbook.

Calendar anchors: 2026-01-01 is a Thursday, so Oct 1 2026 is a Thursday and Tue Oct 20 is the
default "today" (earned PTO 4,800 + 9 x 600 = 10,200 from an opening of 4,800 on Jan 1, so 10,200
is available with no requests). Wed Oct 21, Thu 22, Fri 23, Sat 24, Sun 25, Mon 26, Tue 27,
Wed 28; Fri Oct 30; Mon Nov 2 to Fri Nov 6. 2027-01-01 is a Friday and 2028-01-01 a Saturday.
"""

import time
from datetime import date

import pytest

from app.domain.timeoff.counting import Skipped
from app.domain.timeoff.evaluate import Draw, Evaluation, NewRequest, evaluate
from app.domain.timeoff.model import (
    LeaveType,
    Opening,
    Person,
    Request,
    RequestStatus,
    Schedule,
    State,
)
from app.domain.timeoff.rules import RULES, Rule

MON_TO_FRI = Schedule(weekdays=frozenset({1, 2, 3, 4, 5}))
ALL_DAYS = Schedule(weekdays=frozenset({1, 2, 3, 4, 5, 6, 7}))
TODAY = date(2026, 10, 20)
OPENING = Opening(date(2026, 1, 1), 4800)


def person(state: State = "TX", schedule: Schedule = MON_TO_FRI) -> Person:
    return Person("salaried", state, date(2020, 1, 6), schedule)


def req(
    ident: str,
    kind: LeaveType,
    start: date,
    end: date,
    status: RequestStatus,
    partial: int | None = None,
) -> Request:
    return Request(ident, kind, start, end, partial, status)


def run(
    new: NewRequest,
    requests: tuple[Request, ...] = (),
    who: Person | None = None,
    opening: Opening = OPENING,
    today: date = TODAY,
    holidays: dict[date, str] | None = None,
) -> Evaluation:
    return evaluate(who or person(), opening, requests, holidays or {}, new, today)


def pto(start: date, end: date | None = None, partial: int | None = None) -> NewRequest:
    return NewRequest("pto", start, end or start, partial)


def sick(start: date, end: date | None = None, partial: int | None = None) -> NewRequest:
    return NewRequest("sick", start, end or start, partial)


def test_a_new_request_cannot_end_before_it_starts() -> None:
    with pytest.raises(ValueError, match="end before"):
        NewRequest("pto", date(2026, 10, 22), date(2026, 10, 21), None)


# no-scheduled-days


def test_no_scheduled_days() -> None:
    # Sat Oct 24 and Sun Oct 25 2026: nothing counts for Monday to Friday.
    result = run(pto(date(2026, 10, 24), date(2026, 10, 25)))
    assert result.ok is False
    assert result.problems == ("no-scheduled-days",)
    assert result.counted == ()
    assert result.skipped == (
        Skipped(date(2026, 10, 24), "not scheduled"),
        Skipped(date(2026, 10, 25), "not scheduled"),
    )
    assert result.amount_minutes is None
    assert result.draws == ()


def test_a_sick_partial_on_an_unscheduled_day_is_no_scheduled_days() -> None:
    # Sat Oct 24, 3 hours: a valid partial, but the day does not count.
    result = run(sick(date(2026, 10, 24), partial=180))
    assert result.problems == ("no-scheduled-days",)
    assert result.amount_minutes is None


# too-long


def test_thirty_two_calendar_days_is_too_long_and_thirty_one_is_not() -> None:
    # Wed Oct 21 to Fri Nov 20 is 11 + 20 = 31 days; to Sat Nov 21 is 32 days.
    # Counted weekdays for 31 days: Oct 21-23 (3), Oct 26-30 (5), Nov 2-6 (5), Nov 9-13 (5),
    # Nov 16-20 (5) = 23, so 23 x 480 = 11,040, under the 20,000 + 5,400 available.
    # A range over 31 days is not counted at all: only the date checks run.
    big = Opening(date(2026, 1, 1), 20000)
    ok = run(pto(date(2026, 10, 21), date(2026, 11, 20)), opening=big)
    assert ok.problems == ()
    assert ok.amount_minutes == 11040
    too_long = run(pto(date(2026, 10, 21), date(2026, 11, 21)), opening=big)
    assert too_long.problems == ("too-long",)
    assert too_long.counted == ()
    assert too_long.skipped == ()
    assert too_long.amount_minutes is None
    assert too_long.draws == ()


def test_a_range_to_the_end_of_time_is_refused_without_counting_it() -> None:
    # 2026-10-20 to 9999-12-31 is far over 31 days and ends after 2027-12-31.
    started = time.perf_counter()
    result = run(pto(date(2026, 10, 20), date(9999, 12, 31)))
    assert time.perf_counter() - started < 1
    assert result.problems == ("too-long", "out-of-range")
    assert result.counted == ()
    assert result.amount_minutes is None
    assert result.draws == ()


def test_an_overlap_is_still_found_on_a_too_long_range() -> None:
    existing = (req("e", "pto", date(2026, 10, 26), date(2026, 10, 27), "approved"),)
    result = run(pto(date(2026, 10, 21), date(2026, 11, 21)), existing)
    assert result.problems == ("too-long", "overlaps")


# out-of-range


def test_pto_starting_yesterday_is_out_of_range_and_today_is_in_range() -> None:
    # Mon Oct 19 is yesterday; Tue Oct 20 is today.
    assert run(pto(date(2026, 10, 19))).problems == ("out-of-range",)
    today = run(pto(date(2026, 10, 20)))
    assert today.problems == ()
    assert today.amount_minutes == 480


def test_sick_exactly_30_days_back_is_allowed_and_31_is_not() -> None:
    # Today Wed Oct 21 2026. 30 days back is Mon Sep 21 (Oct 21 - 21 = Sep 30; - 9 = Sep 21).
    # 31 days back is Sun Sep 20, so use an every-day schedule for that one.
    today = date(2026, 10, 21)
    allowed = run(sick(date(2026, 9, 21)), today=today)
    assert allowed.problems == ()
    assert allowed.amount_minutes == 480
    assert RULES["sick-window"] not in allowed.rules
    late = run(sick(date(2026, 9, 20)), who=person(schedule=ALL_DAYS), today=today)
    assert late.problems == ("out-of-range",)
    assert RULES["sick-window"] in late.rules


def test_pto_before_the_opening_date_is_out_of_range() -> None:
    # The opening is as of Wed 2026-10-21 but the location's today is still Tue 2026-10-20 (a
    # scheduled day). A PTO day before the opening would cost nothing once approved, so it is
    # refused. Starting on the opening date is fine.
    opening = Opening(date(2026, 10, 21), 4800)
    before = run(pto(date(2026, 10, 20)), opening=opening)
    assert before.problems == ("out-of-range",)
    assert run(pto(date(2026, 10, 21)), opening=opening).problems == ()
    # Sick time doesn't use the opening.
    assert run(sick(date(2026, 10, 20)), opening=opening).problems == ()


def test_an_end_after_december_31_of_next_year_is_out_of_range() -> None:
    # Today is in 2026, so the last allowed day is Fri 2027-12-31. Thu 2027-12-30 to Fri
    # 2027-12-31 is fine (2 days, 960). Thu Dec 30 2027 to Mon 2028-01-03 ends too late
    # (Dec 30, 31, and Jan 3 count: 1,440, which fits in 10,200).
    inside = run(pto(date(2027, 12, 30), date(2027, 12, 31)))
    assert inside.problems == ()
    assert inside.amount_minutes == 960
    past = run(pto(date(2027, 12, 30), date(2028, 1, 3)))
    assert past.problems == ("out-of-range",)
    assert past.amount_minutes == 1440


# bad-partial


@pytest.mark.parametrize("partial", [480, 120, 0, 60])
def test_a_pto_partial_other_than_240_is_bad(partial: int) -> None:
    result = run(pto(date(2026, 10, 21), partial=partial))
    assert result.problems == ("bad-partial",)
    assert result.amount_minutes is None
    assert result.draws == ()


@pytest.mark.parametrize("partial", [0, 540, 90, 30, 600])
def test_a_sick_partial_must_be_whole_hours_from_60_to_480(partial: int) -> None:
    result = run(sick(date(2026, 10, 21), partial=partial))
    assert result.problems == ("bad-partial",)
    assert result.amount_minutes is None


def test_a_partial_on_a_range_is_bad() -> None:
    assert run(pto(date(2026, 10, 21), date(2026, 10, 22), 240)).problems == ("bad-partial",)
    assert run(sick(date(2026, 10, 21), date(2026, 10, 22), 120)).problems == ("bad-partial",)


# amounts, draws, rules


def test_a_pto_half_day() -> None:
    # Wed Oct 21: one scheduled day with a 240 partial. Available 10,200 before, 9,960 after.
    result = run(pto(date(2026, 10, 21), partial=240))
    assert result.ok is True
    assert result.amount_minutes == 240
    assert result.counted == (date(2026, 10, 21),)
    assert result.draws == (Draw(None, 240, 10200, 9960),)
    assert result.rules == (
        RULES["scheduled-days"],
        RULES["pto-available"],
        RULES["pto-increments"],
    )


def test_sick_three_hours() -> None:
    # Wed Oct 21, 180 minutes. TX 2026 grant 2,400 with nothing used: 2,400 before, 2,220 after.
    result = run(sick(date(2026, 10, 21), partial=180))
    assert result.ok is True
    assert result.amount_minutes == 180
    assert result.draws == (Draw(2026, 180, 2400, 2220),)
    assert result.rules == (
        RULES["scheduled-days"],
        Rule("4.3", "sick-grant"),
        RULES["sick-increments"],
    )


def test_a_holiday_adds_the_holiday_rule() -> None:
    # Wed Nov 25 to Fri Nov 27 2026 with Thu Nov 26 (Thanksgiving) a holiday: Nov 25 and 27 count,
    # 960.
    result = run(
        pto(date(2026, 11, 25), date(2026, 11, 27)),
        holidays={date(2026, 11, 26): "Thanksgiving Day"},
    )
    assert result.amount_minutes == 960
    assert result.skipped == (Skipped(date(2026, 11, 26), "Thanksgiving Day"),)
    assert result.rules == (
        RULES["scheduled-days"],
        RULES["holidays-not-charged"],
        RULES["pto-available"],
    )


def test_sick_rules_use_the_state_section() -> None:
    result = run(sick(date(2026, 10, 21)), who=person("CA"))
    assert Rule("CA-4.3", "sick-grant") in result.rules


# short notice


def test_four_days_starting_ten_days_out_is_ok_with_short_notice() -> None:
    # Fri Oct 30 is 10 days from Tue Oct 20. Fri Oct 30, Mon Nov 2, Tue Nov 3, Wed Nov 4 = 4 days.
    result = run(pto(date(2026, 10, 30), date(2026, 11, 4)))
    assert result.ok is True
    assert result.warnings == ("short-notice",)
    assert result.amount_minutes == 1920
    assert RULES["pto-notice"] in result.rules


def test_four_days_starting_thirteen_days_out_warns_and_fourteen_does_not() -> None:
    # Mon Nov 2 is 13 days out: Mon to Thu Nov 5 is 4 days, warns.
    # Tue Nov 3 is 14 days out: Tue to Fri Nov 6 is 4 days, no warning.
    assert run(pto(date(2026, 11, 2), date(2026, 11, 5))).warnings == ("short-notice",)
    exactly = run(pto(date(2026, 11, 3), date(2026, 11, 6)))
    assert exactly.warnings == ()
    assert RULES["pto-notice"] not in exactly.rules


def test_three_days_starting_tomorrow_has_no_warning() -> None:
    # Wed Oct 21 to Fri Oct 23 is 3 days: not more than 3.
    result = run(pto(date(2026, 10, 21), date(2026, 10, 23)))
    assert result.warnings == ()
    assert result.ok is True


def test_sick_time_never_warns_about_notice() -> None:
    assert run(sick(date(2026, 10, 21), date(2026, 10, 27))).warnings == ()


# not-enough


def _held_back() -> tuple[Request, ...]:
    return (
        req("p", "pto", date(2026, 10, 26), date(2026, 10, 27), "pending"),
        req("a", "pto", date(2026, 11, 2), date(2026, 11, 3), "approved"),
    )


# Opening 0 on Jan 1 2026: earned 9 x 600 = 5,400 by Oct 20. The new request is Mon Nov 9 to Thu
# Nov 19: Nov 9-13 (5) and Nov 16-19 (4) = 9 days = 4,320. It starts 20 days out: no warning.
_NINE_DAYS = NewRequest("pto", date(2026, 11, 9), date(2026, 11, 19), None)
_ZERO = Opening(date(2026, 1, 1), 0)


def test_pending_and_booked_requests_count_against_what_is_available() -> None:
    # Pending Oct 26-27 (960) and approved Nov 2-3 (960) leave 5,400 - 1,920 = 3,480 < 4,320.
    held = run(_NINE_DAYS, _held_back(), opening=_ZERO)
    assert held.problems == ("not-enough",)
    assert held.amount_minutes == 4320
    assert held.draws == (Draw(None, 4320, 3480, -840),)
    # Without them, 5,400 >= 4,320 fits.
    free = run(_NINE_DAYS, (), opening=_ZERO)
    assert free.problems == ()
    assert free.draws == (Draw(None, 4320, 5400, 1080),)


@pytest.mark.parametrize("status", ["denied", "canceled"])
def test_available_grows_back_when_the_pending_request_ends(status: RequestStatus) -> None:
    # The pending Oct 26-27 request no longer counts: 5,400 - 960 = 4,440 >= 4,320.
    requests = (
        req("p", "pto", date(2026, 10, 26), date(2026, 10, 27), status),
        req("a", "pto", date(2026, 11, 2), date(2026, 11, 3), "approved"),
    )
    result = run(_NINE_DAYS, requests, opening=_ZERO)
    assert result.problems == ()
    assert result.draws == (Draw(None, 4320, 4440, 120),)


def test_no_future_earning_counts_toward_what_is_available() -> None:
    # Opening 0: 5,400 is available now. 12 days from Mon Nov 9 is Nov 9-13, 16-20, 23-24 (12 days)
    # = 5,760 > 5,400 even though Oct 31 and Nov 30 would earn more.
    result = run(pto(date(2026, 11, 9), date(2026, 11, 24)), opening=_ZERO)
    assert result.problems == ("not-enough",)


# overlaps


@pytest.mark.parametrize("status", ["pending", "approved"])
def test_overlapping_a_pto_request_that_is_waiting_or_approved_refuses(
    status: RequestStatus,
) -> None:
    existing = (req("e", "pto", date(2026, 10, 26), date(2026, 10, 28), status),)
    # Wed Oct 28 to Fri Oct 30 shares Oct 28.
    assert run(pto(date(2026, 10, 28), date(2026, 10, 30)), existing).problems == ("overlaps",)
    # Thu Oct 29 to Fri Oct 30 starts after Oct 28.
    assert run(pto(date(2026, 10, 29), date(2026, 10, 30)), existing).problems == ()


def test_a_recorded_sick_request_overlaps_a_new_pto_request() -> None:
    existing = (req("e", "sick", date(2026, 10, 26), date(2026, 10, 28), "recorded"),)
    assert run(pto(date(2026, 10, 27)), existing).problems == ("overlaps",)


def test_a_sick_request_over_an_approved_pto_day_overlaps() -> None:
    existing = (req("e", "pto", date(2026, 10, 26), date(2026, 10, 28), "approved"),)
    assert run(sick(date(2026, 10, 27)), existing).problems == ("overlaps",)


@pytest.mark.parametrize("status", ["denied", "canceled"])
def test_denied_and_canceled_requests_never_overlap(status: RequestStatus) -> None:
    existing = (req("e", "pto", date(2026, 10, 26), date(2026, 10, 28), status),)
    assert run(pto(date(2026, 10, 27)), existing).problems == ()


# sick: last year and December 31


def _used_2400_in_2026() -> tuple[Request, ...]:
    # Mon Nov 2 to Fri Nov 6 2026: 5 days x 480 = 2,400 used.
    return (req("u", "sick", date(2026, 11, 2), date(2026, 11, 6), "recorded"),)


def test_early_january_sick_time_for_last_year_draws_on_last_years_grant() -> None:
    # Today Sun 2027-01-10. Mon 2026-12-28 is 13 days back, in range, and falls in 2026.
    # TX 2026: 2,400 granted, 2,400 used, 0 available < 480. 2027's full grant is not touched.
    today = date(2027, 1, 10)
    opening = Opening(date(2027, 1, 1), 0)
    result = run(sick(date(2026, 12, 28)), _used_2400_in_2026(), opening=opening, today=today)
    assert result.problems == ("not-enough",)
    assert result.draws == (Draw(2026, 480, 0, -480),)


def test_colorado_has_room_last_year() -> None:
    # CO 2026: 2,880 - 2,400 = 480 available, exactly the 480 asked for.
    today = date(2027, 1, 10)
    opening = Opening(date(2027, 1, 1), 0)
    result = run(
        sick(date(2026, 12, 28)),
        _used_2400_in_2026(),
        who=person("CO"),
        opening=opening,
        today=today,
    )
    assert result.problems == ()
    assert result.draws == (Draw(2026, 480, 480, 0),)


_HOLIDAYS_2027 = {date(2027, 1, 1): "New Year's Day"}
_ACROSS = NewRequest("sick", date(2026, 12, 30), date(2027, 1, 4), None)


def test_a_sick_request_across_december_31_has_one_draw_per_year() -> None:
    # Wed 2026-12-30 to Mon 2027-01-04, today Tue 2026-12-15, TX Monday to Friday.
    # Dec 30, 31 count in 2026 (960); Jan 1 holiday; Jan 2, 3 not scheduled; Jan 4 in 2027 (480).
    result = run(_ACROSS, today=date(2026, 12, 15), holidays=_HOLIDAYS_2027)
    assert result.ok is True
    assert result.amount_minutes == 1440
    assert result.counted == (date(2026, 12, 30), date(2026, 12, 31), date(2027, 1, 4))
    assert result.draws == (Draw(2026, 960, 2400, 1440), Draw(2027, 480, 2400, 1920))
    assert result.skipped == (
        Skipped(date(2027, 1, 1), "New Year's Day"),
        Skipped(date(2027, 1, 2), "not scheduled"),
        Skipped(date(2027, 1, 3), "not scheduled"),
    )


def test_a_sick_request_across_december_31_refuses_if_the_first_year_does_not_fit() -> None:
    # Used Mon Nov 2 to Thu Nov 5 2026: 4 x 480 = 1,920, leaving 480 < 960 for Dec 30-31.
    used = (req("u", "sick", date(2026, 11, 2), date(2026, 11, 5), "recorded"),)
    result = run(_ACROSS, used, today=date(2026, 12, 15), holidays=_HOLIDAYS_2027)
    assert result.problems == ("not-enough",)
    assert result.draws == (Draw(2026, 960, 480, -480), Draw(2027, 480, 2400, 1920))


def test_a_sick_request_across_december_31_refuses_if_the_second_year_does_not_fit() -> None:
    # Booked Tue 2027-01-05 to Fri Jan 8 (4 x 480) and Mon Jan 11 (480): 2,400, so 2027 has 0 left
    # for the 480 on Jan 4. 2026 still fits (960 of 2,400).
    booked = (
        req("b1", "sick", date(2027, 1, 5), date(2027, 1, 8), "recorded"),
        req("b2", "sick", date(2027, 1, 11), date(2027, 1, 11), "recorded"),
    )
    result = run(_ACROSS, booked, today=date(2026, 12, 15), holidays=_HOLIDAYS_2027)
    assert result.problems == ("not-enough",)
    assert result.draws == (Draw(2026, 960, 2400, 1440), Draw(2027, 480, 0, -480))


def test_a_start_before_the_hire_date_is_out_of_range() -> None:
    # Hired Mon 2026-06-01, today Wed 2026-06-10. Wed 2026-05-20 (Jun 1 minus 12 days) is a
    # scheduled day, 21 days back and inside the sick window, but before the hire.
    # Tue 2026-06-02 is after the hire.
    hired = Person("salaried", "TX", date(2026, 6, 1), MON_TO_FRI)
    opening = Opening(date(2026, 6, 1), 0)
    today = date(2026, 6, 10)
    before = run(sick(date(2026, 5, 20)), who=hired, opening=opening, today=today)
    assert before.problems == ("out-of-range",)
    assert RULES["sick-window"] not in before.rules
    after = run(sick(date(2026, 6, 2)), who=hired, opening=opening, today=today)
    assert after.problems == ()


def test_a_colorado_sick_request_across_december_31_has_one_draw_per_year() -> None:
    # Same dates as the Texas case, today Tue 2026-12-15. CO grant 2,880 each year, nothing used:
    # 2026 draw 960 (Dec 30, 31): 2,880 before, 1,920 after. 2027 draw 480 (Jan 4): 2,880, 2,400.
    result = run(_ACROSS, who=person("CO"), today=date(2026, 12, 15), holidays=_HOLIDAYS_2027)
    assert result.ok is True
    assert result.draws == (Draw(2026, 960, 2880, 1920), Draw(2027, 480, 2880, 2400))
    assert Rule("CO-4.3", "sick-grant") in result.rules


def test_an_hourly_person_is_evaluated_against_the_hourly_balance() -> None:
    # Hourly, opening 0 on Jan 1, today Tue Oct 20: 9 month-ends x 480 = 4,320 available
    # (a salaried person would have 9 x 600 = 5,400).
    # Mon Nov 9 to Fri Nov 20: 10 weekdays = 4,800 > 4,320, so not-enough; salaried would fit.
    hourly = Person("hourly", "TX", date(2020, 1, 6), MON_TO_FRI)
    result = run(pto(date(2026, 11, 9), date(2026, 11, 20)), who=hourly, opening=_ZERO)
    assert result.problems == ("not-enough",)
    assert result.draws == (Draw(None, 4800, 4320, -480),)
    # Nine days (Nov 9 to Nov 19) = 4,320 fits exactly.
    nine = run(_NINE_DAYS, who=hourly, opening=_ZERO)
    assert nine.problems == ()
    assert nine.draws == (Draw(None, 4320, 4320, 0),)


def test_a_request_refused_for_a_past_start_gets_no_notice_warning() -> None:
    # Today Tue 2026-10-20. Sat 2026-10-17 is 3 days back. Sat 17 to Fri 23: Mon 19 to Fri 23 count,
    # 5 days (more than 3), so it would warn if the start were not in the past.
    result = run(pto(date(2026, 10, 17), date(2026, 10, 23)))
    assert "out-of-range" in result.problems
    assert len(result.counted) == 5
    assert result.warnings == ()
    assert RULES["pto-notice"] not in result.rules


# order of problems


def test_every_check_runs_and_problems_come_out_in_the_specs_order() -> None:
    # Mon Oct 12 to Wed Oct 28 2026 with a 240 partial: starts before today (out-of-range), a
    # partial on a range (bad-partial), and shares Oct 26-27 with a pending request (overlaps).
    existing = (req("e", "pto", date(2026, 10, 26), date(2026, 10, 27), "pending"),)
    result = run(pto(date(2026, 10, 12), date(2026, 10, 28), 240), existing)
    assert result.problems == ("out-of-range", "bad-partial", "overlaps")
    # Sat Oct 17 and Sun Oct 18: nothing counts and the start is before today.
    weekend = run(pto(date(2026, 10, 17), date(2026, 10, 18)))
    assert weekend.problems == ("no-scheduled-days", "out-of-range")
    # Wed Oct 21 to Sat Nov 21 is 32 days: too long, and not counted, so no not-enough.
    long = run(pto(date(2026, 10, 21), date(2026, 11, 21)), opening=_ZERO)
    assert long.problems == ("too-long",)


# The dates a request may use cite the handbook's sentence (Phase 5, stage 4): "A request can start
# today or later, and end by December 31 of next year" in 4.1, and "Sick time can't be recorded for
# a day before your first day of work, or for a day after December 31 of next year" in 4.3.


def test_the_date_rules_are_in_the_table_with_their_sections() -> None:
    assert RULES["pto-dates"] == Rule("4.1", "pto-dates")
    assert RULES["sick-dates"] == Rule("4.3", "sick-dates")


def test_pto_out_of_range_cites_the_pto_date_rule_and_an_in_range_one_does_not() -> None:
    # Yesterday (Mon Oct 19), an end past Fri 2027-12-31 (Thu Dec 30 2027 to Mon 2028-01-03), and a
    # day before an opening dated Wed Oct 21 (today is Tue Oct 20) are each out of range.
    yesterday = run(pto(date(2026, 10, 19)))
    too_late = run(pto(date(2027, 12, 30), date(2028, 1, 3)))
    before_opening = run(pto(date(2026, 10, 20)), opening=Opening(date(2026, 10, 21), 4800))
    for result in (yesterday, too_late, before_opening):
        assert result.problems == ("out-of-range",)
        assert RULES["pto-dates"] in result.rules
    # Today, Tue Oct 20, is in range: nothing about dates to cite.
    assert RULES["pto-dates"] not in run(pto(date(2026, 10, 20))).rules


def test_sick_time_before_the_hire_date_or_after_next_year_cites_the_sick_date_rule() -> None:
    # Hired Mon 2026-06-01, today Wed 2026-06-10: Wed 2026-05-20 is inside the 30-day window but
    # before the hire. With a 2026 today, Thu 2027-12-30 to Mon 2028-01-03 ends past Dec 31 2027.
    hired = Person("salaried", "TX", date(2026, 6, 1), MON_TO_FRI)
    before_hire = run(
        sick(date(2026, 5, 20)),
        who=hired,
        opening=Opening(date(2026, 6, 1), 0),
        today=date(2026, 6, 10),
    )
    too_late = run(sick(date(2027, 12, 30), date(2028, 1, 3)))
    for result in (before_hire, too_late):
        assert result.problems == ("out-of-range",)
        assert RULES["sick-dates"] in result.rules
        assert RULES["sick-window"] not in result.rules


def test_sick_time_past_the_window_cites_the_window_not_the_date_rule() -> None:
    # Today Wed Oct 21 2026; Sun Sep 20 is 31 days back (an every-day schedule makes it count).
    late = run(sick(date(2026, 9, 20)), who=person(schedule=ALL_DAYS), today=date(2026, 10, 21))
    assert late.problems == ("out-of-range",)
    assert RULES["sick-window"] in late.rules
    assert RULES["sick-dates"] not in late.rules
    # An in-range sick day cites neither.
    fine = run(sick(date(2026, 10, 21)), today=date(2026, 10, 21))
    assert RULES["sick-dates"] not in fine.rules
