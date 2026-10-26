"""The seed company: the same fictional company of 145 people in every sandbox.

`build_company` builds it in memory, and `insert_company` writes it into a sandbox. Names come
from fixed lists and every other choice from a fixed seed. IDs are uuid5 of the tenant ID and a
stable key, so only the IDs differ between sandboxes. Dates count back from the tenant's anchor
date, so "last week" always means last week.

Time off (Phase 5) is part of the company too: every person's working weekdays, an opening PTO
balance, a few approved PTO requests and the odd recorded sick day in the past, and one pending
request in Marcus's queue. They are drawn from a stream of their own, so nobody who already
existed changes. The engine (app.domain.timeoff) does all the counting here: no day or amount in
the history is worked out by hand.
"""

import random
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, fields
from datetime import UTC, date, datetime, time, timedelta
from typing import cast
from uuid import UUID, uuid5

from sqlalchemy import Insert, Text, bindparam, func, insert, select
from sqlalchemy import cast as sql_cast
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession

# Importing the models puts their tables on Base.metadata.
from app.db import models  # noqa: F401
from app.db.base import Base
from app.domain.holidays import holidays_for
from app.domain.timeoff.charges import charge_days
from app.domain.timeoff.counting import count_days
from app.domain.timeoff.model import (
    DAY_MINUTES,
    HALF_DAY_MINUTES,
    EmploymentType,
    LeaveType,
    Opening,
    RequestStatus,
    Schedule,
    State,
)
from app.domain.timeoff.model import Person as EnginePerson
from app.domain.timeoff.model import Request as EngineRequest
from app.domain.timeoff.pto import MONTHLY_RATE_MINUTES, pto_balance
from app.domain.timeoff.sick import sick_years
from app.modules.sandbox.seed_data import (
    ATLANTA_FAMILY_NAMES,
    ATLANTA_GIVEN_NAMES,
    FAMILY_NAMES,
    GIVEN_NAMES,
    LAST_WEEK_PTO_SEAT,
    LOCATIONS,
    ORG,
    PENDING_REQUEST_SEAT,
    PERSONAL_EMAIL_DOMAIN,
    SEED,
    STREET_NAMES,
    STREET_TYPES,
    TIME_OFF_STREAM,
    WORK_EMAIL_DOMAIN,
    LocationSpec,
    PersonSpec,
    Position,
)

# Everyone drawn from the seed is 22 to 63 years old, was hired at 19 or older, and joined between
# a month and 12 years before the anchor date.
YOUNGEST_DAYS = 22 * 365
OLDEST_DAYS = 64 * 365
YOUNGEST_AT_HIRE_DAYS = 19 * 365
NEWEST_HIRE_DAYS = 30
LONGEST_TENURE_DAYS = 12 * 365

# Holidays are seeded from the year before the anchor to two years after it. A sandbox lives 24
# hours, so a person's today can be a day before the anchor (Americas, early UTC) or two days
# after it, across New Year. The engine refuses a request that ends after December 31 of the year
# after today, which is at most the anchor year + 2. The year before is for leave taken over the
# holidays just before an anchor in early January.
HOLIDAY_YEARS_BEFORE = 1
HOLIDAY_YEARS_AFTER = 2

# Time off. An opening is drawn in whole hours, from a day's worth up to a 12-hour margin below
# the ceiling, so it is always strictly below it and a month's earning on the opening's own day
# (at most 10 hours) is never cut short. The floor lets the fixed requests (Leo's three days, and
# Zara's two) always fit.
OPENING_FLOOR_HOURS = 24
OPENING_HEADROOM_HOURS = 12
# The ceiling is 1.5 times the year's earning (handbook 4.1).
CEILING_MONTHS = 18
# History starts two weeks after a hire, and a request is made two to 21 days before it starts.
MIN_DAYS_AFTER_HIRE = 14
LEAST_LEAD_DAYS = 2
MOST_LEAD_DAYS = 21
# The pending request starts about three weeks after the anchor: the first two scheduled days in a
# row on or after this many days later.
PENDING_DAYS_AHEAD = 21
PENDING_SEARCH_DAYS = 30
PTO_ATTEMPTS = (2, 4)
SICK_ATTEMPTS = (0, 2)
PTO_LENGTHS = (1, 1, 2, 3, 5)
# One in this many single days is a half day.
HALF_DAY_ONE_IN = 4


