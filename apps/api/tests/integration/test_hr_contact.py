"""The HR team's contact details, read from the directory under row-level security."""

from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.ai.fixed_texts import HrContact, hr_contact
from app.db.models import Person
from app.db.tenancy import TenantContext, tenant_session
from app.modules.sandbox.seed import SeedCompany
from tests.integration.conftest import MakeTenant

pytestmark = pytest.mark.integration


async def test_the_hr_contact_is_dana_with_her_work_email(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    async with tenant_session(app_engine, TenantContext(seeded_sandbox.tenant_id, None)) as db:
        contacts = await hr_contact(db)

    assert [c.name for c in contacts] == ["Dana Whitfield"]
    assert contacts[0].work_email.startswith("dana.whitfield@")
    assert contacts[0].to_json() == {
        "name": "Dana Whitfield",
        "workEmail": contacts[0].work_email,
    }
    assert isinstance(contacts[0], HrContact)


async def test_contacts_are_ordered_by_name_and_stay_inside_the_tenant(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany, make_tenant: MakeTenant
) -> None:
    # Another sandbox, whose HR admin (Dana, dana@juniperrow.example) must not appear.
    await make_tenant()
    tenant = TenantContext(seeded_sandbox.tenant_id, None)
    async with tenant_session(app_engine, tenant) as db:
        dana = (await db.execute(select(Person).where(Person.persona_key == "dana"))).scalar_one()
        # Inserted after Dana, but sorts before her.
        db.add(
            Person(
                id=uuid4(),
                tenant_id=seeded_sandbox.tenant_id,
                given_name="Abel",
                family_name="Aardvark",
                title="HR Partner",
                department_id=dana.department_id,
                location_id=dana.location_id,
                manager_id=dana.id,
                work_email="abel.aardvark@juniperrow.example",
                employment_type="salaried",
                hire_date=date(2024, 3, 4),
                is_hr_admin=True,
            )
        )
    async with tenant_session(app_engine, tenant) as db:
        contacts = await hr_contact(db)

    assert [c.name for c in contacts] == ["Abel Aardvark", "Dana Whitfield"]
    assert all(c.work_email != "dana@juniperrow.example" for c in contacts)
