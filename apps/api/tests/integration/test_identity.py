"""Sessions, the actor, and the audit log, as the API's login sees them."""

import asyncio
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4, uuid5

import pytest
from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.request_id import request_id_var
from app.db.models import AuditEvent, Person, Tenant, UserSession
from app.db.tenancy import NO_TENANT, TenantContext, tenant_session
from app.modules.audit.service import record_event
from app.modules.identity.actor import load_actor
from app.modules.identity.sessions import (
    PersonNotInTenantError,
    SessionGoneError,
    end_session,
    find_session,
    rotate_session,
    start_session,
)
from app.modules.identity.tokens import SessionTokens
from app.modules.sandbox.seed import build_company, insert_company
from tests.integration.conftest import TEST_KEYS, MakeTenant, sha256_of_random_token

pytestmark = pytest.mark.integration


async def seeded_tenant(engine: AsyncEngine, created_tenant_ids: list[UUID]) -> UUID:
    """A tenant filled with the seed company. It is deleted when the test session ends."""
    tenant_id = uuid4()
    created_tenant_ids.append(tenant_id)
    now = datetime.now(UTC)
    company = build_company(tenant_id, now.date())
    async with tenant_session(engine, TenantContext(tenant_id, None)) as session:
        tenant = {"id": tenant_id, "expires_at": now + timedelta(hours=24)}
        await session.execute(insert(Tenant).values(**tenant, anchor_date=company.anchor_date))
        await insert_company(session, company, TEST_KEYS)
    return tenant_id


def person_id(tenant_id: UUID, key: str) -> UUID:
    """A seeded person's ID: the same key in every sandbox, under that sandbox's tenant ID."""
    return uuid5(tenant_id, f"person:{key}")


async def session_count(engine: AsyncEngine, person_id: UUID) -> int:
    """A person's session count. `sessions` has no row-level security, so any context sees it."""
    async with tenant_session(engine, NO_TENANT) as session:
        count = await session.scalar(
            select(func.count()).select_from(UserSession).where(UserSession.person_id == person_id)
        )
    assert count is not None
    return count