@dataclass(frozen=True, slots=True)
class LocationRow:
    id: UUID
    tenant_id: UUID
    code: str
    name: str
    city: str
    state: str
    timezone: str


@dataclass(frozen=True, slots=True)
class DepartmentRow:
    id: UUID
    tenant_id: UUID
    name: str


@dataclass(frozen=True, slots=True)
class PersonRow:
    id: UUID
    tenant_id: UUID
    given_name: str
    family_name: str
    title: str
    department_id: UUID
    location_id: UUID
    manager_id: UUID | None
    work_email: str
    employment_type: str
    hire_date: date
    is_hr_admin: bool
    persona_key: str | None
    # The ISO weekdays the person works, sorted: 1 is Monday and 7 is Sunday.
    scheduled_weekdays: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class PersonPrivateRow:
    person_id: UUID
    tenant_id: UUID
    personal_email: str
    phone: str
    home_address: str
    date_of_birth: date


@dataclass(frozen=True, slots=True)
class HolidayRow:
    id: UUID
    tenant_id: UUID
    location_id: UUID
    holiday_date: date
    name: str


@dataclass(frozen=True, slots=True)
class OpeningRow:
    id: UUID
    tenant_id: UUID
    person_id: UUID
    as_of: date
    amount_minutes: int
    created_at: datetime


@dataclass(frozen=True, slots=True)
class RequestRow:
    id: UUID
    tenant_id: UUID
    person_id: UUID
    type: str
    start_date: date
    end_date: date
    partial_minutes: int | None
    amount_minutes: int
    status: str
    created_at: datetime
    created_via: str
    proposal_id: UUID | None
    decided_by: UUID | None
    decided_at: datetime | None
    decision_note: str | None
    canceled_at: datetime | None


type Row = (
    LocationRow
    | DepartmentRow
    | PersonRow
    | PersonPrivateRow
    | HolidayRow
    | OpeningRow
    | RequestRow
)

# The tables the seed fills, parents first, each with its row type. A row type's fields are
# exactly its table's columns, under the same names: insert_company relies on that, and a test
# checks it against the models.
ROW_TYPES: dict[str, type[Row]] = {
    "locations": LocationRow,
    "departments": DepartmentRow,
    "people": PersonRow,
    "person_private": PersonPrivateRow,
    "holidays": HolidayRow,
    "time_off_openings": OpeningRow,
    "time_off_requests": RequestRow,
}


@dataclass(frozen=True, slots=True)
class SeedCompany:
    """One sandbox's seed rows. The fields after the first two are named after their tables."""

    tenant_id: UUID
    anchor_date: date
    locations: tuple[LocationRow, ...]
    departments: tuple[DepartmentRow, ...]
    people: tuple[PersonRow, ...]
    person_private: tuple[PersonPrivateRow, ...]
    holidays: tuple[HolidayRow, ...]
    time_off_openings: tuple[OpeningRow, ...]
    time_off_requests: tuple[RequestRow, ...]


class _Draws:
    """Seeded choices, all made through random.random().

    Python keeps random()'s sequence the same across versions for the same seed, which it doesn't
    promise for choice() or shuffle(). So upgrading Python can't quietly change the company.
    """

    def __init__(self, seed: int) -> None:
        # Not for security: the point is that every sandbox gets the same choices.
        self._random = random.Random(seed)  # noqa: S311

    def below(self, limit: int) -> int:
        """A whole number from 0 up to, but not including, `limit`."""
        return int(self._random.random() * limit)

    def between(self, low: int, high: int) -> int:
        """A whole number from `low` to `high`, both included."""
        return low + self.below(high - low + 1)

    def pick[T](self, items: Sequence[T]) -> T:
        return items[self.below(len(items))]

    def shuffled[T](self, items: Sequence[T]) -> list[T]:
        """A shuffled copy of `items` (a Fisher-Yates shuffle)."""
        result = list(items)
        for index in range(len(result) - 1, 0, -1):
            other = self.below(index + 1)
            result[index], result[other] = result[other], result[index]
        return result


@dataclass(frozen=True, slots=True)
class _Seat:
    key: str
    department: str
    location: LocationSpec
    position: Position
    weekdays: tuple[int, ...]


