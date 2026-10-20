"""The engine's input types. Plain frozen data, checked when built."""

from dataclasses import dataclass
from datetime import date
from typing import Literal, get_args

EmploymentType = Literal["salaried", "hourly"]
State = Literal["CA", "CO", "TX", "GA"]
LeaveType = Literal["pto", "sick"]
RequestStatus = Literal["pending", "approved", "denied", "recorded", "canceled"]

EMPLOYMENT_TYPES: tuple[str, ...] = get_args(EmploymentType)
STATES: tuple[str, ...] = get_args(State)
LEAVE_TYPES: tuple[str, ...] = get_args(LeaveType)
REQUEST_STATUSES: tuple[str, ...] = get_args(RequestStatus)

# A request spans at most 31 calendar days (longer leaves go through HR, handbook 5.1).
MAX_REQUEST_DAYS = 31

# Every scheduled day counts as 8 hours (handbook 3.1); a PTO half day is 4 hours (4.1).
DAY_MINUTES = 480
HALF_DAY_MINUTES = 240


def partial_is_valid(kind: LeaveType, start: date, end: date, partial_minutes: int | None) -> bool:
    """Whether a partial amount fits the rules: none, or on a one-day request only.

    A PTO partial is 240 minutes (a half day). A sick partial is whole hours from 60 to 480.
    """
    if partial_minutes is None:
        return True
    if start != end:
        return False
    if kind == "pto":
        return partial_minutes == HALF_DAY_MINUTES
    return partial_minutes % 60 == 0 and 60 <= partial_minutes <= DAY_MINUTES


@dataclass(frozen=True, slots=True)
class Schedule:
    """The ISO weekdays a person normally works, 1 (Monday) to 7 (Sunday). At least one."""

    weekdays: frozenset[int]

    def __post_init__(self) -> None:
        # Freeze whatever was passed, so a caller's later change to its own set can't alter us.
        object.__setattr__(self, "weekdays", frozenset(self.weekdays))
        if not self.weekdays:
            msg = "A schedule needs at least one weekday"
            raise ValueError(msg)
        if any(not 1 <= weekday <= 7 for weekday in self.weekdays):
            msg = f"Schedule weekdays are ISO 1 to 7, got {sorted(self.weekdays)}"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class Person:
    employment_type: EmploymentType
    state: State
    hire_date: date
    schedule: Schedule

    def __post_init__(self) -> None:
        if self.employment_type not in EMPLOYMENT_TYPES:
            msg = (
                f"A person's employment type is one of {EMPLOYMENT_TYPES}, "
                f"got {self.employment_type!r}"
            )
            raise ValueError(msg)
        if self.state not in STATES:
            msg = f"A person's state is one of {STATES}, got {self.state!r}"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class Opening:
    """The PTO balance in minutes at the start of `as_of` (PTO only; sick leave is granted by rule).

    It is the balance before any earning on that day, so a month-end that falls on `as_of` earns
    on top of it. That is why a hire on June 30 with an opening of 0 earns on June 30.
    """

    as_of: date
    amount_minutes: int

    def __post_init__(self) -> None:
        if self.amount_minutes < 0:
            msg = "An opening balance can't be negative"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class Request:
    """A leave request from `start` to `end`, both included.

    `partial_minutes` is set only for a one-day request: 240 for a PTO half day, or whole hours
    from 60 to 480 for sick time. The engine's evaluator checks that; this type checks the dates.
    """

    id: str
    type: LeaveType
    start: date
    end: date
    partial_minutes: int | None
    status: RequestStatus

    def __post_init__(self) -> None:
        if self.type not in LEAVE_TYPES:
            msg = f"A request's type is one of {LEAVE_TYPES}, got {self.type!r}"
            raise ValueError(msg)
        if self.status not in REQUEST_STATUSES:
            msg = f"A request's status is one of {REQUEST_STATUSES}, got {self.status!r}"
            raise ValueError(msg)
        if self.end < self.start:
            msg = "A request can't end before it starts"
            raise ValueError(msg)
        if (self.end - self.start).days + 1 > MAX_REQUEST_DAYS:
            msg = f"A request spans at most {MAX_REQUEST_DAYS} days"
            raise ValueError(msg)
        if not partial_is_valid(self.type, self.start, self.end, self.partial_minutes):
            msg = f"A {self.type} request can't have a partial of {self.partial_minutes} minutes"
            raise ValueError(msg)
