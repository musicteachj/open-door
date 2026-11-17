"""The API can add and read audit events, and never change or remove them."""

import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.models import AiProposal, AuditEvent
from app.db.tenancy import TenantContext, tenant_session
from app.modules.audit.service import record_event
from tests.integration.conftest import MakeTenant

pytestmark = pytest.mark.integration


async def test_the_api_can_read_the_event_it_added(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()

    async with tenant_session(app_engine, TenantContext(tenant.id, tenant.employee_id)) as session:
        actions = list((await session.execute(select(AuditEvent.action))).scalars())

    assert actions == ["sandbox.created"]


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE audit_events SET action = 'edited'",
        "DELETE FROM audit_events",
        "TRUNCATE audit_events",
    ],
)
async def test_the_api_cannot_change_or_remove_audit_events(
    app_engine: AsyncEngine, make_tenant: MakeTenant, statement: str
) -> None:
    tenant = await make_tenant()

    with pytest.raises(DBAPIError, match="permission denied for table audit_events"):
        async with tenant_session(app_engine, TenantContext(tenant.id, tenant.hr_id)) as session:
            await session.execute(text(statement))


async def test_an_event_stores_the_proposal_it_came_from(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    context = TenantContext(tenant.id, tenant.employee_id)
    async with tenant_session(app_engine, context) as session:
        proposal_id = (await session.execute(select(AiProposal.id))).scalar_one()
        await record_event(
            session,
            tenant_id=tenant.id,
            actor_id=tenant.employee_id,
            action="timeoff.requested",
            via="assistant",
            proposal_id=proposal_id,
        )

    async with tenant_session(app_engine, context) as session:
        stored = (
            await session.execute(
                select(AuditEvent.proposal_id).where(AuditEvent.action == "timeoff.requested")
            )
        ).scalar_one()
    assert stored == proposal_id


NULL_FLAGS = text(
    "SELECT before IS NULL, after IS NULL, before = 'null'::jsonb, after = 'null'::jsonb"
    " FROM audit_events WHERE id = :id"
)


async def test_an_event_with_no_before_or_after_stores_sql_null(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    async with tenant_session(app_engine, TenantContext(tenant.id, tenant.employee_id)) as session:
        await record_event(
            session, tenant_id=tenant.id, actor_id=tenant.employee_id, action="session.ended"
        )
        found = (
            await session.execute(
                text(
                    "SELECT before IS NULL, after IS NULL FROM audit_events"
                    " WHERE action = 'session.ended' AND tenant_id = :tenant"
                ),
                {"tenant": tenant.id},
            )
        ).one()

    assert tuple(found) == (True, True)


async def test_an_event_with_a_before_and_after_still_stores_them(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    async with tenant_session(app_engine, TenantContext(tenant.id, tenant.employee_id)) as session:
        await record_event(
            session,
            tenant_id=tenant.id,
            actor_id=tenant.employee_id,
            action="session.persona_switched",
            before={"personaKey": "priya"},
            after={"personaKey": "dana"},
        )
        event = (
            await session.execute(
                select(AuditEvent).where(AuditEvent.action == "session.persona_switched")
            )
        ).scalar_one()

    assert (event.before, event.after) == ({"personaKey": "priya"}, {"personaKey": "dana"})


def migration_0017() -> object:
    path = Path(__file__).parents[2] / "migrations/versions/0017_sessions_and_audit.py"
    spec = importlib.util.spec_from_file_location("migration_0017", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def test_the_migration_turns_json_null_into_sql_null(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    legacy_id, bystander_id = uuid4(), uuid4()
    insert = text(
        "INSERT INTO audit_events (id, tenant_id, via, action, before, after)"
        " VALUES (:id, :tenant, 'system', 'session.ended', {before}, {after})"
    )
    # A committed row with SQL NULLs: the migration's statements have no row filter, so the test
    # runs them in a transaction it rolls back, and this row proves nothing leaked out of it.
    async with owner_engine.begin() as connection:
        await connection.execute(
            text(insert.text.format(before="NULL", after="NULL")),
            {"id": bystander_id, "tenant": tenant.id},
        )
    async with owner_engine.connect() as connection:
        transaction = await connection.begin()
        # A row as the old model wrote it: the JSON value null, which IS NULL does not find.
        await connection.execute(
            text(insert.text.format(before="'null'::jsonb", after="'null'::jsonb")),
            {"id": legacy_id, "tenant": tenant.id},
        )
        before = (await connection.execute(NULL_FLAGS, {"id": legacy_id})).one()
        migration = migration_0017()
        for statement in migration.AUDIT_NULLS_UP:  # type: ignore[attr-defined]
            await connection.execute(text(statement))
        after = (await connection.execute(NULL_FLAGS, {"id": legacy_id})).one()
        for statement in migration.AUDIT_NULLS_DOWN:  # type: ignore[attr-defined]
            await connection.execute(text(statement))
        reverted = (await connection.execute(NULL_FLAGS, {"id": legacy_id})).one()
        await transaction.rollback()

    async with owner_engine.connect() as connection:
        untouched = (await connection.execute(NULL_FLAGS, {"id": bystander_id})).one()
        legacy_rows = await connection.scalar(
            text("SELECT count(*) FROM audit_events WHERE id = :id"), {"id": legacy_id}
        )
    assert tuple(untouched) == (True, True, None, None)  # Still SQL NULL: not rewritten.
    assert legacy_rows == 0  # The test's own row was rolled back too.
    assert tuple(before) == (False, False, True, True)
    assert tuple(after) == (True, True, None, None)
    assert tuple(reverted) == (False, False, True, True)
