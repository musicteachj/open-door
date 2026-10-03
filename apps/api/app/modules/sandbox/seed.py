"""The seed company: the same fictional company of 120 people in every sandbox.

`build_company` builds it in memory, and `insert_company` writes it into a sandbox. Names come
from fixed lists and every other choice from a fixed seed. IDs are uuid5 of the tenant ID and a
stable key, so only the IDs differ between sandboxes. Dates count back from the tenant's anchor
date, so "last week" always means last week.
"""

import random
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, fields
from datetime import date, timedelta
from uuid import UUID, uuid5

from sqlalchemy import Insert, bindparam, func, insert, select
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession

# Importing the models puts their tables on Base.metadata.
from app.db import models  # noqa: F401
from app.db.base import Base
from app.domain.holidays import holidays_for
from app.modules.sandbox.seed_data import (
    FAMILY_NAMES,
    GIVEN_NAMES,
    LOCATIONS,
    ORG,
    PERSONAL_EMAIL_DOMAIN,
    SEED,
    STREET_NAMES,
    STREET_TYPES,
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


type Row = LocationRow | DepartmentRow | PersonRow | PersonPrivateRow | HolidayRow

# The tables the seed fills, parents first, each with its row type. A row type's fields are
# exactly its table's columns, under the same names: insert_company relies on that, and a test
# checks it against the models.
ROW_TYPES: dict[str, type[Row]] = {
    "locations": LocationRow,
    "departments": DepartmentRow,
    "people": PersonRow,
    "person_private": PersonPrivateRow,
    "holidays": HolidayRow,
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


def build_company(tenant_id: UUID, anchor_date: date) -> SeedCompany:
    """Build one sandbox's company in memory. Pure: equal arguments always give equal rows."""

    def make_id(kind: str, key: str) -> UUID:
        return uuid5(tenant_id, f"{kind}:{key}")

    draws = _Draws(SEED)
    seats = list(_seats())
    person_ids = {seat.key: make_id("person", seat.key) for seat in seats}
    given_names = draws.shuffled(GIVEN_NAMES)
    family_names = draws.shuffled(FAMILY_NAMES)
    phone_numbers = {spec.code: iter(draws.shuffled(range(100))) for spec in LOCATIONS}
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
        holidays=tuple(
            HolidayRow(
                make_id("holiday", f"{spec.code}:{holiday.holiday_date.isoformat()}"),
                tenant_id,
                make_id("location", spec.code),
                holiday.holiday_date,
                holiday.name,
            )
            for spec in LOCATIONS
            for year in (anchor_date.year, anchor_date.year + 1)
            for holiday in holidays_for(spec.code, year)
        ),
    )


def _seats() -> Iterator[_Seat]:
    """Every seat in the org chart, in order. A position's several seats are numbered from 1."""
    locations = {spec.code: spec for spec in LOCATIONS}
    for (department, location_code), positions in ORG.items():
        for position in positions:
            for number in range(1, position.seats + 1):
                key = position.key if position.seats == 1 else f"{position.key}-{number}"
                yield _Seat(key, department, locations[location_code], position)


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


async def insert_company(session: AsyncSession, company: SeedCompany) -> None:
    """Write the company into its sandbox, inside the caller's transaction.

    The session must be scoped to the company's tenant (see app/db/tenancy.py), or row-level
    security refuses every row. Each table takes one INSERT ... SELECT FROM unnest(...), parents
    first, with each column's values sent as one typed array. COPY would be faster, but Postgres
    refuses it into a table under row-level security. Nothing is read back: the private-details
    rule would refuse a RETURNING on person_private.
    """
    for table_name, row_type in ROW_TYPES.items():
        rows: tuple[Row, ...] = getattr(company, table_name)
        values = {
            field.name: [getattr(row, field.name) for row in rows] for field in fields(row_type)
        }
        await session.execute(_INSERTS[table_name], values)


def _unnest_insert(table_name: str, row_type: type[Row]) -> Insert:
    """INSERT INTO <table> (<columns>) SELECT ... FROM unnest(<one typed array per column>)."""
    table = Base.metadata.tables[table_name]
    names = [field.name for field in fields(row_type)]
    arrays = [bindparam(name, type_=ARRAY(table.c[name].type)) for name in names]
    unnested = func.unnest(*arrays).table_valued(*names).render_derived(name="seed")
    return insert(table).from_select(names, select(*unnested.c))


# Built once, from the models, so each array's type always matches its column.
_INSERTS = {name: _unnest_insert(name, row_type) for name, row_type in ROW_TYPES.items()}
