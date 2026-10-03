"""Migration 0002 reuses an existing od_app or od_cleanup only if it is safe to.

Roles belong to the whole Postgres server, so a role with one of these names may already exist from
elsewhere, with powers it should not have. The test runs the migration's own statement inside a
transaction that always rolls back, after changing the real role the way a stranger might have.
"""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.integration

MIGRATION = Path(__file__).resolve().parents[2] / "migrations/versions/0002_app_schema_and_roles.py"
ROLES = ("od_app", "od_cleanup")
POWERS = ("LOGIN", "SUPERUSER", "BYPASSRLS", "CREATEROLE", "CREATEDB", "REPLICATION")


def load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("migration_0002", MIGRATION)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def run_create_roles_after(owner_engine: AsyncEngine, *statements: str) -> None:
    """Run the given statements, then the migration's role statement, then always roll back."""
    create_roles: str = load_migration().CREATE_ROLES
    async with owner_engine.connect() as connection:
        transaction = await connection.begin()
        try:
            for statement in statements:
                await connection.exec_driver_sql(statement)
            await connection.exec_driver_sql(create_roles)
        finally:
            await transaction.rollback()


async def test_roles_that_are_safe_to_reuse_are_accepted(owner_engine: AsyncEngine) -> None:
    await run_create_roles_after(owner_engine)


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("power", POWERS)
async def test_an_existing_role_with_a_power_it_should_not_have_stops_the_migration(
    owner_engine: AsyncEngine, role: str, power: str
) -> None:
    with pytest.raises(DBAPIError, match=f"{role}.*not safe to reuse"):
        await run_create_roles_after(owner_engine, f"ALTER ROLE {role} {power}")


@pytest.mark.parametrize("role", ROLES)
async def test_an_existing_role_that_belongs_to_another_role_stops_the_migration(
    owner_engine: AsyncEngine, role: str
) -> None:
    with pytest.raises(DBAPIError, match=f"{role}.*not safe to reuse"):
        await run_create_roles_after(
            owner_engine,
            "CREATE ROLE od_test_elsewhere NOLOGIN",
            f"GRANT od_test_elsewhere TO {role}",
        )


async def test_the_failed_checks_changed_nothing(owner_engine: AsyncEngine) -> None:
    async with owner_engine.connect() as connection:
        rows = await connection.execute(
            text(
                "SELECT rolname, rolcanlogin, rolsuper, rolbypassrls, rolcreaterole, rolcreatedb,"
                " rolreplication FROM pg_roles WHERE rolname IN ('od_app', 'od_cleanup')"
                " ORDER BY rolname"
            )
        )
        roles = [tuple(row) for row in rows]
        leftover = await connection.scalar(
            text("SELECT EXISTS (SELECT FROM pg_roles WHERE rolname = 'od_test_elsewhere')")
        )

    assert roles == [
        ("od_app", False, False, False, False, False, False),
        ("od_cleanup", False, False, False, False, False, False),
    ]
    assert leftover is False
