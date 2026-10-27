"""Migration 0012 deletes every sandbox first, in both directions.

Row-level security is forced, and under FORCE even a non-superuser owner's DELETE sees no rows, so
the migration brackets the delete with NO FORCE and FORCE (the development and CI owner is a
superuser, which skips row-level security, so this test can't show the difference; it proves the
statements delete every tenant and its rows and leave FORCE on). It runs the migration's own
statements in a transaction that always rolls back, so the test sandboxes survive.
"""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.integration.conftest import MakeTenant
from tests.integration.test_cleanup import rows_left

pytestmark = pytest.mark.integration

MIGRATION = (
    Path(__file__).resolve().parents[2] / "migrations/versions/0012_encrypt_conversations.py"
)


def load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("migration_0012", MIGRATION)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def test_the_delete_removes_every_tenant_and_every_row_in_them(
    owner_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    before = await rows_left(owner_engine, tenant.id)
    statements: tuple[str, ...] = load_migration().DELETE_EVERY_TENANT

    async with owner_engine.connect() as connection:
        transaction = await connection.begin()
        try:
            for statement in statements:
                await connection.exec_driver_sql(statement)
            tenants: int = (
                await connection.execute(text("SELECT count(*) FROM tenants"))
            ).scalar_one()
            assistant_rows: int = (
                await connection.execute(text("SELECT count(*) FROM ai_turns"))
            ).scalar_one()
            # FORCE is back on, so the owner is held to the policies again.
            forced: bool = (
                await connection.execute(
                    text("SELECT relforcerowsecurity FROM pg_class WHERE relname = 'tenants'")
                )
            ).scalar_one()
        finally:
            await transaction.rollback()

    assert before["ai_turns"] > 0
    assert tenants == 0
    assert assistant_rows == 0
    assert forced is True
