"""The four seeded cases, written into a sandbox by `insert_company` and read back the way HR does.

The seed writes them as people who are not the visitor, with times in the past, so it clears
`app.person_id` around those inserts and puts it back (migration 0013 lets an insert through only
when no person is set). Their words and summaries are plaintext in `build_company` and ciphertext
in the database.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.problems import ProblemError
from app.db.models import Case, CaseEvent, CaseSummary, Tenant
from app.db.tenancy import TenantContext, set_is_hr, tenant_session
from app.modules.cases import queries, service
from app.modules.identity.actor import load_actor
from app.modules.sandbox.seed import SeedCompany, build_company, insert_company
from app.modules.sandbox.seed_data import SEEDED_SUMMARY_PLACEHOLDER
from app.policy import Actor
from tests.integration.conftest import TEST_KEYS

pytestmark = pytest.mark.integration

ANCHOR = date(2026, 10, 5)
NAMES = ("Keisha", "Chloe", "Aaliyah", "Lucia")


def persona(company: SeedCompany, key: str) -> UUID:
    return next(p.id for p in company.people if p.persona_key == key)


def person(company: SeedCompany, given_name: str) -> UUID:
    return next(p.id for p in company.people if p.given_name == given_name)


async def seed_as(
    engine: AsyncEngine, created_tenant_ids: list[UUID], who: str, anchor: date = ANCHOR
) -> tuple[SeedCompany, str | None]:
    """Create a sandbox as the `who` persona, the way sandbox creation does. Returns the company
    and what `app.current_person_id()` reads afterward in the same transaction."""
    tenant_id = uuid4()
    created_tenant_ids.append(tenant_id)
    company = build_company(tenant_id, anchor)
    async with tenant_session(engine, TenantContext(tenant_id, persona(company, who))) as session:
        session.add(
            Tenant(
                id=tenant_id,
                expires_at=datetime.now(UTC) + timedelta(hours=24),
                anchor_date=anchor,
            )
        )
        await session.flush()
        await insert_company(session, company, TEST_KEYS)
        after: str | None = (
            await session.execute(text("SELECT app.current_person_id()::text"))
        ).scalar_one()
    return company, after


@asynccontextmanager
async def acting(
    engine: AsyncEngine, company: SeedCompany, who: UUID
) -> AsyncIterator[tuple[AsyncSession, Actor]]:
    async with tenant_session(engine, TenantContext(company.tenant_id, who)) as db:
        actor = await load_actor(db, company.tenant_id, who)
        assert actor is not None
        await set_is_hr(db, actor.is_hr_admin)
        yield db, actor


@pytest.fixture
async def sandbox(
    app_engine: AsyncEngine, created_tenant_ids: list[UUID]
) -> tuple[SeedCompany, str | None]:
    return await seed_as(app_engine, created_tenant_ids, "priya")


@pytest.mark.parametrize("who", ["priya", "dana"])
async def test_seeding_as_an_employee_or_as_hr_works_and_puts_the_person_back(
    app_engine: AsyncEngine, created_tenant_ids: list[UUID], who: str
) -> None:
    company, after = await seed_as(app_engine, created_tenant_ids, who)

    assert after == str(persona(company, who))
    async with acting(app_engine, company, persona(company, "dana")) as (db, _):
        rows = (await db.execute(select(Case.created_at, Case.status_changed_at))).all()
    # The backdated times were kept, not stamped with now().
    assert len(rows) == 4
    assert all(created < datetime.now(UTC) - timedelta(days=1) for created, _ in rows)
    assert sorted(created for created, _ in rows) == sorted(c.created_at for c in company.cases)
    assert sorted(changed for _, changed in rows) == sorted(
        c.status_changed_at for c in company.cases
    )


async def test_the_words_and_summaries_are_sealed_and_open_through_the_service(
    app_engine: AsyncEngine, sandbox: tuple[SeedCompany, str | None]
) -> None:
    company, _ = sandbox
    dana = persona(company, "dana")

    async with acting(app_engine, company, dana) as (db, _):
        stored = (await db.execute(select(Case.id, Case.text_ciphertext))).all()
        summaries = (await db.execute(select(CaseSummary.ciphertext))).scalars().all()
    for case in company.cases:
        blob = dict(stored)[case.id]
        assert case.text.encode() not in blob
        assert case.text[:20].encode() not in blob
    assert len(summaries) == 4
    assert all(SEEDED_SUMMARY_PLACEHOLDER.encode()[:20] not in blob for blob in summaries if blob)
    for case in company.cases:
        async with acting(app_engine, company, dana) as (db, actor):
            summary = await service.case_summary_for(db, TEST_KEYS, actor, case.id)
            words = await service.case_text_for(db, TEST_KEYS, actor, case.id)
        assert words == case.text
        assert (summary.status, summary.text) == ("written", SEEDED_SUMMARY_PLACEHOLDER)


async def test_the_events_and_summaries_are_stored_as_built(
    app_engine: AsyncEngine, sandbox: tuple[SeedCompany, str | None]
) -> None:
    company, _ = sandbox

    async with acting(app_engine, company, persona(company, "dana")) as (db, _):
        events = {
            (e.case_id, e.kind, e.actor_person_id, e.occurred_at, e.from_status, e.to_status)
            for e in (await db.execute(select(CaseEvent))).scalars()
        }
        written_by_hr = (await db.execute(select(CaseSummary.written_by_hr))).scalars().all()

    assert events == {
        (case.id, e.kind, e.actor_person_id, e.occurred_at, e.from_status, e.to_status)
        for case in company.cases
        for e in case.events
    }
    assert written_by_hr == [False] * 4


async def test_dana_sees_the_four_in_the_specs_order_with_the_counts(
    app_engine: AsyncEngine, sandbox: tuple[SeedCompany, str | None]
) -> None:
    company, _ = sandbox

    async with acting(app_engine, company, persona(company, "dana")) as (db, actor):
        page = await service.queue(db, actor, None, None)
        # On the anchor date, a Monday and a business day: Chloe's reply is due that day.
        new, due = await queries.counts(db, company.tenant_id, actor.person_id, ANCHOR)

    # New cases first, by reply-by; then the rest, oldest first (Lucia's was sent first).
    assert [(item.given_name, item.status) for item in page.items] == [
        ("Chloe", "new"),
        ("Keisha", "new"),
        ("Lucia", "closed"),
        ("Aaliyah", "in_review"),
    ]
    assert page.next_cursor is None
    assert (new, due) == (2, 1)


async def test_status_changes_follow_whether_dana_has_read_the_words(
    app_engine: AsyncEngine, sandbox: tuple[SeedCompany, str | None]
) -> None:
    company, _ = sandbox
    dana = persona(company, "dana")
    aaliyah = next(c for c in company.cases if c.person_id == person(company, "Aaliyah"))
    keisha = next(c for c in company.cases if c.person_id == person(company, "Keisha"))

    # Dana already read Aaliyah's words in the seed, so she can close it without a new read.
    async with acting(app_engine, company, dana) as (db, actor):
        closed = await service.change_status(db, actor, aaliyah.id, "closed")
    assert closed.status == "closed"
    async with acting(app_engine, company, dana) as (db, actor):
        with pytest.raises(ProblemError) as refused:
            await service.change_status(db, actor, keisha.id, "in_review")
    assert refused.value.code == "words-not-read"


async def test_no_one_but_hr_sees_a_seeded_case(
    app_engine: AsyncEngine, sandbox: tuple[SeedCompany, str | None]
) -> None:
    company, _ = sandbox
    # Priya (the visitor), Marcus (a manager), and Keisha herself see only their own: nothing for
    # the first two; Keisha sees her own case.
    for who, expected in (
        (persona(company, "priya"), 0),
        (persona(company, "marcus"), 0),
        (person(company, "Keisha"), 1),
    ):
        async with acting(app_engine, company, who) as (db, _):
            count = (await db.execute(select(func.count()).select_from(Case))).scalar_one()
            event_count = (
                await db.execute(select(func.count()).select_from(CaseEvent))
            ).scalar_one()
        assert (count, event_count) == (expected, 0)


async def test_a_failed_case_insert_raises_its_own_error(
    app_engine: AsyncEngine, created_tenant_ids: list[UUID]
) -> None:
    tenant_id = uuid4()
    created_tenant_ids.append(tenant_id)
    company = build_company(tenant_id, ANCHOR)
    first = company.cases[0]
    # Two events with one ID: the database refuses the second, aborting the transaction.
    twin = replace(first.events[1], id=first.events[0].id)
    broken = replace(
        company,
        cases=(replace(first, events=(*first.events, twin)), *company.cases[1:]),
    )

    async def seed_broken() -> None:
        async with tenant_session(
            app_engine, TenantContext(tenant_id, persona(company, "priya"))
        ) as session:
            session.add(
                Tenant(
                    id=tenant_id,
                    expires_at=datetime.now(UTC) + timedelta(hours=24),
                    anchor_date=ANCHOR,
                )
            )
            await session.flush()
            await insert_company(session, broken, TEST_KEYS)

    with pytest.raises(IntegrityError):
        await seed_broken()
