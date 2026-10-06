"""The directory's counts, against a seeded sandbox: its real numbers, and the count rule."""

from dataclasses import replace
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.modules.identity.actor import load_actor
from app.modules.people.queries import DirectoryFilters, directory_facets
from app.modules.sandbox.seed import PersonRow, SeedCompany
from tests.integration.test_directory_queries import listed, open_session

pytestmark = pytest.mark.integration


def persona(company: SeedCompany, key: str) -> PersonRow:
    return next(p for p in company.people if p.persona_key == key)


async def reports_of(session: AsyncSession, company: SeedCompany, key: str) -> frozenset[UUID]:
    """The persona's direct and indirect reports, from the query the API runs on every request."""
    actor = await load_actor(session, company.tenant_id, persona(company, key).id)
    assert actor is not None
    return actor.report_ids


async def test_the_seeds_real_numbers(app_engine: AsyncEngine, seeded_sandbox: SeedCompany) -> None:
    async with open_session(app_engine, seeded_sandbox) as session:
        team = await reports_of(session, seeded_sandbox, "marcus")
        facets = await directory_facets(session, filters=DirectoryFilters(), team_ids=team)

    assert (facets.total, facets.matching, facets.my_team) == (120, 120, 44)
    assert [(loc.name, loc.state, loc.count) for loc in facets.locations] == [
        ("Austin warehouse", "TX", 35),
        ("Denver HQ", "CO", 40),
        ("Oakland store", "CA", 45),
    ]
    assert len(facets.departments) == 8
    assert sum(department.count for department in facets.departments) == 120
    assert [d.name for d in facets.departments] == sorted(d.name for d in facets.departments)


async def test_someone_with_no_reports_has_no_team_count(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    async with open_session(app_engine, seeded_sandbox) as session:
        team = await reports_of(session, seeded_sandbox, "priya")
        facets = await directory_facets(session, filters=DirectoryFilters(), team_ids=team)

    assert team == frozenset()
    assert facets.my_team is None


async def test_options_at_zero_are_listed_sorted_by_name(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    # A search that only Marcus's store matches, so the other two locations count zero.
    filters = DirectoryFilters(
        q="Store Manager", location_id=persona(seeded_sandbox, "marcus").location_id
    )
    async with open_session(app_engine, seeded_sandbox) as session:
        facets = await directory_facets(session, filters=filters, team_ids=frozenset())

    assert facets.matching == 1
    assert [loc.name for loc in facets.locations] == [
        "Austin warehouse",
        "Denver HQ",
        "Oakland store",
    ]
    # The location menu swaps in each location: "Store Manager" exists at one store only.
    zeros = [loc.name for loc in facets.locations if loc.count == 0]
    assert zeros
    assert len(facets.departments) == 8
    assert [d.name for d in facets.departments] == sorted(d.name for d in facets.departments)
    assert any(d.count == 0 for d in facets.departments)


async def test_an_options_count_is_the_lists_length_with_that_option_chosen(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    marcus = persona(seeded_sandbox, "marcus")
    async with open_session(app_engine, seeded_sandbox) as session:
        team = await reports_of(session, seeded_sandbox, "marcus")
        combinations = [
            DirectoryFilters(),
            DirectoryFilters(q="a"),
            DirectoryFilters(location_id=marcus.location_id),
            DirectoryFilters(department_id=marcus.department_id),
            DirectoryFilters(team=team),
            DirectoryFilters(q="lead", location_id=marcus.location_id),
            DirectoryFilters(q="e", department_id=marcus.department_id, team=team),
            DirectoryFilters(
                q="a",
                location_id=marcus.location_id,
                department_id=marcus.department_id,
                team=team,
            ),
        ]
        for filters in combinations:
            facets = await directory_facets(session, filters=filters, team_ids=team)

            assert facets.total == 120
            assert facets.matching == len(await listed(session, filters)), filters
            for location in facets.locations:
                chosen = replace(filters, location_id=location.id)
                assert location.count == len(await listed(session, chosen)), (filters, location)
            for department in facets.departments:
                chosen = replace(filters, department_id=department.id)
                assert department.count == len(await listed(session, chosen)), (filters, department)
            # My team counts the list with the team filter on and the rest kept.
            assert facets.my_team == len(await listed(session, replace(filters, team=team))), (
                filters
            )