def build_company(tenant_id: UUID, anchor_date: date) -> SeedCompany:
    """Build one sandbox's company in memory. Pure: equal arguments always give equal rows."""

    def make_id(kind: str, key: str) -> UUID:
        return uuid5(tenant_id, f"{kind}:{key}")

    draws = _Draws(SEED)
    # Each location opened later has its own stream, so the draws of the original three are the
    # same as before it opened: nobody who already existed changes. Atlanta is stream 1.
    later_draws = _Draws(SEED + 1)
    streams = {0: draws, 1: later_draws}
    seats = list(_seats())
    person_ids = {seat.key: make_id("person", seat.key) for seat in seats}
    # Names are taken from the end, so the older names go first and the Atlanta names are the
    # last in line.
    given_names = later_draws.shuffled(ATLANTA_GIVEN_NAMES) + draws.shuffled(GIVEN_NAMES)
    family_names = later_draws.shuffled(ATLANTA_FAMILY_NAMES) + draws.shuffled(FAMILY_NAMES)
    phone_numbers = {
        spec.code: iter(streams[spec.seed_stream].shuffled(range(100))) for spec in LOCATIONS
    }
    people: list[PersonRow] = []
    private: list[PersonPrivateRow] = []
    for seat in seats:
        who = seat.position.person or _someone(draws, given_names.pop(), family_names.pop())
        manager = seat.position.manager
        location = seat.location
        people.append(
            PersonRow(
                id=person_ids[seat.key],
                tenant_id=tenant_id,
                given_name=who.given_name,
                family_name=who.family_name,
                title=seat.position.title,
                department_id=make_id("department", seat.department),
                location_id=make_id("location", location.code),
                manager_id=None if manager is None else person_ids[manager],
                work_email=f"{who.given_name}.{who.family_name}@{WORK_EMAIL_DOMAIN}".lower(),
                employment_type=seat.position.employment_type,
                hire_date=anchor_date - timedelta(days=who.hired_days_ago),
                is_hr_admin=who.is_hr_admin,
                persona_key=who.persona_key,
                scheduled_weekdays=seat.weekdays,
            )
        )
        born = anchor_date - timedelta(days=who.born_days_ago)
        personal_email = f"{who.given_name}.{who.family_name}{born:%y}@{PERSONAL_EMAIL_DOMAIN}"
        private.append(
            PersonPrivateRow(
                person_id=person_ids[seat.key],
                tenant_id=tenant_id,
                personal_email=personal_email.lower(),
                phone=f"{location.area_code}-555-01{next(phone_numbers[location.code]):02d}",
                home_address=_address(draws, location),
                date_of_birth=born,
            )
        )

    holidays = tuple(
        HolidayRow(
            make_id("holiday", f"{spec.code}:{holiday.holiday_date.isoformat()}"),
            tenant_id,
            make_id("location", spec.code),
            holiday.holiday_date,
            holiday.name,
        )
        for spec in LOCATIONS
        for year in range(
            anchor_date.year - HOLIDAY_YEARS_BEFORE, anchor_date.year + HOLIDAY_YEARS_AFTER + 1
        )
        for holiday in holidays_for(spec.code, year)
    )
    # Time off has a stream of its own, so the draws above (and so every person, phone, and
    # address) are exactly what they were before it existed.
    openings, requests = _time_off(
        tenant_id, anchor_date, seats, people, holidays, _Draws(SEED + TIME_OFF_STREAM)
    )

    return SeedCompany(
        tenant_id=tenant_id,
        anchor_date=anchor_date,
        locations=tuple(
            LocationRow(
                make_id("location", spec.code),
                tenant_id,
                spec.code,
                spec.name,
                spec.city,
                spec.state,
                spec.timezone,
            )
            for spec in LOCATIONS
        ),
        departments=tuple(
            DepartmentRow(make_id("department", name), tenant_id, name)
            for name in dict.fromkeys(department for department, _ in ORG)
        ),
        people=tuple(people),
        person_private=tuple(private),
        holidays=holidays,
        time_off_openings=tuple(openings),
        time_off_requests=tuple(requests),
    )


def _seats() -> Iterator[_Seat]:
    """Every seat in the org chart, in order. A position's several seats are numbered from 1."""
    locations = {spec.code: spec for spec in LOCATIONS}
    # How many seats at each location have taken a turn in its rotation, for the seats that
    # don't set their own weekdays.
    turns = dict.fromkeys(locations, 0)
    for (department, location_code), positions in ORG.items():
        location = locations[location_code]
        for position in positions:
            for number in range(1, position.seats + 1):
                key = position.key if position.seats == 1 else f"{position.key}-{number}"
                if position.weekdays is None:
                    weekdays = location.rotation[turns[location_code] % len(location.rotation)]
                    turns[location_code] += 1
                else:
                    weekdays = position.weekdays
                yield _Seat(key, department, location, position, weekdays)


