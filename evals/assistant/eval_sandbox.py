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

**The fairness set's people** (`with_eval_clones`). The fairness groups ask one question from
several people who differ only in name, and the seed has no pairs like that, so the eval adds
"clones": employees that copy a template person's title, department, office, employment type,
schedule, hire date, birth date, opening PTO balance, and every time-off request, and differ in
name (and so in work and personal email), in their phone number and street number (theirs alone, so
the private-data check can tell people apart), and in their manager (see below). The demo's seed
never gets them.

- **Time off matches the template's.** A clone gets a copy of each of its template's requests that
  exist when the clones are built (the seed's, and the eval's own for Priya), with the same dates,
  kind, status, and amount and a new ID, `uuid5(tenant_id, "fairness:<clone key>:<template request
  id>")`. A decided request names the clone's own manager as its decider. So the balance, the
  request list, and the engine's inputs (schedule, hire date, office holidays, opening balance)
  are the template's, and an answer's figures differ only if the assistant made them differ.

- **Employees only.** A clone is never HR and never a manager, and nobody reports to one.
- **Who they report to.** All of them report to the Marketing Manager at Denver HQ. "My team" is
  recursive, and every Oakland lead reports up to Marcus, so no clone may sit under an Oakland
  lead; Austin's chain runs through the Warehouse Manager to the COO, where Mateo's own lead sits.
  The Marketing Manager (CEO, Director of Marketing, Marketing Manager) is outside every persona's
  management chain and below nobody an eval question asks about (the eval YAMLs name only Marcus
  and Zara as managers), so no clone changes any other item's tool results. The isolation proof in
  tests/integration/test_fairness_isolation.py checks that against every recorded tool call.
- **IDs** come from the tenant and the clone's key (`clone_person_id`), so an asker named by a clone
  key resolves without any map. The people table's persona-key check allows only the four personas,
  so clones have no persona key.
- **Names** are outside the seed's name pools (a test checks).

Pure: rows are built in memory from the seed company and the time-off engine, which does all the
counting. Run from apps/api like the rest of the eval.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
from typing import cast
from uuid import UUID, uuid5

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
from app.modules.sandbox.seed import (
    OpeningRow,
    PersonPrivateRow,
    PersonRow,
    RequestRow,
    SeedCompany,
)
from app.modules.sandbox.seed_data import LOCATIONS

# Priya's seat key in the seed (the eval's requests are hers), and the labels of the two requests.
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
            EngineRequest(
                f"{persona}:{label}", "pto", start, end, None, cast(RequestStatus, status)
            )
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
        id=uuid5(company.tenant_id, f"timeoff:{persona}:{label}"),
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
    cancel = build_request(company, SEAT, CANCEL_LABEL, CANCEL_DAY, CANCEL_DAY, "approved")
    # The second is checked against the company plus the first, so the pair's fit is checked.
    with_cancel = replace(company, time_off_requests=(*company.time_off_requests, cancel))
    pending = build_request(with_cancel, SEAT, PENDING_LABEL, PENDING_START, PENDING_END, "pending")
    return (cancel, pending)


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


# --- The fairness set's people ----------------------------------------------------------------

# The seat all clones report to (see the module docstring), and its title.
CLONE_MANAGER_SEAT = "marketing-manager"
CLONE_MANAGER_TITLE = "Marketing Manager"
# The employee personas a clone may copy: not Dana (HR) and not Marcus (a manager).
CLONEABLE_PERSONAS = ("priya", "mateo")
# For a clone that names an office and an employment type instead of a persona: the seeded person
# whose title, schedule, hire date, and opening balance it copies. No persona is hourly in
# Oakland, so that is the only combination. The seat is a Sales Associate who manages no one.
TEMPLATE_SEATS = {("oak", "hourly"): "oak-apparel-1"}


@dataclass(frozen=True, slots=True)
class CloneSpec:
    """One eval-only person: a key, a name, and the template it copies (a persona to be `like`, or
    an office and an employment type)."""

    key: str
    given_name: str
    family_name: str
    like: str | None = None
    location: str | None = None
    employment_type: str | None = None


def clone_person_id(tenant_id: UUID, key: str) -> UUID:
    """The ID of the clone with this key in this tenant."""
    return uuid5(tenant_id, f"person:fairness:{key}")


def _seat_person_id(tenant_id: UUID, seat: str) -> UUID:
    # The seed's own rule for a person's ID (`make_id("person", seat)` in seed.py).
    return uuid5(tenant_id, f"person:{seat}")


def template_person_id(tenant_id: UUID, spec: CloneSpec) -> UUID:
    """The ID of the seeded person a clone without a persona copies (by office and employment
    type). Raises `ValueError` when there is none."""
    seat = TEMPLATE_SEATS.get((spec.location or "", spec.employment_type or ""))
    if seat is None:
        msg = (
            f"{spec.key}: no template person for {spec.employment_type!r} staff at"
            f" {spec.location!r}"
        )
        raise ValueError(msg)
    return _seat_person_id(tenant_id, seat)


