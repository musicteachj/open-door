"""Counting a request's days (handbook 3.1 and 4.2).

A day counts when it is one of the person's scheduled weekdays and not a company holiday at their
location. Every other day in the range is listed as skipped with its reason. "Not scheduled" wins
over a holiday on the same day, since the person wasn't going to work it anyway. Holidays come in
as data (date to name). The mapping must cover every year that any request passed to the
engine touches: the new request's years and the stored requests' years too, since the balances
recount the stored requests on every call. A year missing from the mapping reads as having no
holidays, so its holiday days would be charged. The balance and evaluate functions rely on this.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta

from app.domain.timeoff.model import Person
from app.domain.timeoff.rules import RULES, Rule

NOT_SCHEDULED = "not scheduled"


@dataclass(frozen=True, slots=True)
class Skipped:
    day: date
    reason: str  # "not scheduled" or the holiday's name


@dataclass(frozen=True, slots=True)
class Counted:
    counted: tuple[date, ...]  # in date order
    skipped: tuple[Skipped, ...]  # in date order
    rules: tuple[Rule, ...]  # 3.1 always; 4.2 only when a holiday was skipped


def count_days(person: Person, start: date, end: date, holidays: Mapping[date, str]) -> Counted:
    """The days from `start` to `end`, both included, that count against the person's time off."""
    if end < start:
        msg = "A range can't end before it starts"
        raise ValueError(msg)
    counted: list[date] = []
    skipped: list[Skipped] = []
    holiday_skipped = False
    for offset in range((end - start).days + 1):
        day = start + timedelta(days=offset)
        if day.isoweekday() not in person.schedule.weekdays:
            skipped.append(Skipped(day, NOT_SCHEDULED))
        elif day in holidays:
            holiday_skipped = True
            skipped.append(Skipped(day, holidays[day]))
        else:
            counted.append(day)
    rules = [RULES["scheduled-days"]]
    if holiday_skipped:
        rules.append(RULES["holidays-not-charged"])
    return Counted(tuple(counted), tuple(skipped), tuple(rules))
