"""Sick leave by calendar year (handbook 4.3 and the state addenda).

Decisions the code follows:

- A year's grant is front-loaded on January 1, or on the hire date in the hire year. A year before
  the hire year grants 0. A future year's grant is known in advance. TX and GA grant 2,400
  minutes (4.3). CA grants the larger of 40 hours and 5 workdays (CA-4.3), computed from the day
  length. CO grants 2,880 (CO-4.3): "raised back to 48" and "use up to 48 a year" come to a grant
  of 48, so the engine never adds carryover on top.
- `holidays` must cover every year the passed requests touch (see `counting.py`).
- Only `sick` requests with status `recorded` count. Each counted day is charged to its own
  calendar year. Used is days on or before today (today counts as used); booked is days after
  today. Available is granted minus used minus booked. Nothing carries over.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from app.domain.timeoff.charges import charge_days
from app.domain.timeoff.model import DAY_MINUTES, Person, Request, State
from app.domain.timeoff.rules import Rule, sick_grant_rule

_SICK_HOURS_MINUTES = 40 * 60
_GRANT_MINUTES: dict[State, int] = {
    "TX": _SICK_HOURS_MINUTES,
    "GA": _SICK_HOURS_MINUTES,
    "CA": max(_SICK_HOURS_MINUTES, 5 * DAY_MINUTES),
    "CO": 48 * 60,
}


@dataclass(frozen=True, slots=True)
class SickYear:
    year: int
    granted_minutes: int
    used_minutes: int
    booked_minutes: int
    available_minutes: int
    rules: tuple[Rule, ...]


def _recorded_charges(
    person: Person, requests: Sequence[Request], holidays: Mapping[date, str]
) -> list[tuple[date, int]]:
    return [
        charge
        for request in requests
        if request.type == "sick" and request.status == "recorded"
        for charge in charge_days(
            person, request.start, request.end, request.partial_minutes, holidays
        )
    ]


def sick_balance(
    person: Person,
    requests: Sequence[Request],
    holidays: Mapping[date, str],
    year: int,
    today: date,
) -> SickYear:
    granted = _GRANT_MINUTES[person.state] if year >= person.hire_date.year else 0
    charges = _recorded_charges(person, requests, holidays)
    used = sum(minutes for day, minutes in charges if day.year == year and day <= today)
    booked = sum(minutes for day, minutes in charges if day.year == year and day > today)
    return SickYear(
        year=year,
        granted_minutes=granted,
        used_minutes=used,
        booked_minutes=booked,
        available_minutes=granted - used - booked,
        rules=(sick_grant_rule(person.state),),
    )


def sick_years(
    person: Person,
    requests: Sequence[Request],
    holidays: Mapping[date, str],
    today: date,
) -> tuple[SickYear, ...]:
    """The current year, plus next year once a recorded sick day falls in it."""
    years = [today.year]
    if any(day.year == today.year + 1 for day, _ in _recorded_charges(person, requests, holidays)):
        years.append(today.year + 1)
    return tuple(sick_balance(person, requests, holidays, year, today) for year in years)
