"""PTO balances (handbook 4.1).

Decisions the code follows:

- Only `pto` requests count. An `approved` request is taken (day on or before today, so today
  counts as taken) or booked (day after today). A `pending` request is pending, whatever its dates.
  `denied` and `canceled` count nowhere. Days dated before `opening.as_of` are ignored everywhere,
  because the opening already reflects them.
- Salaried staff earn 600 minutes a month and hourly staff 480. The ceiling is 1.5 times the
  yearly amount: rate * 12 * 3 / 2.
- Earning happens on each month's last day M with M >= max(opening.as_of, hire date) and
  M <= today (inclusive). In date order, at each M the balance is the opening, plus earned so far,
  minus approved PTO charged on days from `opening.as_of` up to M. The month earns
  min(rate, max(0, ceiling - balance)). An opening above the ceiling earns nothing and is never
  reduced.
- Earned to date is the opening plus those earnings. Available is earned minus taken, booked, and
  pending. No future earning counts toward it.
- The next earning is the first month-end after today (and on or after the start above), worked
  out the same way against approved PTO charged up to it. A next amount of 0 means earning is
  paused at the ceiling, and `next_earning` is None.
- `holidays` must cover every year the passed requests touch (see `counting.py`).
- A later approval can change a past month's earning, since the balance is the rules applied to
  what is approved now.
"""

import calendar
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from app.domain.timeoff.charges import charge_days
from app.domain.timeoff.model import EmploymentType, Opening, Person, Request
from app.domain.timeoff.rules import RULES, Rule

MONTHLY_RATE_MINUTES: dict[EmploymentType, int] = {"salaried": 600, "hourly": 480}


@dataclass(frozen=True, slots=True)
class PtoBalance:
    earned_minutes: int
    taken_minutes: int
    booked_minutes: int
    pending_minutes: int
    available_minutes: int
    ceiling_minutes: int
    next_earning: date | None  # None when paused at the ceiling
    next_earning_minutes: int  # 0 when next_earning is None
    rules: tuple[Rule, ...]


def _month_ends(start: date) -> Iterator[date]:
    """Every month's last day on or after `start`, in order, without end."""
    year, month = start.year, start.month
    while True:
        last = date(year, month, calendar.monthrange(year, month)[1])
        if last >= start:
            yield last
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)


def pto_balance(
    person: Person,
    opening: Opening,
    requests: Sequence[Request],
    holidays: Mapping[date, str],
    today: date,
) -> PtoBalance:
    rate = MONTHLY_RATE_MINUTES[person.employment_type]
    ceiling = rate * 12 * 3 // 2
    approved: list[tuple[date, int]] = []
    pending = 0
    for request in requests:
        if request.type != "pto" or request.status not in ("approved", "pending"):
            continue
        charges = charge_days(person, request.start, request.end, request.partial_minutes, holidays)
        kept = [(day, minutes) for day, minutes in charges if day >= opening.as_of]
        if request.status == "approved":
            approved.extend(kept)
        else:
            pending += sum(minutes for _, minutes in kept)
    taken = sum(minutes for day, minutes in approved if day <= today)
    booked = sum(minutes for day, minutes in approved if day > today)

    def earning_at(month_end: date, earned: int) -> int:
        used = sum(minutes for day, minutes in approved if day <= month_end)
        return min(rate, max(0, ceiling - (earned - used)))

    earned = opening.amount_minutes
    next_earning: date | None = None
    next_minutes = 0
    for month_end in _month_ends(max(opening.as_of, person.hire_date)):
        if month_end > today:
            next_minutes = earning_at(month_end, earned)
            next_earning = month_end if next_minutes > 0 else None
            break
        earned += earning_at(month_end, earned)
    return PtoBalance(
        earned_minutes=earned,
        taken_minutes=taken,
        booked_minutes=booked,
        pending_minutes=pending,
        available_minutes=earned - taken - booked - pending,
        ceiling_minutes=ceiling,
        next_earning=next_earning,
        next_earning_minutes=next_minutes,
        rules=(RULES["pto-earning"], RULES["pto-ceiling"], RULES["pto-available"]),
    )
