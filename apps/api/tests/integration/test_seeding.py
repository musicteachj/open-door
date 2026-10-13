"""Seeding a sandbox as the API's login: every row lands, sandboxes never collide, and it's fast."""

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
from app.db.models import Tenant
from app.db.tenancy import TenantContext, set_is_hr, tenant_session
from app.modules.sandbox.seed import ROW_TYPES, SeedCompany, build_company, insert_company

pytestmark = pytest.mark.integration

ANCHOR = date(2026, 10, 5)
SANDBOXES_TIMED = 20
P95_LIMIT_SECONDS = 2.0

type TableRows = dict[str, set[tuple[Any, ...]]]


async def create_sandbox(engine: AsyncEngine, created_tenant_ids: list[UUID]) -> SeedCompany:
    """A new tenant row and its seed company, in one transaction, as sandbox creation will do it.

    The tenant is deleted when the test session ends, like every tenant `make_tenant` creates.
    """
    tenant_id = uuid4()
    created_tenant_ids.append(tenant_id)
    company = build_company(tenant_id, ANCHOR)
    expires_at = datetime.now(UTC) + timedelta(hours=24)
    async with tenant_session(engine, TenantContext(tenant_id, None)) as session:
        session.add(Tenant(id=tenant_id, expires_at=expires_at, anchor_date=ANCHOR))
        # The tenant row goes first: every seeded row refers to it.
        await session.flush()
        await insert_company(session, company)
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
            rows[name] = {tuple(row) for row in await session.execute(select(*columns))}
    return rows


async def test_a_seeded_sandbox_reads_back_exactly_as_built(
    app_engine: AsyncEngine, created_tenant_ids: list[UUID]
) -> None:
    company = await create_sandbox(app_engine, created_tenant_ids)

    read_back = await rows_read_back(app_engine, company)

    assert {name: len(rows) for name, rows in read_back.items()} == {
        "locations": 4,
        "departments": 8,
        "people": 145,
        "person_private": 145,
        "holidays": 54,
    }
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
