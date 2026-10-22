"""The helper functions every row-level security policy calls."""

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.integration

READ_CONTEXT = text("SELECT app.current_tenant_id(), app.current_person_id(), app.current_is_hr()")
SET_CONTEXT = text(
    "SELECT set_config('app.tenant_id', :tenant_id, true),"
    " set_config('app.person_id', :person_id, true),"
    " set_config('app.is_hr', :is_hr, true)"
)


async def test_a_fresh_connection_has_no_tenant_person_or_hr(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as connection:
        row = (await connection.execute(READ_CONTEXT)).one()

    assert tuple(row) == (None, None, False)


async def test_empty_settings_read_as_none_instead_of_failing(app_engine: AsyncEngine) -> None:
    # After one transaction sets a value locally, the next transaction on that connection sees ''
    # rather than NULL, and ''::uuid would raise. The functions turn '' into NULL.
    async with app_engine.connect() as connection:
        await connection.execute(SET_CONTEXT, {"tenant_id": "", "person_id": "", "is_hr": ""})
        row = (await connection.execute(READ_CONTEXT)).one()

    assert tuple(row) == (None, None, False)


async def test_set_values_come_back_typed(app_engine: AsyncEngine) -> None:
    tenant_id, person_id = uuid4(), uuid4()
    async with app_engine.connect() as connection:
        await connection.execute(
            SET_CONTEXT, {"tenant_id": str(tenant_id), "person_id": str(person_id), "is_hr": "true"}
        )
        row = (await connection.execute(READ_CONTEXT)).one()

    assert tuple(row) == (tenant_id, person_id, True)


async def test_the_app_schema_holds_only_the_known_functions_none_leakproof_or_definer(
    app_engine: AsyncEngine,
) -> None:
    async with app_engine.connect() as connection:
        rows = await connection.execute(
            text(
                "SELECT proname, provolatile::text, proleakproof, prosecdef FROM pg_proc"
                " WHERE pronamespace = 'app'::regnamespace ORDER BY proname"
            )
        )
        functions = [tuple(row) for row in rows]

    assert functions == [
        ("current_is_hr", "s", False, False),
        ("current_person_id", "s", False, False),
        ("current_tenant_id", "s", False, False),
        # The trigger functions (migrations 0003, 0005, 0008, and 0009) are volatile.
        ("enforce_proposal_insert", "v", False, False),
        ("enforce_proposal_update", "v", False, False),
        ("enforce_time_off_request_update", "v", False, False),
        ("pin_tenant_handbook_version", "v", False, False),
        ("refuse_finished_turn_update", "v", False, False),
        ("stamp_tenant_created_at", "v", False, False),
    ]


async def test_public_cannot_execute_the_trigger_functions(app_engine: AsyncEngine) -> None:
    # A trigger function needs no EXECUTE for the role that fires it, so nothing is lost by
    # revoking the default grant to PUBLIC, and nobody can call one directly.
    async with app_engine.connect() as connection:
        rows = await connection.execute(
            text(
                "SELECT proname, EXISTS (SELECT 1 FROM aclexplode(coalesce(proacl,"
                " acldefault('f', proowner))) a WHERE a.grantee = 0"
                " AND a.privilege_type = 'EXECUTE') AS public_can_execute FROM pg_proc"
                " WHERE pronamespace = 'app'::regnamespace AND prorettype = 'trigger'::regtype"
                " ORDER BY proname"
            )
        )
        functions = [tuple(row) for row in rows]

    assert functions == [
        ("enforce_proposal_insert", False),
        ("enforce_proposal_update", False),
        ("enforce_time_off_request_update", False),
        ("pin_tenant_handbook_version", False),
        ("refuse_finished_turn_update", False),
        ("stamp_tenant_created_at", False),
    ]
