"""The SQL applicability filter keeps exactly the sections the pure `applies` keeps."""

from itertools import product

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models import HandbookSection
from app.domain.handbook.applicability import Asker, applies
from app.domain.handbook.models import Audience
from app.modules.handbook.queries import applies_to
from app.modules.sandbox.seed_data import LOCATIONS

pytestmark = pytest.mark.integration

STATES = sorted({location.state for location in LOCATIONS})
CODES = [location.code for location in LOCATIONS]
EMPLOYMENT_TYPES = ["salaried", "hourly"]


def audience_of(raw: dict[str, list[str]]) -> Audience:
    return Audience(
        states=tuple(raw.get("states", ())),
        employment_types=tuple(raw.get("employmentTypes", ())),
        locations=tuple(raw.get("locations", ())),
    )


async def test_the_sql_filter_agrees_with_applies_for_every_section_and_asker(
    app_engine: AsyncEngine,
) -> None:
    async with AsyncSession(app_engine) as session:
        # The newest published version is the real handbook (or whatever `make db` loaded).
        sections = (await session.execute(select(HandbookSection))).scalars().all()
        assert len(sections) > 20
        askers = [Asker(*combo) for combo in product(STATES, EMPLOYMENT_TYPES, CODES)]
        # Includes combinations no seed person has, such as a Texan in Denver.
        assert len(askers) == 32  # 4 states x 2 employment types x 4 locations

        for asker in askers:
            kept = set(
                (await session.scalars(select(HandbookSection.id).where(applies_to(asker)))).all()
            )
            expected = {s.id for s in sections if applies(audience_of(s.audience), asker)}
            assert kept == expected, asker


async def test_a_missing_or_empty_list_does_not_restrict(app_engine: AsyncEngine) -> None:
    asker = Asker("TX", "hourly", "aus")
    async with AsyncSession(app_engine) as session:
        sections = (await session.execute(select(HandbookSection))).scalars().all()
        everyone = [s for s in sections if not any(s.audience.get(k) for k in s.audience)]
        assert everyone, "the handbook has sections for everyone"
        kept = set(
            (await session.scalars(select(HandbookSection.id).where(applies_to(asker)))).all()
        )
        assert {s.id for s in everyone} <= kept