def _someone(draws: _Draws, given_name: str, family_name: str) -> PersonSpec:
    """A person drawn from the seed, for a seat without a named person."""
    born_days_ago = draws.between(YOUNGEST_DAYS, OLDEST_DAYS)
    longest = min(LONGEST_TENURE_DAYS, born_days_ago - YOUNGEST_AT_HIRE_DAYS)
    return PersonSpec(
        given_name, family_name, draws.between(NEWEST_HIRE_DAYS, longest), born_days_ago
    )


def _address(draws: _Draws, location: LocationSpec) -> str:
    """A made-up street address in the location's city."""
    street = f"{draws.between(100, 9899)} {draws.pick(STREET_NAMES)} {draws.pick(STREET_TYPES)}"
    return f"{street}, {location.city}, {location.state} {draws.pick(location.zip_codes)}"


def _time_off(
    tenant_id: UUID,
    anchor_date: date,
    seats: Sequence[_Seat],
    people: Sequence[PersonRow],
    holidays: Sequence[HolidayRow],
    draws: _Draws,
) -> tuple[list[OpeningRow], list[RequestRow]]:
    """Every person's opening balance and request history, in seat order.

    `seats` and `people` are parallel. An opening is the balance at the start of its date, before
    that day's earning: January 1 of the anchor year, or the hire date if later, where it is 0.
    """
    calendars: dict[UUID, dict[date, str]] = {}
    for holiday in holidays:
        calendars.setdefault(holiday.location_id, {})[holiday.holiday_date] = holiday.name
    january_1 = date(anchor_date.year, 1, 1)
    openings: list[OpeningRow] = []
    requests: list[RequestRow] = []
    for seat, person in zip(seats, people, strict=True):
        employment_type = cast(EmploymentType, person.employment_type)
        engine_person = EnginePerson(
            employment_type=employment_type,
            state=cast(State, seat.location.state),
            hire_date=person.hire_date,
            schedule=Schedule(frozenset(person.scheduled_weekdays)),
        )
        as_of = max(january_1, person.hire_date)
        if person.hire_date >= january_1:
            amount = 0
        else:
            ceiling_hours = MONTHLY_RATE_MINUTES[employment_type] * CEILING_MONTHS // 60
            amount = 60 * draws.between(OPENING_FLOOR_HOURS, ceiling_hours - OPENING_HEADROOM_HOURS)
        opening = Opening(as_of, amount)
        openings.append(
            OpeningRow(
                id=uuid5(tenant_id, f"opening:{seat.key}"),
                tenant_id=tenant_id,
                person_id=person.id,
                as_of=as_of,
                amount_minutes=amount,
                created_at=datetime.combine(as_of, time(), tzinfo=UTC),
            )
        )
        history = _History(
            tenant_id,
            anchor_date,
            seat.key,
            person,
            engine_person,
            opening,
            calendars[person.location_id],
            draws,
        )
        requests.extend(
            history.build(
                last_week_pto=seat.key == LAST_WEEK_PTO_SEAT,
                pending_pto=seat.key == PENDING_REQUEST_SEAT,
            )
        )
    return openings, requests