def _template(company: SeedCompany, spec: CloneSpec) -> PersonRow:
    if spec.like is not None:
        if spec.like not in CLONEABLE_PERSONAS:
            msg = f"{spec.key}: a clone can only copy an employee persona, not {spec.like!r}"
            raise ValueError(msg)
        return _person_named(company, spec.like)
    wanted = template_person_id(company.tenant_id, spec)
    found = next((p for p in company.people if p.id == wanted), None)
    if found is None:
        msg = f"{spec.key}: no seeded person fills the template seat for this clone"
        raise ValueError(msg)
    return found


_STREET_NUMBER = re.compile(r"^(\d+) (.*)$")


def with_eval_clones(company: SeedCompany, specs: Sequence[CloneSpec]) -> SeedCompany:
    """The company with the clones after the seeded people, nothing else changed. Raises
    `ValueError` for a clone with no usable template."""
    if not specs:
        return company
    manager_id = _seat_person_id(company.tenant_id, CLONE_MANAGER_SEAT)
    manager = next((p for p in company.people if p.id == manager_id), None)
    if manager is None:
        msg = f"No seeded person fills the clone manager seat {CLONE_MANAGER_SEAT!r}"
        raise ValueError(msg)
    if manager.title != CLONE_MANAGER_TITLE:
        msg = f"The clone manager is {manager.title!r}, not {CLONE_MANAGER_TITLE!r}"
        raise ValueError(msg)
    area_codes = {spec.code: spec.area_code for spec in LOCATIONS}
    location_codes = {loc.id: loc.code for loc in company.locations}
    used_suffixes = {row.phone[-2:] for row in company.person_private}
    free = sorted(f"{n:02d}" for n in range(100) if f"{n:02d}" not in used_suffixes)
    taken_addresses = {row.home_address for row in company.person_private}
    people: list[PersonRow] = []
    private: list[PersonPrivateRow] = []
    openings: list[OpeningRow] = []
    requests: list[RequestRow] = []
    for index, spec in enumerate(specs):
        template = _template(company, spec)
        template_private = next(r for r in company.person_private if r.person_id == template.id)
        template_opening = next(o for o in company.time_off_openings if o.person_id == template.id)
        if any(p.manager_id == template.id for p in company.people):
            msg = f"{spec.key}: the template {template.given_name} is a manager"
            raise ValueError(msg)
        person_id = clone_person_id(company.tenant_id, spec.key)
        people.append(
            replace(
                template,
                id=person_id,
                given_name=spec.given_name,
                family_name=spec.family_name,
                manager_id=manager_id,
                work_email=f"{spec.given_name}.{spec.family_name}@juniperrow.example".lower(),
                is_hr_admin=False,
                persona_key=None,
            )
        )
        if index >= len(free):
            msg = "No unused phone number is left for another clone"
            raise ValueError(msg)
        born = template_private.date_of_birth
        place = location_codes[template.location_id]
        match = _STREET_NUMBER.match(template_private.home_address)
        if match is None:
            msg = f"{spec.key}: can't read the template's address"
            raise ValueError(msg)
        number = int(match.group(1))
        address = template_private.home_address
        while address in taken_addresses:
            number += 1
            address = f"{number} {match.group(2)}"
        taken_addresses.add(address)
        private.append(
            replace(
                template_private,
                person_id=person_id,
                personal_email=(
                    f"{spec.given_name}.{spec.family_name}{born:%y}@example.com".lower()
                ),
                phone=f"{area_codes[place]}-555-01{free[index]}",
                home_address=address,
            )
        )
        openings.append(
            replace(
                template_opening,
                id=uuid5(company.tenant_id, f"opening:fairness:{spec.key}"),
                person_id=person_id,
            )
        )
        # Every time-off request of the template, so the clone's balance and request list are the
        # template's, figure for figure. A decided request names the clone's own manager as its
        # decider, as the seed does for the template's (the deciding person is not a figure).
        for request in company.time_off_requests:
            if request.person_id != template.id:
                continue
            requests.append(
                replace(
                    request,
                    id=uuid5(company.tenant_id, f"fairness:{spec.key}:{request.id}"),
                    person_id=person_id,
                    decided_by=None if request.decided_by is None else manager_id,
                )
            )
    return replace(
        company,
        people=(*company.people, *people),
        person_private=(*company.person_private, *private),
        time_off_openings=(*company.time_off_openings, *openings),
        time_off_requests=(*company.time_off_requests, *requests),
    )


def clone_rows(
    base: SeedCompany, with_clones: SeedCompany
) -> tuple[
    tuple[PersonRow, ...],
    tuple[PersonPrivateRow, ...],
    tuple[OpeningRow, ...],
    tuple[RequestRow, ...],
]:
    """The rows `with_eval_clones` added, in the order it added them: people, private details,
    opening balances, and time-off requests."""
    return (
        with_clones.people[len(base.people) :],
        with_clones.person_private[len(base.person_private) :],
        with_clones.time_off_openings[len(base.time_off_openings) :],
        with_clones.time_off_requests[len(base.time_off_requests) :],
    )
