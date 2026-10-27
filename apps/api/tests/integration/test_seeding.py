"""Seeding a sandbox as the API's login: every row lands, sandboxes never collide, and it's fast.

The time-off rows go through the database's own checks too (the decision columns, the 31-day
limit, nobody deciding their own request, and the exclusion constraint that refuses overlapping
open requests), and the time-off service reads them back: a person's balance and a possible
request, worked out for the date at their location, never the sandbox's anchor date.
"""

import math
import statistics
import time
from dataclasses import astuple, fields
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.base import Base
from app.db.models import Holiday, Tenant
from app.db.tenancy import TenantContext, set_is_hr, tenant_session
from app.domain.holidays import holidays_for
from app.domain.timeoff.evaluate import NewRequest
from app.modules.identity.actor import load_actor
from app.modules.sandbox.seed import ROW_TYPES, SeedCompany, build_company, insert_company
from app.modules.timeoff import service
from app.modules.timeoff.service import Balances
from tests.integration.conftest import TEST_KEYS

pytestmark = pytest.mark.integration

ANCHOR = date(2026, 10, 5)
SANDBOXES_TIMED = 20
P95_LIMIT_SECONDS = 2.0

type TableRows = dict[str, set[tuple[Any, ...]]]


async def create_sandbox(
    engine: AsyncEngine, created_tenant_ids: list[UUID], anchor: date = ANCHOR
) -> SeedCompany:
    """A new tenant row and its seed company, in one transaction, as sandbox creation will do it.

    The tenant is deleted when the test session ends, like every tenant `make_tenant` creates.
    """
    tenant_id = uuid4()
    created_tenant_ids.append(tenant_id)
    company = build_company(tenant_id, anchor)
    expires_at = datetime.now(UTC) + timedelta(hours=24)
    async with tenant_session(engine, TenantContext(tenant_id, None)) as session:
        session.add(Tenant(id=tenant_id, expires_at=expires_at, anchor_date=anchor))
        # The tenant row goes first: every seeded row refers to it.
        await session.flush()
        await insert_company(session, company, TEST_KEYS)
    return company


def rows_built(company: SeedCompany) -> TableRows:
    return {name: {astuple(row) for row in getattr(company, name)} for name in ROW_TYPES}


async def rows_read_back(engine: AsyncEngine, company: SeedCompany) -> TableRows:
    """Every seeded table's rows, read by the API's login inside the company's own sandbox."""
    rows: TableRows = {}
    async with tenant_session(engine, TenantContext(company.tenant_id, None)) as session:
        # As HR, so the private-details rule shows every private row.
        await set_is_hr(session, True)
        for name, row_type in ROW_TYPES.items():
            table = Base.metadata.tables[name]
            columns = [table.c[field.name] for field in fields(row_type)]
            # An array column (a person's weekdays) comes back as a list, and the row as a tuple.
            rows[name] = {
                tuple(tuple(value) if isinstance(value, list) else value for value in row)
                for row in await session.execute(select(*columns))
            }
    return rows


async def test_a_seeded_sandbox_reads_back_exactly_as_built(
    app_engine: AsyncEngine, created_tenant_ids: list[UUID]
) -> None:
    company = await create_sandbox(app_engine, created_tenant_ids)

    read_back = await rows_read_back(app_engine, company)

    # Four years of holidays for each of the four locations.
    holiday_count = sum(
        len(holidays_for(code, year))
        for code in ("den", "oak", "aus", "atl")
        for year in range(ANCHOR.year - 1, ANCHOR.year + 3)
    )
    assert {name: len(rows) for name, rows in read_back.items()} == {
        "locations": 4,
        "departments": 8,
        "people": 145,
        "person_private": 145,
        "holidays": holiday_count,
        "time_off_openings": 145,
        "time_off_requests": len(company.time_off_requests),
    }
    # The history is there, and one request waits for Marcus.
    assert len(company.time_off_requests) > 145
    assert len([row for row in read_back["time_off_requests"] if "pending" in row]) == 1
    assert read_back == rows_built(company)


