"""What the time-off API takes and gives.

Every amount is a pair: `...Minutes` for a program and `...Label` for a person ("8 hours (1 day)"),
the one label the assistant's tools use too. Every list of rules is resolved: the handbook section
a figure rests on, with its title and deep link, ready to show as a source chip.
"""

from datetime import date, datetime
from datetime import date as date_
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, StringConstraints, model_validator

from app.api.schemas import CamelModel
from app.domain.timeoff.evaluate import Draw
from app.domain.timeoff.labels import label
from app.domain.timeoff.pto import PtoBalance
from app.domain.timeoff.sick import SickYear
from app.modules.timeoff import queries
from app.modules.timeoff.coverage import CoverageEntry
from app.modules.timeoff.service import (
    MAX_NOTE_CHARACTERS as MAX_NOTE_CHARACTERS,
)
from app.modules.timeoff.service import (
    Balances,
    Preview,
    RuleRef,
    checked_note,
)
from app.modules.timeoff.texts import refusal_text

type LeaveTypeName = Literal["pto", "sick"]


# ---------------------------------------------------------------------------------------------
# What comes in


class PossibleRequest(CamelModel):
    """The body of a check and of a request: type, dates, and a partial amount for a single day."""

    type: LeaveTypeName
    start_date: date
    end_date: date
    # 240 for a PTO half day, or whole hours from 60 to 480 for sick time. The engine checks it.
    partial_minutes: int | None = None

    @model_validator(mode="after")
    def _ends_after_it_starts(self) -> "PossibleRequest":
        if self.end_date < self.start_date:
            msg = "A request can't end before it starts."
            raise ValueError(msg)
        return self


class DecisionBody(CamelModel):
    decision: Literal["approve", "deny"]
    # A denial's note: trimmed, at most 300 characters. An approval carries none.
    note: (
        Annotated[
            str,
            StringConstraints(strip_whitespace=True, max_length=MAX_NOTE_CHARACTERS),
            AfterValidator(checked_note),
        ]
        | None
    ) = None

    @model_validator(mode="after")
    def _only_a_denial_has_a_note(self) -> "DecisionBody":
        if self.note and self.decision == "approve":
            msg = "Only a denial carries a note."
            raise ValueError(msg)
        return self


# ---------------------------------------------------------------------------------------------
# Rules, balances


class RuleRefOut(CamelModel):
    section_id: str
    rule: str
    title: str
    deep_link: str

    @classmethod
    def of(cls, ref: RuleRef) -> "RuleRefOut":
        return cls(
            section_id=ref.section_id, rule=ref.rule, title=ref.title, deep_link=ref.deep_link
        )


class PtoBalanceOut(CamelModel):
    earned_minutes: int
    earned_label: str
    taken_minutes: int
    taken_label: str
    booked_minutes: int
    booked_label: str
    pending_minutes: int
    pending_label: str
    available_minutes: int
    available_label: str
    ceiling_minutes: int
    ceiling_label: str
    # Null when earning is paused at the ceiling.
    next_earning_date: date | None
    next_earning_minutes: int
    next_earning_label: str

    @classmethod
    def of(cls, pto: PtoBalance) -> "PtoBalanceOut":
        return cls(
            earned_minutes=pto.earned_minutes,
            earned_label=label(pto.earned_minutes),
            taken_minutes=pto.taken_minutes,
            taken_label=label(pto.taken_minutes),
            booked_minutes=pto.booked_minutes,
            booked_label=label(pto.booked_minutes),
            pending_minutes=pto.pending_minutes,
            pending_label=label(pto.pending_minutes),
            available_minutes=pto.available_minutes,
            available_label=label(pto.available_minutes),
            ceiling_minutes=pto.ceiling_minutes,
            ceiling_label=label(pto.ceiling_minutes),
            next_earning_date=pto.next_earning,
            next_earning_minutes=pto.next_earning_minutes,
            next_earning_label=label(pto.next_earning_minutes),
        )


class SickYearOut(CamelModel):
    year: int
    granted_minutes: int
    granted_label: str
    used_minutes: int
    used_label: str
    booked_minutes: int
    booked_label: str
    available_minutes: int
    available_label: str

    @classmethod
    def of(cls, year: SickYear) -> "SickYearOut":
        return cls(
            year=year.year,
            granted_minutes=year.granted_minutes,
            granted_label=label(year.granted_minutes),
            used_minutes=year.used_minutes,
            used_label=label(year.used_minutes),
            booked_minutes=year.booked_minutes,
            booked_label=label(year.booked_minutes),
            available_minutes=year.available_minutes,
            available_label=label(year.available_minutes),
        )


class BalancesOut(CamelModel):
    person_id: UUID
    # The date at the person's location, which the balances are as of.
    today: date
    pto: PtoBalanceOut
    sick: list[SickYearOut]
    rules: list[RuleRefOut]

    @classmethod
    def of(cls, balances: Balances) -> "BalancesOut":
        return cls(
            person_id=balances.person_id,
            today=balances.today,
            pto=PtoBalanceOut.of(balances.pto),
            sick=[SickYearOut.of(year) for year in balances.sick],
            rules=[RuleRefOut.of(rule) for rule in balances.rules],
        )


# ---------------------------------------------------------------------------------------------
# Requests


class PersonOut(CamelModel):
    id: UUID
    name: str
    title: str


class NameOut(CamelModel):
    name: str


class CoveragePerson(CamelModel):
    id: UUID
    name: str


class CoverageDayOut(CamelModel):
    date: date_
    type: LeaveTypeName
    # Null for a whole day off; 240 for half a day of PTO, or the hours of a sick record in minutes.
    partial_minutes: int | None


