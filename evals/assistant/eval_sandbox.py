"""The requests the eval adds to its sandbox after the seed.

The action questions need two requests the demo's seed does not have, and the demo must never get
them. Both are Priya's, on days that no booking item asks about:

- **An upcoming Friday, approved** (Friday, October 30, 2026), for the "cancel my Friday off" items.
- **A pending request for Marcus to decide** (Monday, November 16 to Wednesday, November 18, 2026),
  for the "approve Priya's request" items.

**Why those days.** Priya works Monday to Friday in Oakland, and the company's closed days from the
seed are Thanksgiving (Thursday, November 26) and Christmas Day (Friday, December 25). Neither
request touches a closed day, so the engine charges every day in them: 8 hours for the Friday and
24 hours for the three days. Priya has 174 hours available in the seed on October 15, so 8 booked
and 24 pending leave 142, and `build_request` checks that again with the engine for any request it
builds. The booking items in actions.yaml keep clear of both ranges (they ask about next week,
Thanksgiving week, December, and so on), so a new request never overlaps these two.

**IDs** are derived the way the seed derives its own, `uuid5(tenant_id, "timeoff:<seat>:<label>")`,
with labels the seed never uses (it uses `pto-1`, `pto-pending`, `sick-1`, and so on), so a result
that names a request repeats from one run to the next. The eval inserts them with the seed's own
insert path (`insert_time_off_requests`), so the table's constraints hold for them as for the rest.

Pure: rows are built in memory from the seed company and the time-off engine, which does all the
counting. Run from apps/api like the rest of the eval.
"""

from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from typing import cast
from uuid import uuid5

from app.domain.timeoff.charges import charge_days
from app.domain.timeoff.model import (
    EmploymentType,
    LeaveType,
    Opening,
    RequestStatus,
    Schedule,
    State,
)
from app.domain.timeoff.model import Person as EnginePerson
from app.domain.timeoff.model import Request as EngineRequest
from app.domain.timeoff.pto import pto_balance
from app.domain.timeoff.sick import sick_years
from app.modules.sandbox.seed import PersonRow, RequestRow, SeedCompany

# Priya's seat key in the seed, and the labels of the two requests.
SEAT = "priya"
CANCEL_LABEL = "eval-cancel-friday"
PENDING_LABEL = "eval-pending-november"

CANCEL_DAY = date(2026, 10, 30)
PENDING_START = date(2026, 11, 16)
PENDING_END = date(2026, 11, 18)


class NoSuchRequest(LookupError):  # noqa: N818
    """No request of that person starts on that day."""


def _person_named(company: SeedCompany, persona: str) -> PersonRow:
    return next(p for p in company.people if p.persona_key == persona)


def build_request(
    company: SeedCompany,
    persona: str,
    label: str,
    start: date,
    end: date,
    status: str,
) -> RequestRow:
    """One PTO request of the persona's, charged by the engine. Raises `ValueError` ("doesn't fit")
    when the engine charges no day, it overlaps one of the person's own requests, or PTO would go
    below zero today or the day before (a person's today can be the day before the anchor)."""
    person = _person_named(company, persona)
    location = next(loc for loc in company.locations if loc.id == person.location_id)
    engine_person = EnginePerson(
        cast(EmploymentType, person.employment_type),
        cast(State, location.state),
        person.hire_date,
        Schedule(frozenset(person.scheduled_weekdays)),
    )
    holidays = {h.holiday_date: h.name for h in company.holidays if h.location_id == location.id}
    charges = charge_days(engine_person, start, end, None, holidays)
    mine = [r for r in company.time_off_requests if r.person_id == person.id]
    problem = None
    if not charges:
        problem = "the engine charges no day in it"
    elif any(r.start_date <= end and start <= r.end_date for r in mine):
        problem = "it overlaps one of her requests"
    if problem is None:
        opening_row = next(o for o in company.time_off_openings if o.person_id == person.id)
        opening = Opening(opening_row.as_of, opening_row.amount_minutes)
        trial = [
            EngineRequest(
                str(r.id),
                cast(LeaveType, r.type),
                r.start_date,
                r.end_date,
                r.partial_minutes,
                cast(RequestStatus, r.status),
            )
            for r in mine
        ]
        trial.append(
            EngineRequest(f"{SEAT}:{label}", "pto", start, end, None, cast(RequestStatus, status))
        )
        for today in (company.anchor_date - timedelta(days=1), company.anchor_date):
            balance = pto_balance(engine_person, opening, trial, holidays, today)
            years = sick_years(engine_person, trial, holidays, today)
            if balance.available_minutes < 0 or any(y.available_minutes < 0 for y in years):
                problem = "it takes PTO below zero"
    if problem is not None:
        msg = f"The eval's request {persona}:{label} ({start} to {end}) doesn't fit: {problem}"
        raise ValueError(msg)
    if status == "approved":
        created_at = datetime.combine(company.anchor_date - timedelta(days=7), time(15), tzinfo=UTC)
        decided_at: datetime | None = created_at + timedelta(hours=2)
        decided_by = person.manager_id
    else:
        created_at = datetime.combine(company.anchor_date - timedelta(days=2), time(17), tzinfo=UTC)
        decided_at = None
        decided_by = None
    return RequestRow(
        id=uuid5(company.tenant_id, f"timeoff:{SEAT}:{label}"),
        tenant_id=company.tenant_id,
        person_id=person.id,
        type="pto",
        start_date=start,
        end_date=end,
        partial_minutes=None,
        amount_minutes=sum(minutes for _, minutes in charges),
        status=status,
        created_at=created_at,
        created_via="ui",
        proposal_id=None,
        decided_by=decided_by,
        decided_at=decided_at,
        decision_note=None,
        canceled_at=None,
    )


def eval_requests(company: SeedCompany) -> tuple[RequestRow, ...]:
    """The two requests the eval adds: the Friday to cancel, then the pending one."""
    return (
        build_request(company, "priya", CANCEL_LABEL, CANCEL_DAY, CANCEL_DAY, "approved"),
        build_request(company, "priya", PENDING_LABEL, PENDING_START, PENDING_END, "pending"),
    )


def with_eval_requests(company: SeedCompany) -> SeedCompany:
    """The company with the eval's requests after the seed's, nothing else changed."""
    return replace(company, time_off_requests=(*company.time_off_requests, *eval_requests(company)))


def request_id(company: SeedCompany, person_name: str, start: date) -> str:
    """The ID of the request of the person ("Priya Raman") whose first day is `start`. Raises
    `NoSuchRequest`. The datasets name a request this way, and the graders resolve it here."""
    people = {p.id: f"{p.given_name} {p.family_name}" for p in company.people}
    for row in company.time_off_requests:
        if people[row.person_id] == person_name and row.start_date == start:
            return str(row.id)
    msg = f"no request of {person_name} starts on {start.isoformat()}"
    raise NoSuchRequest(msg)
