"""The engine's two small questions for the routes: which days of a range are already booked
(`overlapping_days`) and where a request may start and end (`request_bounds`). Every expected
value was worked out by hand.

Calendar anchors: 2026-10-20 is a Tuesday. Wed Oct 21, Thu 22, Fri 23, Sat 24, Sun 25, Mon 26,
Tue 27, Wed 28, Fri Oct 30. 2026-09-20 is 30 days before Oct 20.
"""

import time
from datetime import date

import pytest

from app.domain.timeoff.evaluate import (
    PROBLEM_CODES,
    Bounds,
    NewRequest,
    evaluate,
    overlapping_days,
    request_bounds,
)
from app.domain.timeoff.model import (
    LeaveType,
    Opening,
    Person,
    Request,
    RequestStatus,
    Schedule,
)

MON_TO_FRI = Schedule(weekdays=frozenset({1, 2, 3, 4, 5}))
TODAY = date(2026, 10, 20)


def req(ident: str, kind: LeaveType, start: date, end: date, status: RequestStatus) -> Request:
    return Request(ident, kind, start, end, None, status)


def person(hired: date = date(2020, 1, 6)) -> Person:
    return Person("salaried", "TX", hired, MON_TO_FRI)


# ---------------------------------------------------------------------------------------------
# overlapping_days

STORED = (
    # Wed Oct 21 to Fri Oct 23, waiting.
    req("a", "pto", date(2026, 10, 21), date(2026, 10, 23), "pending"),
    # Tue Oct 27 and Wed Oct 28, approved.
    req("b", "pto", date(2026, 10, 27), date(2026, 10, 28), "approved"),
    # Sat Oct 24, denied: frees its day.
    req("c", "pto", date(2026, 10, 24), date(2026, 10, 24), "denied"),
    # Mon Oct 26, canceled: frees its day.
    req("d", "pto", date(2026, 10, 26), date(2026, 10, 26), "canceled"),
    # Fri Oct 30, recorded sick time.
    req("e", "sick", date(2026, 10, 30), date(2026, 10, 30), "recorded"),
)


def test_the_days_of_a_range_inside_open_requests_come_out_in_order() -> None:
    # Oct 22 and 23 are in request a, Oct 27 and 28 in request b. Oct 24 to 26 are free.
    assert overlapping_days(STORED, date(2026, 10, 22), date(2026, 10, 28)) == (
        date(2026, 10, 22),
        date(2026, 10, 23),
        date(2026, 10, 27),
        date(2026, 10, 28),
    )


def test_denied_and_canceled_requests_book_nothing() -> None:
    # Only the denied Saturday and the canceled Monday, with nothing open between them.
    assert overlapping_days(STORED, date(2026, 10, 24), date(2026, 10, 26)) == ()


def test_a_recorded_sick_day_books_its_day() -> None:
    assert overlapping_days(STORED, date(2026, 10, 29), date(2026, 10, 31)) == (date(2026, 10, 30),)


def test_a_weekend_inside_a_request_is_a_booked_calendar_day() -> None:
    long = (req("w", "pto", date(2026, 10, 23), date(2026, 10, 26), "approved"),)

    # Fri 23 to Mon 26 is booked, so Sat 24 and Sun 25 are too.
    assert overlapping_days(long, date(2026, 10, 24), date(2026, 10, 25)) == (
        date(2026, 10, 24),
        date(2026, 10, 25),
    )


def test_a_request_that_starts_before_the_range_counts_only_from_its_start() -> None:
    # Request a is Oct 21 to 23. Asking from Oct 23 to Oct 25 meets it on Oct 23 only.
    assert overlapping_days(STORED, date(2026, 10, 23), date(2026, 10, 25)) == (date(2026, 10, 23),)


def test_two_requests_that_share_a_day_report_it_once() -> None:
    twice = (
        req("x", "pto", date(2026, 10, 21), date(2026, 10, 22), "approved"),
        req("y", "sick", date(2026, 10, 22), date(2026, 10, 23), "recorded"),
    )

    assert overlapping_days(twice, date(2026, 10, 20), date(2026, 10, 24)) == (
        date(2026, 10, 21),
        date(2026, 10, 22),
        date(2026, 10, 23),
    )


def test_a_range_with_no_request_in_it_has_none() -> None:
    assert overlapping_days(STORED, date(2026, 11, 2), date(2026, 11, 6)) == ()
    assert overlapping_days((), date(2026, 10, 21), date(2026, 10, 22)) == ()


def test_a_range_to_the_end_of_time_is_answered_at_once() -> None:
    started = time.perf_counter()

    found = overlapping_days(STORED, date(2026, 10, 29), date(9999, 12, 31))

    assert found == (date(2026, 10, 30),)
    assert time.perf_counter() - started < 0.5


