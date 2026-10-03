"""The API can add and read audit events, and never change or remove them."""

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.models import AuditEvent
from app.db.tenancy import TenantContext, tenant_session
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
