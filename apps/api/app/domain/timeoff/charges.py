"""Charging a request by day (handbook 3.1).

A request is charged per counted day. Each counted day charges a full day (480 minutes), except a
one-day request with a partial amount, whose one day charges the partial. A day that doesn't count
(not scheduled, or a holiday) charges nothing. A partial on a range is not applied: the evaluator
refuses it, and stored data never holds one. PTO and sick leave both split a request by these
pairs: around today, at month-ends, and at December 31.
"""

from collections.abc import Mapping
from datetime import date

from app.domain.timeoff.counting import Counted, count_days
from app.domain.timeoff.model import DAY_MINUTES, Person


def charges_for(
    counted: Counted, start: date, end: date, partial_minutes: int | None
) -> tuple[tuple[date, int], ...]:
    """The (day, minutes) pairs for days already counted, in date order."""
    minutes = partial_minutes if partial_minutes is not None and start == end else DAY_MINUTES
    return tuple((day, minutes) for day in counted.counted)


def charge_days(
    person: Person,
    start: date,
    end: date,
    partial_minutes: int | None,
    holidays: Mapping[date, str],
) -> tuple[tuple[date, int], ...]:
    """The (day, minutes) pairs a request charges, in date order."""
    return charges_for(count_days(person, start, end, holidays), start, end, partial_minutes)
