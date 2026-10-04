"""The two roles have exactly the privileges the spec lists: nothing missing and nothing extra.

A new table that forgets its grants fails closed, because the API can't touch it. A grant broader
than the spec fails these tests.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.integration

ROLES = ("od_app", "od_cleanup")
READ_AND_ADD = ("tenants", "locations", "departments", "people", "person_private", "holidays")

EXPECTED_TABLE_GRANTS = {
    *(("od_app", table, privilege) for table in READ_AND_ADD for privilege in ("SELECT", "INSERT")),
    # Append-only: no UPDATE or DELETE, ever.
    ("od_app", "audit_events", "SELECT"),
    ("od_app", "audit_events", "INSERT"),
    ("od_app", "sessions", "SELECT"),
    ("od_app", "sessions", "INSERT"),
    ("od_app", "sessions", "DELETE"),
    ("od_cleanup", "tenants", "SELECT"),
    ("od_cleanup", "tenants", "DELETE"),
}
EXPECTED_SCHEMA_GRANTS = {
    # Postgres's own default: everyone may use the public schema.
    ("PUBLIC", "public", "USAGE"),
    ("od_app", "public", "USAGE"),
    ("od_app", "app", "USAGE"),
    # The cleanup login deletes through od_cleanup's policies, which call no app function, and a
    # cascade runs as the table owner. It needs no access to the app schema.
    ("od_cleanup", "public", "USAGE"),
}

# Grants to PUBLIC count too, because every role inherits them.
TABLE_GRANTS = """
    SELECT coalesce(r.rolname, 'PUBLIC'), c.relname, a.privilege_type
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    CROSS JOIN LATERAL aclexplode(c.relacl) a
    LEFT JOIN pg_roles r ON r.oid = a.grantee
    WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
      AND (a.grantee = 0 OR r.rolname = ANY(:roles))
"""

COLUMN_GRANTS = """
    SELECT coalesce(r.rolname, 'PUBLIC'), c.relname, col.attname, a.privilege_type
    FROM pg_attribute col
    JOIN pg_class c ON c.oid = col.attrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    CROSS JOIN LATERAL aclexplode(col.attacl) a
    LEFT JOIN pg_roles r ON r.oid = a.grantee
    WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
      AND (a.grantee = 0 OR r.rolname = ANY(:roles))
"""

SCHEMA_GRANTS = """
    SELECT coalesce(r.rolname, 'PUBLIC'), n.nspname, a.privilege_type
    FROM pg_namespace n
    CROSS JOIN LATERAL aclexplode(n.nspacl) a
    LEFT JOIN pg_roles r ON r.oid = a.grantee
    WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
      AND (a.grantee = 0 OR r.rolname = ANY(:roles))
"""


async def grants(engine: AsyncEngine, query: str) -> set[tuple[str, ...]]:
    async with engine.connect() as connection:
        rows = await connection.execute(text(query), {"roles": list(ROLES)})
        return {tuple(row) for row in rows}


async def test_the_roles_have_exactly_the_planned_table_privileges(
    app_engine: AsyncEngine,
) -> None:
    assert await grants(app_engine, TABLE_GRANTS) == EXPECTED_TABLE_GRANTS


async def test_no_role_has_privileges_on_single_columns(app_engine: AsyncEngine) -> None:
    assert await grants(app_engine, COLUMN_GRANTS) == set()


async def test_the_roles_can_use_exactly_the_planned_schemas(
    app_engine: AsyncEngine,
) -> None:
    assert await grants(app_engine, SCHEMA_GRANTS) == EXPECTED_SCHEMA_GRANTS