async def test_two_sandboxes_with_identical_people_coexist(
    app_engine: AsyncEngine, created_tenant_ids: list[UUID]
) -> None:
    # Every unique rule starts with tenant_id. A global rule on work_email, persona_key, a
    # location code, or a department name would refuse the second sandbox.
    first = await create_sandbox(app_engine, created_tenant_ids)
    second = await create_sandbox(app_engine, created_tenant_ids)

    def unique_values(company: SeedCompany) -> tuple[list[str | None], ...]:
        return (
            [person.work_email for person in company.people],
            [person.persona_key for person in company.people],
            [location.code for location in company.locations],
            [department.name for department in company.departments],
        )

    assert unique_values(first) == unique_values(second)
    assert await rows_read_back(app_engine, first) == rows_built(first)
    assert await rows_read_back(app_engine, second) == rows_built(second)


async def test_creating_a_sandbox_takes_under_two_seconds_at_p95(
    app_engine: AsyncEngine, created_tenant_ids: list[UUID]
) -> None:
    durations: list[float] = []
    for _ in range(SANDBOXES_TIMED):
        started = time.perf_counter()
        await create_sandbox(app_engine, created_tenant_ids)
        durations.append(time.perf_counter() - started)

    p50 = statistics.median(durations)
    # The nearest-rank 95th percentile: the 19th fastest of 20.
    p95 = sorted(durations)[math.ceil(0.95 * len(durations)) - 1]
    print(f"\n{SANDBOXES_TIMED} sandboxes: p50 {p50 * 1000:.0f} ms, p95 {p95 * 1000:.0f} ms")
    assert p95 < P95_LIMIT_SECONDS


# ---- The time-off service on a seeded sandbox -----------------------------------------------


def person_named(company: SeedCompany, given_name: str) -> UUID:
    return next(person.id for person in company.people if person.given_name == given_name)


async def balances_as(
    engine: AsyncEngine, company: SeedCompany, actor_id: UUID, person_id: UUID, now: datetime
) -> Balances:
    async with tenant_session(engine, TenantContext(company.tenant_id, actor_id)) as session:
        actor = await load_actor(session, company.tenant_id, actor_id)
        assert actor is not None
        result = await service.balances(session, actor, person_id, now)
    assert isinstance(result, Balances)
    return result


async def test_leos_balance_as_marcus_matches_the_figure_worked_by_hand(
    app_engine: AsyncEngine, created_tenant_ids: list[UUID]
) -> None:
    """Leo is hourly, so he earns 480 minutes on each month's last day, to a ceiling of 8,640
    (144 hours, handbook 4.1). A month's earning is checked against the balance at that month's
    end: the opening plus what he has earned, minus approved PTO on days up to it.

    The seed gives Leo (anchor 2026-10-05, a Monday) an opening of 7,380 minutes as of 2026-01-01
    and two approved PTO requests: Friday and Saturday, January 23 and 24 (both on his Wednesday to
    Sunday week), 2 * 480 = 960; and Wednesday to Friday, September 30 to October 2, 3 * 480 =
    1,440. No holiday falls on any of those days. Today is October 5 in Oakland (noon UTC is 5:00
    there), and the earnings are:

        Jan 31: 7,380 - 960 = 6,420; room 8,640 - 6,420 = 2,220; earns 480; earned 7,860
        Feb 28: 7,860 - 960 = 6,900; room 1,740; earns 480; earned 8,340
        Mar 31: 8,340 - 960 = 7,380; room 1,260; earns 480; earned 8,820
        Apr 30: 8,820 - 960 = 7,860; room 780; earns 480; earned 9,300
        May 31: 9,300 - 960 = 8,340; room 300; earns 300 (the ceiling); earned 9,600
        Jun 30: 9,600 - 960 = 8,640; room 0; earns 0
        Jul 31 and Aug 31: still 8,640 at the ceiling; earn 0
        Sep 30: 9,600 - (960 + 480 for Wednesday the 30th) = 8,160; room 480; earns 480;
                earned 10,080

    So earned is 10,080. Taken (approved, up to today) is 960 + 1,440 = 2,400; nothing is booked
    or pending, so available is 10,080 - 2,400 = 7,680. The next earning is October 31: used by
    then is still 2,400, so 10,080 - 2,400 = 7,680; room 960; it earns 480.
    """
    company = await create_sandbox(app_engine, created_tenant_ids)
    leo, marcus = person_named(company, "Leo"), person_named(company, "Marcus")
    # The seed's inputs, so a change to the draws fails here and not in the arithmetic.
    opening = next(row for row in company.time_off_openings if row.person_id == leo)
    history = [
        (row.start_date, row.end_date, row.amount_minutes)
        for row in company.time_off_requests
        if row.person_id == leo
    ]
    assert (opening.as_of, opening.amount_minutes) == (date(2026, 1, 1), 7_380)
    assert history == [
        (date(2026, 1, 23), date(2026, 1, 24), 960),
        (date(2026, 9, 30), date(2026, 10, 2), 1_440),
    ]

    result = await balances_as(
        app_engine, company, marcus, leo, datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
    )

    assert result.today == date(2026, 10, 5)
    assert (result.pto.earned_minutes, result.pto.taken_minutes) == (10_080, 2_400)
    assert (result.pto.booked_minutes, result.pto.pending_minutes) == (0, 0)
    assert result.pto.available_minutes == 7_680
    assert (result.pto.next_earning, result.pto.next_earning_minutes) == (date(2026, 10, 31), 480)
    assert result.pto.ceiling_minutes == 8_640