# ---------------------------------------------------------------------------------------------
# request_bounds


def test_the_bounds_of_a_long_time_employee_are_today_and_30_days_back() -> None:
    # Opening on Jan 1 and hired in 2020: only today matters. Sick time reaches back to Sep 20.
    bounds = request_bounds(person(), Opening(date(2026, 1, 1), 4800), TODAY)

    assert bounds == Bounds(date(2026, 10, 20), date(2026, 9, 20), date(2027, 12, 31))


def test_a_future_hire_date_moves_both_earliest_days() -> None:
    bounds = request_bounds(person(date(2026, 10, 25)), Opening(date(2026, 1, 1), 0), TODAY)

    assert (bounds.earliest_pto_start, bounds.earliest_sick_start) == (
        date(2026, 10, 25),
        date(2026, 10, 25),
    )


def test_a_hire_inside_the_sick_window_moves_only_the_sick_day() -> None:
    bounds = request_bounds(person(date(2026, 10, 5)), Opening(date(2026, 1, 1), 0), TODAY)

    assert (bounds.earliest_pto_start, bounds.earliest_sick_start) == (
        date(2026, 10, 20),
        date(2026, 10, 5),
    )


def test_an_opening_in_the_future_moves_only_the_pto_day() -> None:
    bounds = request_bounds(person(), Opening(date(2026, 11, 1), 4800), TODAY)

    assert (bounds.earliest_pto_start, bounds.earliest_sick_start) == (
        date(2026, 11, 1),
        date(2026, 9, 20),
    )


def test_the_latest_end_is_december_31_of_next_year_and_follows_today() -> None:
    # Dec 31, 2026 is still in 2026, so the latest end is the end of 2027. On Jan 1, 2027 it moves
    # to the end of 2028.
    opening = Opening(date(2026, 1, 1), 0)

    assert request_bounds(person(), opening, date(2026, 12, 31)).latest_end == date(2027, 12, 31)
    assert request_bounds(person(), opening, date(2027, 1, 1)).latest_end == date(2028, 12, 31)


def test_earliest_start_picks_the_day_for_the_type() -> None:
    bounds = Bounds(date(2026, 10, 20), date(2026, 9, 20), date(2027, 12, 31))

    assert bounds.earliest_start("pto") == date(2026, 10, 20)
    assert bounds.earliest_start("sick") == date(2026, 9, 20)


@pytest.mark.parametrize(
    ("hired", "as_of"),
    [
        pytest.param(date(2020, 1, 6), date(2026, 1, 1), id="today binds"),
        pytest.param(date(2026, 10, 25), date(2026, 1, 1), id="the hire date binds"),
        pytest.param(date(2020, 1, 6), date(2026, 11, 1), id="the opening binds"),
        pytest.param(date(2026, 10, 5), date(2026, 1, 1), id="the hire date binds sick time"),
    ],
)
@pytest.mark.parametrize("kind", ["pto", "sick"])
def test_evaluate_refuses_one_day_before_the_earliest_start_and_not_on_it(
    hired: date, as_of: date, kind: LeaveType
) -> None:
    who = person(hired)
    opening = Opening(as_of, 4800)
    earliest = request_bounds(who, opening, TODAY).earliest_start(kind)

    def run(start: date) -> tuple[str, ...]:
        return evaluate(who, opening, (), {}, NewRequest(kind, start, start, None), TODAY).problems

    assert "out-of-range" not in run(earliest)
    assert "out-of-range" in run(date.fromordinal(earliest.toordinal() - 1))


def test_evaluate_refuses_an_end_after_the_latest_end_and_not_on_it() -> None:
    who = person()
    opening = Opening(date(2026, 1, 1), 4800)
    last = request_bounds(who, opening, TODAY).latest_end

    inside = evaluate(who, opening, (), {}, NewRequest("pto", last, last, None), TODAY)
    past = evaluate(who, opening, (), {}, NewRequest("pto", last, date(2028, 1, 1), None), TODAY)

    assert "out-of-range" not in inside.problems
    assert "out-of-range" in past.problems


def test_every_code_evaluate_can_return_is_in_the_list_of_codes() -> None:
    # A request that trips every check at once (see test_timeoff_evaluate's ordering test).
    who = person()
    stored = (req("a", "pto", date(2026, 10, 21), date(2026, 10, 21), "approved"),)
    refused = evaluate(
        who,
        Opening(date(2026, 1, 1), 0),
        stored,
        {},
        NewRequest("pto", date(2026, 9, 1), date(2026, 10, 24), 240),
        TODAY,
    )

    assert refused.problems
    assert set(refused.problems) <= set(PROBLEM_CODES)
    assert len(set(PROBLEM_CODES)) == len(PROBLEM_CODES) == 6
