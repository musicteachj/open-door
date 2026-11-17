"""The reply-by date against a seeded sandbox, across the year's end."""

from datetime import UTC, date, datetime
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.models import Holiday, Location
from app.domain.cases import HQ_LOCATION_CODE
from app.modules.cases import queries
from tests.integration.test_seeded_cases import acting, persona, seed_as

pytestmark = pytest.mark.integration

LATE_DECEMBER = date(2026, 12, 28)


async def test_a_sandbox_seeded_in_late_december_skips_new_years_day(
    app_engine: AsyncEngine, created_tenant_ids: list[UUID]
) -> None:
    company, _ = await seed_as(app_engine, created_tenant_ids, "priya", LATE_DECEMBER)

    async with acting(app_engine, company, persona(company, "priya")) as (db, _):
        denver = (
            await db.execute(
                select(Location.id).where(
                    Location.tenant_id == company.tenant_id, Location.code == HQ_LOCATION_CODE
                )
            )
        ).scalar_one()
        holidays = set(
            await db.scalars(
                select(Holiday.holiday_date).where(
                    Holiday.tenant_id == company.tenant_id, Holiday.location_id == denver
                )
            )
        )
        # Wed Dec 30 2026, 9 AM in Denver (MST, UTC-7). Thu Dec 31 is business day 1, Fri Jan 1 2027
        # is closed, the weekend is skipped, and Mon Jan 4 is day 2.
        sent = datetime(2026, 12, 30, 16, 0, tzinfo=UTC)
        reply_by = await queries.reply_by_at(db, company.tenant_id, sent)

    assert date(2027, 1, 1) in holidays
    assert reply_by == date(2027, 1, 4)
