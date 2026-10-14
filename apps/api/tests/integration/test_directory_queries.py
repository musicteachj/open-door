"""The directory query's search and filters, against a seeded sandbox of 145 people."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models import Person
from app.db.tenancy import TenantContext, tenant_session
from app.modules.people.queries import DirectoryFilters, list_directory
from app.modules.sandbox.seed import PersonRow, SeedCompany

pytestmark = pytest.mark.integration


@asynccontextmanager
async def open_session(engine: AsyncEngine, company: SeedCompany) -> AsyncIterator[AsyncSession]:
    async with tenant_session(engine, TenantContext(company.tenant_id, None)) as session:
        yield session


async def listed(
    session: AsyncSession, filters: DirectoryFilters | None = None, *, limit: int = 100
) -> list[UUID]:
    """Everyone the filters match, in directory order, read page by page."""
    ids: list[UUID] = []
    after = None
    while True:
        page = await list_directory(
            session, limit=limit, after=after, filters=filters or DirectoryFilters()
        )
        ids.extend(card.id for card in page.cards)
        if page.next_cursor is None:
            return ids
        after = page.next_cursor


def in_order(people: list[PersonRow]) -> list[UUID]:
    return [p.id for p in sorted(people, key=lambda p: (p.family_name, p.given_name, p.id))]


def someone(company: SeedCompany) -> PersonRow:
    return next(p for p in company.people if p.persona_key == "marcus")


async def test_no_filters_lists_everyone_in_order(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    async with open_session(app_engine, seeded_sandbox) as session:
        assert await listed(session) == in_order(list(seeded_sandbox.people))


async def test_a_search_matches_part_of_a_full_name(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    marcus = someone(seeded_sandbox)
    # The end of the given name, a space, and the start of the family name: only the joined
    # "given family" text holds that.
    q = f"{marcus.given_name[-2:]} {marcus.family_name[:2]}"
    expected = [
        p
        for p in seeded_sandbox.people
        if q.lower() in f"{p.given_name} {p.family_name}".lower()
        or q.lower() in p.title.lower()
        or q.lower() in p.work_email.lower()
    ]
    assert marcus in expected

    async with open_session(app_engine, seeded_sandbox) as session:
        assert await listed(session, DirectoryFilters(q=q)) == in_order(expected)


async def test_a_search_matches_a_title(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    expected = [p for p in seeded_sandbox.people if "store manager" in p.title.lower()]
    assert expected

    async with open_session(app_engine, seeded_sandbox) as session:
        found = await listed(session, DirectoryFilters(q="Store Manager"))

    assert found == in_order(expected)


async def test_a_search_matches_a_work_email(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    marcus = someone(seeded_sandbox)

    async with open_session(app_engine, seeded_sandbox) as session:
        found = await listed(session, DirectoryFilters(q=marcus.work_email))

    assert found == [marcus.id]


async def test_a_search_ignores_case(app_engine: AsyncEngine, seeded_sandbox: SeedCompany) -> None:
    async with open_session(app_engine, seeded_sandbox) as session:
        lower = await listed(session, DirectoryFilters(q="store manager"))
        upper = await listed(session, DirectoryFilters(q="STORE MANAGER"))
        name = await listed(session, DirectoryFilters(q="mArCuS bElL"))

    assert lower
    assert lower == upper
    assert name == [someone(seeded_sandbox).id]


async def test_wildcard_characters_in_a_search_match_only_themselves(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    by_email = sorted(seeded_sandbox.people, key=lambda p: p.work_email)
    percent, underscore, backslash = by_email[:3]
    # The API's login can't change a title, and nothing seeded holds these characters, so the
    # owner (a superuser, which bypasses row-level security) plants them.
    async with owner_engine.begin() as connection:
        for person, title in (
            (percent, "50% off"),
            (underscore, "Sales_Lead"),
            (backslash, r"Back\slash"),
        ):
            await connection.execute(
                update(Person).where(Person.id == person.id).values(title=title)
            )

    async with open_session(app_engine, seeded_sandbox) as session:

        async def found(q: str) -> list[UUID]:
            return await listed(session, DirectoryFilters(q=q))

        # As patterns, each of these would match many people.
        assert await found("%") == [percent.id]
        assert await found("_") == [underscore.id]
        assert await found("\\") == [backslash.id]
        assert await found("50%") == [percent.id]
        assert await found("%off") == []
        assert await found("Sales_L") == [underscore.id]
        assert await found("Sales.Lead") == []
        assert await found("S_les") == []
        assert await found(r"Back\s") == [backslash.id]
        assert await found(r"Back\\s") == []


async def test_each_filter_alone_and_combined(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    people = seeded_sandbox.people
    location_id = people[0].location_id
    department_id = people[0].department_id
    team = frozenset(p.id for p in people if p.manager_id == someone(seeded_sandbox).id)

    def expect(
        *,
        q: str | None = None,
        location: bool = False,
        department: bool = False,
        mine: bool = False,
    ) -> list[UUID]:
        return in_order(
            [
                p
                for p in people
                if (q is None or q.lower() in p.title.lower())
                and (not location or p.location_id == location_id)
                and (not department or p.department_id == department_id)
                and (not mine or p.id in team)
            ]
        )

    cases = [
        (DirectoryFilters(location_id=location_id), expect(location=True)),
        (DirectoryFilters(department_id=department_id), expect(department=True)),
        (DirectoryFilters(team=team), expect(mine=True)),
        (
            DirectoryFilters(location_id=location_id, department_id=department_id),
            expect(location=True, department=True),
        ),
        (
            DirectoryFilters(q="associate", location_id=location_id, team=team),
            expect(q="associate", location=True, mine=True),
        ),
        (
            DirectoryFilters(
                q="lead", location_id=location_id, department_id=department_id, team=team
            ),
            expect(q="lead", location=True, department=True, mine=True),
        ),
    ]
    async with open_session(app_engine, seeded_sandbox) as session:
        for filters, expected in cases:
            assert await listed(session, filters) == expected, filters
    assert all(expected for _, expected in cases[:3])
    assert len(cases[2][1]) == len(team)


async def test_an_empty_team_matches_no_one(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    async with open_session(app_engine, seeded_sandbox) as session:
        assert await listed(session, DirectoryFilters(team=frozenset())) == []


async def test_filtered_paging_neither_repeats_nor_skips(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    filters = DirectoryFilters(q="e", location_id=seeded_sandbox.people[0].location_id)
    async with open_session(app_engine, seeded_sandbox) as session:
        whole = await listed(session, filters, limit=100)
        for limit in (1, 3, 7):
            assert await listed(session, filters, limit=limit) == whole

    assert 10 < len(whole) < 145
