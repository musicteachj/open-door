"""The handbook's asker, loaded for the seed personas."""

from uuid import uuid5

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.tenancy import TenantContext, tenant_session
from app.domain.handbook.applicability import Asker
from app.modules.handbook.asker import load_asker
from app.modules.identity.actor import load_actor
from app.modules.sandbox.seed import SeedCompany

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    ("persona", "expected"),
    [
        ("dana", Asker("CO", "salaried", "den")),
        ("marcus", Asker("CA", "salaried", "oak")),
        ("mateo", Asker("TX", "hourly", "aus")),
    ],
)
async def test_the_asker_comes_from_the_actors_location_and_employment_type(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany, persona: str, expected: Asker
) -> None:
    tenant_id = seeded_sandbox.tenant_id
    async with tenant_session(app_engine, TenantContext(tenant_id, None)) as session:
        actor = await load_actor(session, tenant_id, uuid5(tenant_id, f"person:{persona}"))
        assert actor is not None

        assert await load_asker(session, actor) == expected