class _History:
    """One person's requests, chosen one at a time.

    A request joins only if the engine counts at least one day in it, it overlaps none of the
    person's others, and PTO and every sick year are still at zero or more at the anchor and the
    day before it. The amount is always the engine's charge. Nothing here works out a day or an
    amount itself.
    """

    def __init__(
        self,
        tenant_id: UUID,
        anchor_date: date,
        seat_key: str,
        person: PersonRow,
        engine_person: EnginePerson,
        opening: Opening,
        holidays: Mapping[date, str],
        draws: _Draws,
    ) -> None:
        self._tenant_id = tenant_id
        self._anchor = anchor_date
        self._seat_key = seat_key
        self._person = person
        self._engine_person = engine_person
        self._opening = opening
        self._holidays = holidays
        self._draws = draws
        self._stored: list[EngineRequest] = []
        self._rows: list[RequestRow] = []

    def build(self, *, last_week_pto: bool, pending_pto: bool) -> list[RequestRow]:
        """The person's requests: the fixed ones first, so the random ones make way for them."""
        if last_week_pto:
            # Wednesday to Friday of the week before the one the anchor is in. It is kept even
            # when it falls before the opening (an anchor in early January): the engine ignores
            # PTO before an opening, which already reflects it.
            monday = self._anchor - timedelta(days=self._anchor.weekday() + 7)
            self._add_fixed("pto-last-week", monday + timedelta(days=2), monday + timedelta(days=4))
        if pending_pto:
            start = self._first_two_scheduled_days(
                self._anchor + timedelta(days=PENDING_DAYS_AHEAD)
            )
            self._add_fixed("pto-pending", start, start + timedelta(days=1), status="pending")
        self._add_pto()
        self._add_sick()
        return sorted(self._rows, key=lambda row: (row.start_date, row.id))

    def _add_fixed(self, name: str, start: date, end: date, status: str = "approved") -> None:
        if not self._add(name, "pto", start, end, None, status):
            msg = f"The seed's fixed request {self._seat_key}:{name} doesn't fit"
            raise ValueError(msg)

    def _first_two_scheduled_days(self, earliest: date) -> date:
        for offset in range(PENDING_SEARCH_DAYS):
            day = earliest + timedelta(days=offset)
            both = (day, day + timedelta(days=1))
            if count_days(self._engine_person, day, both[1], self._holidays).counted == both:
                return day
        msg = f"{self._seat_key} has no two scheduled days in a row after {earliest}"
        raise ValueError(msg)

    def _add_pto(self) -> None:
        first = max(
            self._opening.as_of, self._person.hire_date + timedelta(days=MIN_DAYS_AFTER_HIRE)
        )
        last = self._anchor - timedelta(days=1)
        for attempt in range(self._draws.between(*PTO_ATTEMPTS)):
            length = self._draws.pick(PTO_LENGTHS)
            half_day = length == 1 and self._draws.below(HALF_DAY_ONE_IN) == 0
            latest_start = last - timedelta(days=length - 1)
            if latest_start < first:
                continue
            start = first + timedelta(days=self._draws.below((latest_start - first).days + 1))
            self._add(
                f"pto-{attempt + 1}",
                "pto",
                start,
                start + timedelta(days=length - 1),
                HALF_DAY_MINUTES if half_day else None,
                "approved",
            )

    def _add_sick(self) -> None:
        first = max(self._opening.as_of, self._person.hire_date + timedelta(days=1))
        last = self._anchor - timedelta(days=1)
        for attempt in range(self._draws.between(*SICK_ATTEMPTS)):
            if last < first:
                continue
            day = first + timedelta(days=self._draws.below((last - first).days + 1))
            hours = self._draws.between(2, DAY_MINUTES // 60)
            partial = None if hours * 60 == DAY_MINUTES else hours * 60
            self._add(f"sick-{attempt + 1}", "sick", day, day, partial, "recorded")

    def _add(
        self,
        name: str,
        kind: str,
        start: date,
        end: date,
        partial_minutes: int | None,
        status: str,
    ) -> bool:
        """Add the request if it fits. The database refuses a PTO decision with no one to make it,
        so the person without a manager (the CEO) gets no approved PTO."""
        if status == "approved" and self._person.manager_id is None:
            return False
        charges = charge_days(self._engine_person, start, end, partial_minutes, self._holidays)
        if not charges:
            return False
        if any(r.start <= end and start <= r.end for r in self._stored):
            return False
        candidate = EngineRequest(
            f"{self._seat_key}:{name}",
            cast(LeaveType, kind),
            start,
            end,
            partial_minutes,
            cast(RequestStatus, status),
        )
        trial = (*self._stored, candidate)
        # A person's today can be the day before the anchor (a sandbox made early in the UTC day,
        # viewed from the Americas). Earning only grows with today, and what is taken or booked
        # is the same total for either day, so the day before is the strictest: a month-end
        # anchor's earning can't be what makes the history affordable.
        for today in (self._anchor - timedelta(days=1), self._anchor):
            balance = pto_balance(self._engine_person, self._opening, trial, self._holidays, today)
            years = sick_years(self._engine_person, trial, self._holidays, today)
            if balance.available_minutes < 0 or any(y.available_minutes < 0 for y in years):
                return False
        self._stored.append(candidate)
        self._rows.append(
            self._row(name, kind, start, end, partial_minutes, sum(m for _, m in charges), status)
        )
        return True

    def _row(
        self,
        name: str,
        kind: str,
        start: date,
        end: date,
        partial_minutes: int | None,
        amount_minutes: int,
        status: str,
    ) -> RequestRow:
        decided_by = decided_at = None
        if status == "recorded":
            # A sick day is recorded on the day itself.
            created_at = datetime.combine(start, time(14), tzinfo=UTC)
        elif status == "pending":
            created_at = datetime.combine(self._anchor - timedelta(days=2), time(17), tzinfo=UTC)
        else:
            # Made a couple of weeks ahead (never before the hire), and decided within a day or
            # so, always before the first day.
            lead = self._draws.between(LEAST_LEAD_DAYS, MOST_LEAD_DAYS)
            lead = max(LEAST_LEAD_DAYS, min(lead, (start - self._person.hire_date).days - 1))
            created_at = datetime.combine(start - timedelta(days=lead), time(15), tzinfo=UTC)
            decided_at = created_at + timedelta(hours=self._draws.between(1, 30))
            decided_by = self._person.manager_id
        return RequestRow(
            id=uuid5(self._tenant_id, f"timeoff:{self._seat_key}:{name}"),
            tenant_id=self._tenant_id,
            person_id=self._person.id,
            type=kind,
            start_date=start,
            end_date=end,
            partial_minutes=partial_minutes,
            amount_minutes=amount_minutes,
            status=status,
            created_at=created_at,
            created_via="ui",
            proposal_id=None,
            decided_by=decided_by,
            decided_at=decided_at,
            decision_note=None,
            canceled_at=None,
        )


async def insert_company(session: AsyncSession, company: SeedCompany) -> None:
    """Write the company into its sandbox, inside the caller's transaction.

    The session must be scoped to the company's tenant (see app/db/tenancy.py), or row-level
    security refuses every row. Each table takes one INSERT ... SELECT FROM unnest(...), parents
    first, with each column's values sent as one typed array. COPY would be faster, but Postgres
    refuses it into a table under row-level security. Nothing is read back: the private-details
    rule would refuse a RETURNING on person_private.

    A column that is itself an array (a person's weekdays) can't go in as an array of arrays, since
    unnest would flatten it into one long column. Each person's value goes in as one text literal,
    like '{3,4,5,6,7}', and the SELECT casts it back to the column's type.
    """
    for table_name in ROW_TYPES:
        await _insert_rows(session, table_name, getattr(company, table_name))


async def insert_time_off_requests(session: AsyncSession, rows: Sequence[RequestRow]) -> None:
    """Write more time-off requests into a sandbox the company is already in, the same way the
    company's own are written (so the table's constraints hold for them too). The eval harness
    adds the requests its questions need after the seed; the demo's seed never does."""
    await _insert_rows(session, "time_off_requests", rows)


async def _insert_rows(session: AsyncSession, table_name: str, rows: Sequence[Row]) -> None:
    row_type = ROW_TYPES[table_name]
    array_columns = _ARRAY_COLUMNS[table_name]
    values = {
        field.name: [
            _array_literal(getattr(row, field.name))
            if field.name in array_columns
            else getattr(row, field.name)
            for row in rows
        ]
        for field in fields(row_type)
    }
    await session.execute(_INSERTS[table_name], values)


def _array_literal(items: Sequence[int]) -> str:
    return "{" + ",".join(str(item) for item in items) + "}"


def _unnest_insert(table_name: str, row_type: type[Row]) -> Insert:
    """INSERT INTO <table> (<columns>) SELECT ... FROM unnest(<one typed array per column>)."""
    table = Base.metadata.tables[table_name]
    names = [field.name for field in fields(row_type)]
    array_columns = _ARRAY_COLUMNS[table_name]
    arrays = [
        bindparam(name, type_=ARRAY(Text() if name in array_columns else table.c[name].type))
        for name in names
    ]
    unnested = func.unnest(*arrays).table_valued(*names).render_derived(name="seed")
    selected = [
        sql_cast(unnested.c[name], table.c[name].type)
        if name in array_columns
        else unnested.c[name]
        for name in names
    ]
    return insert(table).from_select(names, select(*selected))


# The columns that are arrays in their table, by table (see insert_company).
_ARRAY_COLUMNS = {
    name: {
        field.name
        for field in fields(row_type)
        if isinstance(Base.metadata.tables[name].c[field.name].type, ARRAY)
    }
    for name, row_type in ROW_TYPES.items()
}
# Built once, from the models, so each array's type always matches its column.
_INSERTS = {name: _unnest_insert(name, row_type) for name, row_type in ROW_TYPES.items()}
