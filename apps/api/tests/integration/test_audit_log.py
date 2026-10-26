"""The API can add and read audit events, and never change or remove them."""

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
