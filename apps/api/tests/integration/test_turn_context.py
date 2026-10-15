"""The per-turn context built from the seed personas through `get_me`."""

from datetime import UTC, datetime, timedelta
from uuid import uuid5

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.ai.context import actor_view, turn_context
from app.db.tenancy import TenantContext, tenant_session
from app.modules.identity.actor import load_actor
from app.modules.people.queries import get_me
from app.modules.sandbox.seed import SeedCompany

pytestmark = pytest.mark.integration

NOW = datetime(2026, 10, 15, 3, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("persona", "role", "location_code"),
    [("priya", "employee", "oak"), ("marcus", "manager", "oak"), ("dana", "hr", "den")],
)
async def test_the_view_and_context_come_from_the_personas_own_record(
    app_engine: AsyncEngine,
    seeded_sandbox: SeedCompany,
    persona: str,
    role: str,
    location_code: str,
) -> None:
    tenant_id = seeded_sandbox.tenant_id
    async with tenant_session(app_engine, TenantContext(tenant_id, None)) as session:
        actor = await load_actor(session, tenant_id, uuid5(tenant_id, f"person:{persona}"))
        assert actor is not None
        me = await get_me(session, actor, NOW + timedelta(hours=24))

    view = actor_view(me)
    assert (view.role, view.location_code) == (role, location_code)
    text = turn_context(view, now=NOW, handbook_label="v1", operator_notes=())
    assert view.given_name in text
    assert "2026-10-14" in text
    assert str(seeded_sandbox.anchor_date) not in text