async def test_a_session_is_found_by_its_token_hash_until_it_expires(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    live, expired = await make_tenant(), await make_tenant(expired=True)
    async with tenant_session(app_engine, TenantContext(live.id, None)) as session:
        tokens = await start_session(session, live.id, live.employee_id)
    async with tenant_session(app_engine, TenantContext(expired.id, None)) as session:
        old_tokens = await start_session(session, expired.id, expired.employee_id)

    async with tenant_session(app_engine, NO_TENANT) as session:
        found = await find_session(session, tokens.session_hash)
        by_csrf_hash = await find_session(session, tokens.csrf_hash)
        too_late = await find_session(session, old_tokens.session_hash)

    assert found is not None
    assert (found.tenant_id, found.person_id, found.csrf_hash) == (
        live.id,
        live.employee_id,
        tokens.csrf_hash,
    )
    assert (by_csrf_hash, too_late) == (None, None)


async def test_rotating_a_session_replaces_both_tokens_and_keeps_the_expiry(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    async with tenant_session(app_engine, TenantContext(tenant.id, None)) as session:
        tokens = await start_session(session, tenant.id, tenant.employee_id)
        current = await find_session(session, tokens.session_hash)
        assert current is not None
        rotated = await rotate_session(session, current, tenant.hr_id)
        tenant_expires_at = await session.scalar(
            select(Tenant.expires_at).where(Tenant.id == tenant.id)
        )

    async with tenant_session(app_engine, NO_TENANT) as session:
        old = await find_session(session, tokens.session_hash)
        new = await find_session(session, rotated.session_hash)
    assert old is None
    assert new is not None
    assert (new.person_id, new.expires_at, new.csrf_hash) == (
        tenant.hr_id,
        current.expires_at,
        rotated.csrf_hash,
    )
    assert new.expires_at == tenant_expires_at
    assert rotated.csrf_hash != tokens.csrf_hash


async def test_ending_a_session_says_whether_it_was_there(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    live, expired = await make_tenant(), await make_tenant(expired=True)
    async with tenant_session(app_engine, TenantContext(live.id, None)) as session:
        tokens = await start_session(session, live.id, live.employee_id)
    async with tenant_session(app_engine, TenantContext(expired.id, None)) as session:
        old_tokens = await start_session(session, expired.id, expired.employee_id)

    async with tenant_session(app_engine, NO_TENANT) as session:
        first = await end_session(session, tokens.session_hash)
    async with tenant_session(app_engine, NO_TENANT) as session:
        again = await end_session(session, tokens.session_hash)
        never_existed = await end_session(session, sha256_of_random_token())
        already_expired = await end_session(session, old_tokens.session_hash)

    assert (first, again, never_existed, already_expired) == (True, False, False, False)


async def test_rotating_a_session_that_is_already_gone_raises_and_starts_nothing(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    async with tenant_session(app_engine, TenantContext(tenant.id, None)) as session:
        tokens = await start_session(session, tenant.id, tenant.employee_id)
        current = await find_session(session, tokens.session_hash)
    assert current is not None
    # Another request ends the same session, and its transaction commits.
    async with tenant_session(app_engine, NO_TENANT) as session:
        await end_session(session, tokens.session_hash)
        assert await find_session(session, tokens.session_hash) is None

    # The raise is caught inside the transaction, which then commits: a session the failed
    # rotation had inserted would stay.
    async with tenant_session(app_engine, TenantContext(tenant.id, None)) as session:
        with pytest.raises(SessionGoneError):
            await rotate_session(session, current, tenant.hr_id)

    assert await session_count(app_engine, tenant.hr_id) == 0


async def test_two_requests_rotating_the_same_session_cannot_both_win(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    async with tenant_session(app_engine, TenantContext(tenant.id, None)) as session:
        tokens = await start_session(session, tenant.id, tenant.employee_id)
        current = await find_session(session, tokens.session_hash)
    assert current is not None

    async def rotate(person_id: UUID) -> SessionTokens:
        async with tenant_session(app_engine, TenantContext(tenant.id, None)) as session:
            return await rotate_session(session, current, person_id)

    results = await asyncio.gather(
        rotate(tenant.hr_id), rotate(tenant.colleague_id), return_exceptions=True
    )

    assert sorted(type(result).__name__ for result in results) == [
        "SessionGoneError",
        "SessionTokens",
    ]
    started = await session_count(app_engine, tenant.hr_id) + await session_count(
        app_engine, tenant.colleague_id
    )
    assert started == 1


@pytest.mark.parametrize(
    "case",
    ["their person, my tenant ID", "their person and tenant ID", "my person, their tenant ID"],
)
async def test_a_session_cannot_be_started_for_the_wrong_person_or_tenant(
    app_engine: AsyncEngine, make_tenant: MakeTenant, case: str
) -> None:
    mine, theirs = await make_tenant(), await make_tenant()
    person_id = mine.employee_id if case == "my person, their tenant ID" else theirs.employee_id
    tenant_id = mine.id if case == "their person, my tenant ID" else theirs.id

    # The raise is caught inside the transaction, which then commits: a session that had been
    # inserted would stay.
    async with tenant_session(app_engine, TenantContext(mine.id, None)) as session:
        with pytest.raises(PersonNotInTenantError):
            await start_session(session, tenant_id, person_id)

    # Each person keeps only the one session that make_tenant gave them.
    assert await session_count(app_engine, mine.employee_id) == 1
    assert await session_count(app_engine, theirs.employee_id) == 1


async def test_a_session_cannot_be_started_for_nobody(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()

    async with tenant_session(app_engine, TenantContext(tenant.id, None)) as session:
        with pytest.raises(PersonNotInTenantError):
            await start_session(session, tenant.id, uuid4())


async def test_a_new_session_expires_when_its_tenant_does(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    async with tenant_session(app_engine, TenantContext(tenant.id, None)) as session:
        tokens = await start_session(session, tenant.id, tenant.employee_id)
        tenant_expires_at = await session.scalar(
            select(Tenant.expires_at).where(Tenant.id == tenant.id)
        )

    async with tenant_session(app_engine, NO_TENANT) as session:
        found = await find_session(session, tokens.session_hash)
    assert found is not None
    assert found.expires_at == tenant_expires_at


@pytest.mark.parametrize(
    ("key", "is_hr_admin", "report_count"),
    [
        ("priya", False, 0),
        ("leo", False, 0),
        ("mateo", False, 0),
        ("dana", True, 0),
        ("oak-front-end", False, 14),
        # Five directly, and the leads' 39 associates through them.
        ("marcus", False, 44),
    ],
)
async def test_the_actor_has_every_report_direct_and_indirect(
    app_engine: AsyncEngine,
    created_tenant_ids: list[UUID],
    key: str,
    is_hr_admin: bool,
    report_count: int,
) -> None:
    tenant_id = await seeded_tenant(app_engine, created_tenant_ids)
    async with tenant_session(app_engine, TenantContext(tenant_id, None)) as session:
        actor = await load_actor(session, tenant_id, person_id(tenant_id, key))

    assert actor is not None
    assert (actor.is_hr_admin, len(actor.report_ids)) == (is_hr_admin, report_count)
    assert actor.is_manager is (report_count > 0)
    assert actor.direct_report_ids <= actor.report_ids
    # Only a manager has direct reports, and the five leads' associates are never direct ones.
    assert (len(actor.direct_report_ids) > 0) is (report_count > 0)


@pytest.mark.parametrize(
    ("key", "direct_keys"),
    [
        ("marcus", {"priya", "leo", "oak-apparel-lead", "oak-home-lead", "oak-front-end"}),
        ("priya", set()),
        ("dana", set()),
    ],
)
async def test_the_actor_has_its_direct_reports(
    app_engine: AsyncEngine,
    created_tenant_ids: list[UUID],
    key: str,
    direct_keys: set[str],
) -> None:
    tenant_id = await seeded_tenant(app_engine, created_tenant_ids)
    async with tenant_session(app_engine, TenantContext(tenant_id, None)) as session:
        actor = await load_actor(session, tenant_id, person_id(tenant_id, key))

    assert actor is not None
    assert actor.direct_report_ids == {person_id(tenant_id, direct) for direct in direct_keys}
    if key == "marcus":
        # Five directly and 44 in all: a lead's associates are reports but not direct ones.
        assert (len(actor.direct_report_ids), len(actor.report_ids)) == (5, 44)


async def test_marcus_manages_the_leads_and_their_teams(
    app_engine: AsyncEngine, created_tenant_ids: list[UUID]
) -> None:
    tenant_id = await seeded_tenant(app_engine, created_tenant_ids)
    async with tenant_session(app_engine, TenantContext(tenant_id, None)) as session:
        marcus = await load_actor(session, tenant_id, person_id(tenant_id, "marcus"))
        lead = await load_actor(session, tenant_id, person_id(tenant_id, "oak-front-end"))

    assert marcus is not None
    assert lead is not None
    direct = {"priya", "leo", "oak-apparel-lead", "oak-home-lead", "oak-front-end"}
    assert {person_id(tenant_id, key) for key in direct} <= marcus.report_ids
    assert lead.report_ids < marcus.report_ids


async def test_another_tenants_person_is_no_actor(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    mine, theirs = await make_tenant(), await make_tenant()

    async with tenant_session(app_engine, TenantContext(mine.id, None)) as session:
        actor = await load_actor(session, mine.id, theirs.hr_id)

    assert actor is None


async def test_the_actor_never_carries_a_tenant_other_than_its_persons(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    mine, theirs = await make_tenant(), await make_tenant()

    async with tenant_session(app_engine, TenantContext(mine.id, None)) as session:
        right = await load_actor(session, mine.id, mine.employee_id)
        wrong_tenant_id = await load_actor(session, theirs.id, mine.employee_id)
        their_person_and_tenant = await load_actor(session, theirs.id, theirs.employee_id)

    assert right is not None
    assert right.tenant_id == mine.id
    assert (wrong_tenant_id, their_person_and_tenant) == (None, None)


async def test_a_person_who_manages_themself_is_not_their_own_report(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    loner = uuid4()
    async with tenant_session(app_engine, TenantContext(tenant.id, None)) as session:
        template = (
            await session.execute(
                select(Person.department_id, Person.location_id).where(
                    Person.id == tenant.employee_id
                )
            )
        ).one()
        # The login may insert this: no CHECK stops a row from naming itself as its manager.
        await session.execute(
            insert(Person).values(
                id=loner,
                tenant_id=tenant.id,
                given_name="Sam",
                family_name="Loop",
                title="Associate",
                department_id=template.department_id,
                location_id=template.location_id,
                manager_id=loner,
                work_email="sam@juniperrow.example",
                employment_type="salaried",
                hire_date=date(2024, 3, 4),
            )
        )
        actor = await load_actor(session, tenant.id, loner)

    assert actor is not None
    assert loner not in actor.report_ids
    assert loner not in actor.direct_report_ids
    assert actor.is_manager is False


async def test_a_manager_in_a_reporting_loop_is_not_their_own_report(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    # The API's login can't update people, so the owner closes the loop: Dana manages Priya and
    # Leo, and now Priya manages Dana.
    async with owner_engine.begin() as connection:
        await connection.execute(
            update(Person).where(Person.id == tenant.hr_id).values(manager_id=tenant.employee_id)
        )

    async with tenant_session(app_engine, TenantContext(tenant.id, None)) as session:
        actor = await load_actor(session, tenant.id, tenant.hr_id)

    assert actor is not None
    assert actor.report_ids == {tenant.employee_id, tenant.colleague_id}
    assert actor.direct_report_ids == {tenant.employee_id, tenant.colleague_id}
    assert actor.is_manager is True


async def test_an_audit_event_carries_the_request_id(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    token = request_id_var.set("trace-42")
    try:
        async with tenant_session(app_engine, TenantContext(tenant.id, tenant.hr_id)) as session:
            await record_event(
                session,
                tenant_id=tenant.id,
                actor_id=tenant.hr_id,
                action="person_private.read",
                target_type="person",
                target_id=tenant.colleague_id,
                after={"fields": ["phone"]},
            )
    finally:
        request_id_var.reset(token)

    async with tenant_session(app_engine, TenantContext(tenant.id, None)) as session:
        query = select(AuditEvent).where(AuditEvent.request_id == "trace-42")
        [event] = (await session.execute(query)).scalars()
    assert (event.action, event.via, event.actor_person_id, event.target_id, event.after) == (
        "person_private.read",
        "ui",
        tenant.hr_id,
        tenant.colleague_id,
        {"fields": ["phone"]},
    )


@pytest.mark.parametrize("field", ["phone", "home_address", "homeAddress", "dateOfBirth"])
async def test_an_audit_event_refuses_a_private_field(
    app_engine: AsyncEngine, make_tenant: MakeTenant, field: str
) -> None:
    tenant = await make_tenant()

    with pytest.raises(ValueError, match="directory fields only"):
        async with tenant_session(app_engine, TenantContext(tenant.id, tenant.hr_id)) as session:
            await record_event(
                session,
                tenant_id=tenant.id,
                actor_id=tenant.hr_id,
                action="person_private.read",
                after={field: "555-0100"},
            )


async def test_an_audit_event_for_another_tenant_is_refused(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    mine, theirs = await make_tenant(), await make_tenant()

    with pytest.raises(ProgrammingError, match="row-level security"):
        async with tenant_session(app_engine, TenantContext(mine.id, mine.hr_id)) as session:
            await record_event(
                session, tenant_id=theirs.id, actor_id=theirs.hr_id, action="session.ended"
            )

    async with tenant_session(app_engine, TenantContext(theirs.id, None)) as session:
        count = await session.scalar(
            select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "session.ended")
        )
    assert count == 0


async def test_an_audit_event_by_another_tenants_actor_is_refused(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    mine, theirs = await make_tenant(), await make_tenant()

    with pytest.raises(IntegrityError, match="foreign key"):
        async with tenant_session(app_engine, TenantContext(mine.id, mine.hr_id)) as session:
            await record_event(
                session, tenant_id=mine.id, actor_id=theirs.hr_id, action="session.ended"
            )

    async with tenant_session(app_engine, TenantContext(mine.id, None)) as session:
        count = await session.scalar(
            select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "session.ended")
        )
    assert count == 0