class CoverageOut(CamelModel):
    """One colleague who is off on some of the request's days. Plain context, never a verdict."""

    person: CoveragePerson
    # The request's days they are off, in date order, each with its type.
    days: list[CoverageDayOut]

    @classmethod
    def of(cls, entry: CoverageEntry) -> "CoverageOut":
        return cls(
            person=CoveragePerson(id=entry.person_id, name=entry.person_name),
            days=[
                CoverageDayOut(date=day.day, type=day.type, partial_minutes=day.partial_minutes)
                for day in entry.days
            ],
        )


class RequestOut(CamelModel):
    id: UUID
    person: PersonOut
    type: LeaveTypeName
    start_date: date
    end_date: date
    partial_minutes: int | None
    amount_minutes: int
    amount_label: str
    status: Literal["pending", "approved", "denied", "recorded", "canceled"]
    # When it was sent: the Approvals card's "Sent October 17".
    created_at: datetime
    created_via: Literal["ui", "assistant"]
    decided_by: NameOut | None
    decided_at: datetime | None
    # A denial's note. Anyone who may read the request sees it, on pages and cards only.
    decision_note: str | None
    canceled_at: datetime | None
    # Only for the person's direct manager. Coverage (who else on the manager's team is off) comes
    # with any of the report's requests. The person's available PTO as it stands (the request
    # already counts against it) comes only with a PTO request still waiting for a decision.
    available_after_minutes: int | None = None
    available_after_label: str | None = None
    coverage: list[CoverageOut] | None = None

    @classmethod
    def of(
        cls,
        row: queries.RequestRow,
        *,
        available_after_minutes: int | None = None,
        coverage: tuple[CoverageEntry, ...] | None = None,
    ) -> "RequestOut":
        return cls(
            id=row.id,
            person=PersonOut(id=row.person_id, name=row.person_name, title=row.person_title),
            type=row.type,
            start_date=row.start_date,
            end_date=row.end_date,
            partial_minutes=row.partial_minutes,
            amount_minutes=row.amount_minutes,
            amount_label=label(row.amount_minutes),
            status=row.status,
            created_at=row.created_at,
            created_via=row.created_via,
            decided_by=None if row.decided_by_name is None else NameOut(name=row.decided_by_name),
            decided_at=row.decided_at,
            decision_note=row.decision_note,
            canceled_at=row.canceled_at,
            available_after_minutes=available_after_minutes,
            available_after_label=(
                None if available_after_minutes is None else label(available_after_minutes)
            ),
            coverage=None if coverage is None else [CoverageOut.of(entry) for entry in coverage],
        )


class RequestList(CamelModel):
    items: list[RequestOut]
    # The window the list covers, as the server worked it out (the default depends on the caller's
    # today).
    from_date: date
    to_date: date


# ---------------------------------------------------------------------------------------------
# The check


class ProblemOut(CamelModel):
    code: str
    text: str


class DrawOut(CamelModel):
    # Null for PTO; the calendar year for sick time.
    year: int | None
    amount_minutes: int
    amount_label: str
    available_before_minutes: int
    available_before_label: str
    available_after_minutes: int
    available_after_label: str

    @classmethod
    def of(cls, draw: Draw) -> "DrawOut":
        return cls(
            year=draw.year,
            amount_minutes=draw.amount_minutes,
            amount_label=label(draw.amount_minutes),
            available_before_minutes=draw.available_before_minutes,
            available_before_label=label(draw.available_before_minutes),
            available_after_minutes=draw.available_after_minutes,
            available_after_label=label(draw.available_after_minutes),
        )


class SkippedDay(CamelModel):
    day: date
    # "not scheduled", or the holiday's name.
    reason: str


class CheckOut(CamelModel):
    """The engine's answer for a possible request. It is a preview: nothing was written, and it is
    a 200 even when the request has problems."""

    ok: bool
    problems: list[ProblemOut]
    # Codes, such as "short-notice". A warning never refuses.
    warnings: list[str]
    counted_days: list[date]
    skipped_days: list[SkippedDay]
    # The days of the range that another pending, approved, or recorded request already covers.
    overlapping_days: list[date]
    amount_minutes: int | None
    amount_label: str | None
    draws: list[DrawOut]
    rules: list[RuleRefOut]

    @classmethod
    def of(cls, answer: Preview) -> "CheckOut":
        evaluation = answer.evaluation
        amount = evaluation.amount_minutes
        return cls(
            ok=answer.ok,
            problems=[ProblemOut(code=code, text=refusal_text(code)) for code in answer.problems],
            warnings=list(evaluation.warnings),
            counted_days=list(evaluation.counted),
            skipped_days=[
                SkippedDay(day=item.day, reason=item.reason) for item in evaluation.skipped
            ],
            overlapping_days=list(answer.overlapping),
            amount_minutes=amount,
            amount_label=None if amount is None else label(amount),
            draws=[DrawOut.of(draw) for draw in evaluation.draws],
            rules=[RuleRefOut.of(rule) for rule in answer.rules],
        )


# ---------------------------------------------------------------------------------------------
# The calendar and the summary


class HolidayOut(CamelModel):
    day: date
    name: str


class EarliestStart(CamelModel):
    pto: date
    sick: date


class CalendarOut(CamelModel):
    """The date picker's marks for the signed-in person."""

    # ISO weekdays, 1 (Monday) to 7 (Sunday).
    scheduled_weekdays: list[int]
    holidays: list[HolidayOut]
    earliest_start: EarliestStart
    # December 31 of next year, for both types.
    latest_end: date


class SummaryOut(CamelModel):
    pto_available_minutes: int
    pto_available_label: str
    # The signed-in person's own requests that wait for a decision.
    pending_count: int
    # Their direct manager, or null for someone with none.
    approver: NameOut | None
    # Requests waiting for them to decide. Null unless they have direct reports.
    waiting_count: int | None
