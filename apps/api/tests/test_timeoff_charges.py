"""Charging a request by day. Every expected value was worked out by hand from a calendar."""

from datetime import date

from app.domain.timeoff.charges import charge_days
from app.domain.timeoff.model import Person, Schedule

MON_TO_FRI = Schedule(weekdays=frozenset({1, 2, 3, 4, 5}))
PERSON = Person(
    employment_type="salaried", state="TX", hire_date=date(2020, 1, 6), schedule=MON_TO_FRI
)


def test_each_counted_day_charges_a_full_day_and_other_days_nothing() -> None:
    # October 2026: Oct 1 is a Thursday, so Fri Oct 9, Sat 10, Sun 11, Mon 12, Tue 13.
    # Fri 9 counts (480); Sat and Sun are not scheduled; Mon 12 is a holiday; Tue 13 counts (480).
    result = charge_days(
        PERSON, date(2026, 10, 9), date(2026, 10, 13), None, {date(2026, 10, 12): "X"}
    )
    assert result == ((date(2026, 10, 9), 480), (date(2026, 10, 13), 480))


def test_a_one_day_request_with_a_partial_charges_the_partial() -> None:
    # Wed Oct 14 2026 (Oct 1 Thursday + 13 days), scheduled: charges the 240 partial.
    assert charge_days(PERSON, date(2026, 10, 14), date(2026, 10, 14), 240, {}) == (
        (date(2026, 10, 14), 240),
    )


def test_a_partial_on_an_unscheduled_day_charges_nothing() -> None:
    # Sat Oct 10 2026 is not scheduled for Monday to Friday.
    assert charge_days(PERSON, date(2026, 10, 10), date(2026, 10, 10), 240, {}) == ()


def test_a_partial_on_a_range_is_not_applied() -> None:
    # Wed Oct 14 and Thu Oct 15: two counted days, 480 each, since a partial only fits one day.
    assert charge_days(PERSON, date(2026, 10, 14), date(2026, 10, 15), 240, {}) == (
        (date(2026, 10, 14), 480),
        (date(2026, 10, 15), 480),
    )
