"""The two roles have exactly the privileges the spec lists: nothing missing and nothing extra.

A new table that forgets its grants fails closed, because the API can't touch it. A grant broader
than the spec fails these tests.
"""

import pytest
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings

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
    # The handbook is global and read-only to the API. Ingestion runs as the database owner, and the
    # cleanup login needs nothing from it.
    *(
        ("od_app", table, "SELECT")
        for table in ("handbook_versions", "handbook_sections", "handbook_chunks")
    ),
    # The assistant's tables (Phase 4) are insert-only, with one exception: a turn is added as
    # `running` and updated once, to its end. Nothing is deleted: the rows go with their sandbox
    # when its tenant is deleted, which runs as the table owner, and the cleanup login needs no
    # grant for that.
    *(
        ("od_app", table, privilege)
        for table in (
            "ai_conversations",
            "ai_messages",
            "ai_feedback",
            "ai_spend",
            "ai_spend_daily",
        )
        for privilege in ("SELECT", "INSERT")
    ),
    # A turn is updated only through the columns below, and a trigger refuses once it has ended.
    *(("od_app", "ai_turns", privilege) for privilege in ("SELECT", "INSERT")),
    # Time off (Phase 5): an opening balance is written once. A request and a proposal are added
    # and then only their status columns change, one way, which a trigger enforces. Nothing is
    # deleted, and the cleanup login needs no grant: the rows go with their sandbox.
    *(
        ("od_app", table, privilege)
        for table in ("time_off_openings", "time_off_requests", "ai_proposals")
        for privilege in ("SELECT", "INSERT")
    ),
    # Cases (Phase 6): added and then, for a case, only its status columns change. No DELETE: the
    # rows go with their sandbox, and the cleanup login needs no grant.
    *(
        ("od_app", table, privilege)
        for table in ("cases", "case_summaries", "case_events")
        for privilege in ("SELECT", "INSERT")
    ),
    ("od_cleanup", "tenants", "SELECT"),
    ("od_cleanup", "tenants", "DELETE"),
}
# The tables with column grants. A turn's columns change when it ends: its identity (id, tenant_id,
# person_id, conversation_id), its question_ciphertext, and started_at are never updatable. A
# request changes only by a decision or a cancel, and a proposal only when it ends: their identity,
# dates, amounts, payload, card, and expiry are never updatable. Nothing else in the schema has a
# column grant.
UPDATABLE_TURN_COLUMNS = {
    "status",
    "error_code",
    "ended_at",
    "answer_ciphertext",
    "citations",
    "guard_verdict",
    "tool_calls",
    "sections_retrieved",
    "served_by_models",
    "effort",
    "prompt_version",
    "toolset_version",
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "cost_usd",
    "first_event_ms",
    "total_ms",
    "refusal",
    "fallback",
    "injection_suspected",
}
UPDATABLE_REQUEST_COLUMNS = {"status", "decided_by", "decided_at", "decision_note", "canceled_at"}
UPDATABLE_PROPOSAL_COLUMNS = {"status", "ended_at", "outcome"}
# A case's status moves one way, by trigger, and HR alone can change it. Its words, category, dates,
# and owner are never updatable, and a summary and a timeline event never change at all.
UPDATABLE_CASE_COLUMNS = {"status", "status_changed_at"}
EXPECTED_COLUMN_GRANTS = {
    *(("od_app", "ai_turns", column, "UPDATE") for column in UPDATABLE_TURN_COLUMNS),
    *(("od_app", "time_off_requests", column, "UPDATE") for column in UPDATABLE_REQUEST_COLUMNS),
    *(("od_app", "ai_proposals", column, "UPDATE") for column in UPDATABLE_PROPOSAL_COLUMNS),
    *(("od_app", "cases", column, "UPDATE") for column in UPDATABLE_CASE_COLUMNS),
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


def login_roles(database_settings: Settings) -> tuple[str, str]:
    """The two login users, named by the usernames in the configured URLs."""
    app_url = database_settings.database_url
    cleanup_url = database_settings.cleanup_database_url
    assert app_url is not None
    assert cleanup_url is not None
    app_login = make_url(str(app_url)).username
    cleanup_login = make_url(str(cleanup_url)).username
    assert app_login
    assert cleanup_login
    return app_login, cleanup_login


async def grants(
    engine: AsyncEngine, query: str, roles: tuple[str, ...] = ROLES
) -> set[tuple[str, ...]]:
    async with engine.connect() as connection:
        rows = await connection.execute(text(query), {"roles": list(roles)})
        return {tuple(row) for row in rows}


async def test_the_roles_have_exactly_the_planned_table_privileges(
    app_engine: AsyncEngine,
) -> None:
    assert await grants(app_engine, TABLE_GRANTS) == EXPECTED_TABLE_GRANTS


async def test_the_only_column_grants_are_the_updatable_columns_of_turns_requests_proposals_cases(
    app_engine: AsyncEngine,
) -> None:
    assert await grants(app_engine, COLUMN_GRANTS) == EXPECTED_COLUMN_GRANTS


def direct_grants(rows: set[tuple[str, ...]], roles: tuple[str, ...]) -> set[tuple[str, ...]]:
    """Only the rows granted to these roles. The queries also return PUBLIC, checked elsewhere."""
    return {row for row in rows if row[0] in roles}


async def test_the_login_users_have_no_privileges_of_their_own(
    app_engine: AsyncEngine, database_settings: Settings
) -> None:
    """Everything reaches the logins through od_app and od_cleanup, never by a direct grant."""
    logins = login_roles(database_settings)
    assert set(logins).isdisjoint(ROLES)
    assert direct_grants(await grants(app_engine, TABLE_GRANTS, logins), logins) == set()
    assert direct_grants(await grants(app_engine, COLUMN_GRANTS, logins), logins) == set()
    assert direct_grants(await grants(app_engine, SCHEMA_GRANTS, logins), logins) == set()


# An owner has no ACL entry, so the grants queries above can't see ownership.
OWNED_TABLES = """
    SELECT n.nspname, c.relname, r.rolname
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    JOIN pg_roles r ON r.oid = c.relowner
    WHERE n.nspname IN ('public', 'app')
      AND c.relkind IN ('r', 'p')
      AND r.rolname = ANY(:roles)
"""


async def test_neither_role_nor_login_owns_a_table(
    app_engine: AsyncEngine, database_settings: Settings
) -> None:
    roles = (*ROLES, *login_roles(database_settings))
    assert await grants(app_engine, OWNED_TABLES, roles) == set()


async def test_the_roles_can_use_exactly_the_planned_schemas(
    app_engine: AsyncEngine,
) -> None:
    assert await grants(app_engine, SCHEMA_GRANTS) == EXPECTED_SCHEMA_GRANTS