async def test_a_sandbox_created_at_3am_utc_still_has_the_evening_before_in_oakland(
    app_engine: AsyncEngine, created_tenant_ids: list[UUID]
) -> None:
    """create_sandbox anchors a sandbox to the UTC date, so one made at 03:00 UTC on October 22 is
    anchored to the 22nd while it is still the evening of the 21st in Oakland. The engine's today
    comes from the location's time zone and never from the anchor date (the backlog's item)."""
    now = datetime(2026, 10, 22, 3, 0, tzinfo=UTC)
    company = await create_sandbox(app_engine, created_tenant_ids, anchor=now.date())
    priya = person_named(company, "Priya")
    assert company.anchor_date == date(2026, 10, 22)

    balances = await balances_as(app_engine, company, priya, priya, now)
    async with tenant_session(app_engine, TenantContext(company.tenant_id, priya)) as session:
        actor = await load_actor(session, company.tenant_id, priya)
        assert actor is not None
        # Wednesday the 21st is Priya's today, and a day she works: not out of range.
        today = await service.check(
            session, actor, NewRequest("pto", date(2026, 10, 21), date(2026, 10, 21), None), now
        )
        # Thursday the 22nd is the anchor date and still tomorrow for her: a valid future day.
        tomorrow = await service.check(
            session, actor, NewRequest("pto", date(2026, 10, 22), date(2026, 10, 22), None), now
        )
        # Tuesday the 20th is already past for her.
        yesterday = await service.check(
            session, actor, NewRequest("pto", date(2026, 10, 20), date(2026, 10, 20), None), now
        )

    assert balances.today == date(2026, 10, 21)
    assert "out-of-range" not in today.problems
    assert today.counted == (date(2026, 10, 21),)
    assert "out-of-range" not in tomorrow.problems
    assert tomorrow.counted == (date(2026, 10, 22),)
    assert "out-of-range" in yesterday.problems


async def test_a_sandbox_created_at_3am_utc_on_january_1_has_the_year_before_in_oakland(
    app_engine: AsyncEngine, created_tenant_ids: list[UUID]
) -> None:
    """Anchor January 1, 2027, created at 03:00 UTC: it is still December 31, 2026 in Oakland,
    before the opening's date. The balance works (earned is the opening, since no month-end has
    passed since it), PTO that starts before the opening is refused, and 2026's holidays are
    seeded."""
    now = datetime(2027, 1, 1, 3, 0, tzinfo=UTC)
    company = await create_sandbox(app_engine, created_tenant_ids, anchor=now.date())
    priya = person_named(company, "Priya")
    opening = next(row for row in company.time_off_openings if row.person_id == priya)
    assert opening.as_of == date(2027, 1, 1)

    balances = await balances_as(app_engine, company, priya, priya, now)
    async with tenant_session(app_engine, TenantContext(company.tenant_id, priya)) as session:
        actor = await load_actor(session, company.tenant_id, priya)
        assert actor is not None
        december_31 = await service.check(
            session, actor, NewRequest("pto", date(2026, 12, 31), date(2026, 12, 31), None), now
        )
        holidays_2026 = (
            await session.execute(
                select(Holiday.name).where(
                    Holiday.holiday_date >= date(2026, 1, 1),
                    Holiday.holiday_date <= date(2026, 12, 31),
                )
            )
        ).all()

    assert balances.today == date(2026, 12, 31)
    assert balances.pto.earned_minutes == opening.amount_minutes
    assert [year.year for year in balances.sick] == [2026]
    assert "out-of-range" in december_31.problems
    assert len(holidays_2026) == sum(
        len(holidays_for(c, 2026)) for c in ("den", "oak", "aus", "atl")
    )
