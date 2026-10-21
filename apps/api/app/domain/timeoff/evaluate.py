"""Evaluating a new request (handbook 3.1, 4.1, 4.2, 4.3).

The evaluation answers only "what would this count, and does it fit". It never decides who may
act: the policy layer does that. The new request is not in `requests`. Every check runs, and the
problems come out in a fixed order:

1. `no-scheduled-days`: no day counts (not reported for a range over 31 days).
2. `too-long`: more than 31 calendar days. Such a range is not counted at all, so a request to
   9999-12-31 costs nothing: it reports only the date checks (`too-long`, `out-of-range`,
   `bad-partial`, `overlaps`), with no counted days, amount, draws, or `not-enough`.
3. `out-of-range`: PTO starting before today; sick time starting more than 30 days before today
   (exactly 30 is allowed); PTO starting before `opening.as_of` (it would cost nothing once
   approved, since the opening already reflects those days); either type starting before the
   hire date; or either type ending
   after December 31 of next year.
4. `bad-partial`: a partial on a range; a PTO partial other than 240; a sick partial that isn't
   whole hours from 60 to 480.
5. `overlaps`: the range meets a pending, approved, or recorded request of either type.
6. `not-enough`: checked only when the amount is defined. PTO must fit in what is available today
   (pending and booked already reduce it; no future earning counts). Sick time is checked per
   calendar year it touches, last year included: in early January a sick day up to 30 days back
   draws on last year's grant.

`holidays` must cover every year the new and the stored requests touch (see `counting.py`).

A warning, never a refusal: `short-notice` for PTO of more than 3 counted days that starts less
than 14 days from today (exactly 14 gets none).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from app.domain.timeoff.charges import charges_for
from app.domain.timeoff.counting import Counted, Skipped, count_days
from app.domain.timeoff.model import (
    LEAVE_TYPES,
    MAX_REQUEST_DAYS,
    LeaveType,
    Opening,
    Person,
    Request,
    partial_is_valid,
)
from app.domain.timeoff.pto import pto_balance
from app.domain.timeoff.rules import RULES, Rule, sick_grant_rule
from app.domain.timeoff.sick import sick_balance

SICK_WINDOW_DAYS = 30
SHORT_NOTICE_DAYS = 14
SHORT_NOTICE_MIN_DAYS = 3
_OVERLAP_STATUSES = ("pending", "approved", "recorded")


@dataclass(frozen=True, slots=True)
class NewRequest:
    type: LeaveType
    start: date
    end: date
    partial_minutes: int | None

    def __post_init__(self) -> None:
        if self.type not in LEAVE_TYPES:
            msg = f"A request's type is one of {LEAVE_TYPES}, got {self.type!r}"
            raise ValueError(msg)
        if self.end < self.start:
            msg = "A request can't end before it starts"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class Draw:
    """What the request takes from one balance."""

    year: int | None  # None for PTO; the calendar year for sick time
    amount_minutes: int
    available_before_minutes: int
    available_after_minutes: int


@dataclass(frozen=True, slots=True)
class Evaluation:
    ok: bool  # no problems; warnings don't count
    problems: tuple[str, ...]
    warnings: tuple[str, ...]
    counted: tuple[date, ...]
    skipped: tuple[Skipped, ...]
    amount_minutes: int | None  # None when bad-partial or no day counts
    draws: tuple[Draw, ...]  # empty when the amount is None
    rules: tuple[Rule, ...]


def evaluate(
    person: Person,
    opening: Opening,
    requests: Sequence[Request],
    holidays: Mapping[date, str],
    new: NewRequest,
    today: date,
) -> Evaluation:
    partial = new.partial_minutes
    bad_partial = not partial_is_valid(new.type, new.start, new.end, partial)
    too_long = (new.end - new.start).days + 1 > MAX_REQUEST_DAYS
    # A range over the limit is not counted at all: only the date checks run on it.
    counting = Counted((), (), ()) if too_long else count_days(person, new.start, new.end, holidays)
    charges = charges_for(counting, new.start, new.end, partial)
    amount = None if bad_partial or not charges else sum(minutes for _, minutes in charges)

    problems: list[str] = []
    if not too_long and not counting.counted:
        problems.append("no-scheduled-days")
    if too_long:
        problems.append("too-long")
    out_of_range = _start_out_of_range(new, today)
    before_opening = new.type == "pto" and new.start < opening.as_of
    if (
        out_of_range
        or before_opening
        or new.start < person.hire_date
        or new.end > date(today.year + 1, 12, 31)
    ):
        problems.append("out-of-range")
    if bad_partial:
        problems.append("bad-partial")
    if any(
        request.status in _OVERLAP_STATUSES
        and request.start <= new.end
        and new.start <= request.end
        for request in requests
    ):
        problems.append("overlaps")

    draws: tuple[Draw, ...] = ()
    if amount is not None:
        draws = _draws(person, opening, requests, holidays, new.type, charges, today)
        if any(draw.available_after_minutes < 0 for draw in draws):
            problems.append("not-enough")

    short_notice = (
        new.type == "pto"
        and new.start >= today
        and len(counting.counted) > SHORT_NOTICE_MIN_DAYS
        and (new.start - today).days < SHORT_NOTICE_DAYS
    )
    rules = list(counting.rules)
    if new.type == "pto":
        rules.append(RULES["pto-available"])
        if partial is not None:
            rules.append(RULES["pto-increments"])
        if short_notice:
            rules.append(RULES["pto-notice"])
    else:
        rules.append(sick_grant_rule(person.state))
        if partial is not None:
            rules.append(RULES["sick-increments"])
        if out_of_range:
            rules.append(RULES["sick-window"])
    return Evaluation(
        ok=not problems,
        problems=tuple(problems),
        warnings=("short-notice",) if short_notice else (),
        counted=counting.counted,
        skipped=counting.skipped,
        amount_minutes=amount,
        draws=draws,
        rules=tuple(dict.fromkeys(rules)),
    )


def _start_out_of_range(new: NewRequest, today: date) -> bool:
    if new.type == "pto":
        return new.start < today
    return new.start < today - timedelta(days=SICK_WINDOW_DAYS)


def _draws(
    person: Person,
    opening: Opening,
    requests: Sequence[Request],
    holidays: Mapping[date, str],
    kind: LeaveType,
    charges: tuple[tuple[date, int], ...],
    today: date,
) -> tuple[Draw, ...]:
    if kind == "pto":
        amount = sum(minutes for _, minutes in charges)
        available = pto_balance(person, opening, requests, holidays, today).available_minutes
        return (Draw(None, amount, available, available - amount),)
    by_year: dict[int, int] = {}
    for day, minutes in charges:
        by_year[day.year] = by_year.get(day.year, 0) + minutes
    draws = []
    for year in sorted(by_year):
        available = sick_balance(person, requests, holidays, year, today).available_minutes
        draws.append(Draw(year, by_year[year], available, available - by_year[year]))
    return tuple(draws)
