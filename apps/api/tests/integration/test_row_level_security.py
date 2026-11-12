"""Row-level security covers every tenant table, and nothing in the schema crosses tenants."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.integration

# `sessions` has a tenant_id and row-level security, but not the plain tenant rule: a session is
# looked up by its token before the tenant is known, so its rules (migration 0017) also match the
# presented token hash. They are checked exactly in test_sessions_rls.py. It is the only such table.
NOT_THE_PLAIN_TENANT_RULE = "sessions"

# The catalog queries below find the tables on their own, so a new table is covered without being
# listed. These names only stop a broken query from passing by finding nothing.
KNOWN_TABLES = {
    "tenants",
    "locations",
    "departments",
    "people",
    "person_private",
    "holidays",
    "ai_conversations",
    "ai_messages",
    "ai_turns",
    "ai_feedback",
    "ai_spend",
    "ai_proposals",
    "time_off_openings",
    "time_off_requests",
    "cases",
    "case_summaries",
    "case_events",
    "ai_console_turns",
}
# Global tables: no tenant_id, so they sit outside row-level security. The handbook is read-only to
# the API. ai_spend_daily holds only a day and an amount, so every sandbox's spending can be summed
# into the demo's daily cap; it carries no tenant and no personal data.
GLOBAL_TABLES = {
    "handbook_versions",
    "handbook_sections",
    "handbook_chunks",
    "ai_spend_daily",
}
KNOWN_UNIQUE_INDEXES = {"uq_people_tenant_id_work_email", "pk_person_private"}

# Ordinary and partitioned tables, plus materialized views ('m') and foreign tables ('f'). Row-level
# security can't be enabled on the last two, so one with a tenant_id can never pass this test.
TABLES_WITH_A_TENANT = """
    SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE c.relkind IN ('r', 'p', 'm', 'f')
      AND n.nspname NOT IN ('pg_catalog', 'information_schema')
      AND (c.relname = 'tenants' OR EXISTS (
          SELECT FROM pg_attribute a
          WHERE a.attrelid = c.oid AND a.attname = 'tenant_id' AND NOT a.attisdropped
      ))
"""

# Each unique index on a table with a tenant_id, with its first column and that column's type.
# An expression index has no first column, so it comes back with NULLs and fails the rule.
UNIQUE_INDEXES = """
    SELECT c.relname, i.relname, x.indisprimary, x.indnkeyatts, a.attname,
           format_type(a.atttypid, a.atttypmod)
    FROM pg_index x
    JOIN pg_class c ON c.oid = x.indrelid
    JOIN pg_class i ON i.oid = x.indexrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    LEFT JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = x.indkey[0]
    WHERE x.indisunique
      AND n.nspname NOT IN ('pg_catalog', 'information_schema')
      AND c.relname <> :not_a_tenant_table
      AND EXISTS (
          SELECT FROM pg_attribute t
          WHERE t.attrelid = c.oid AND t.attname = 'tenant_id' AND NOT t.attisdropped
      )
"""

# The permissive policies that apply to the connected login: those for PUBLIC (role 0), for a role
# the login is a member of (od_app), or for the login itself. Restrictive policies only narrow.
PERMISSIVE_POLICIES = """
    SELECT c.relname, p.polname, p.polcmd::text,
           pg_get_expr(p.polqual, p.polrelid), pg_get_expr(p.polwithcheck, p.polrelid)
    FROM pg_policy p
    JOIN pg_class c ON c.oid = p.polrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE p.polpermissive
      AND n.nspname NOT IN ('pg_catalog', 'information_schema')
      AND (0 = ANY (p.polroles) OR EXISTS (
          SELECT FROM unnest(p.polroles) AS member_of(role_oid)
          WHERE pg_has_role(current_user, member_of.role_oid, 'USAGE')
      ))
    ORDER BY c.relname, p.polname
"""

VIEWS_WITHOUT_SECURITY_INVOKER = """
    SELECT n.nspname || '.' || c.relname
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE c.relkind = 'v'
      AND n.nspname NOT IN ('pg_catalog', 'information_schema')
      AND NOT coalesce((
          SELECT option_value::boolean FROM pg_options_to_table(c.reloptions)
          WHERE option_name = 'security_invoker'
      ), false)
"""


async def test_every_tenant_table_has_row_level_security_enabled_and_forced(
    app_engine: AsyncEngine,
) -> None:
    async with app_engine.connect() as connection:
        rows = (await connection.execute(text(TABLES_WITH_A_TENANT))).all()
    tables = {name: (enabled, forced) for name, enabled, forced in rows}

    assert set(tables) >= KNOWN_TABLES
    unprotected = {name for name, flags in tables.items() if flags != (True, True)}
    assert unprotected == set()
    assert NOT_THE_PLAIN_TENANT_RULE in tables


async def test_the_global_tables_have_no_tenant_id(app_engine: AsyncEngine) -> None:
    # They are outside row-level security on purpose. A tenant_id on one would also put it in the
    # test above, which would then demand row-level security on it.
    async with app_engine.connect() as connection:
        rows = (await connection.execute(text(TABLES_WITH_A_TENANT))).all()
        existing = set(
            await connection.scalars(
                text(
                    "SELECT table_name FROM information_schema.tables"
                    " WHERE table_schema = 'public' AND table_name = ANY(:names)"
                ),
                {"names": sorted(GLOBAL_TABLES)},
            )
        )

    assert existing == GLOBAL_TABLES
    assert {name for name, *_ in rows}.isdisjoint(GLOBAL_TABLES)


async def test_unique_indexes_on_tenant_tables_start_with_tenant_id(
    app_engine: AsyncEngine,
) -> None:
    async with app_engine.connect() as connection:
        rows = (
            await connection.execute(
                text(UNIQUE_INDEXES), {"not_a_tenant_table": NOT_THE_PLAIN_TENANT_RULE}
            )
        ).all()

    assert {index for _, index, *_ in rows} >= KNOWN_UNIQUE_INDEXES
    # A global unique rule would leak whether a value exists in another tenant. The exception is a
    # single-column primary key on a UUID the server generates.
    breaking_the_rule = [
        (table, index)
        for table, index, is_primary, key_count, first_column, first_type in rows
        if first_column != "tenant_id"
        and not (is_primary and key_count == 1 and first_type == "uuid")
    ]
    assert breaking_the_rule == []


async def test_every_view_runs_with_the_callers_permissions(app_engine: AsyncEngine) -> None:
    # A view runs as its owner by default, which would skip row-level security. Phase 1 has no
    # views; this guards the ones to come.
    async with app_engine.connect() as connection:
        result = await connection.execute(text(VIEWS_WITHOUT_SECURITY_INVOKER))
        views: list[str] = list(result.scalars())

    assert views == []


def canonical(column: str) -> str:
    """The policy expression as Postgres prints it back (pg_get_expr), which is how it is stored."""
    return f"({column} = ( SELECT app.current_tenant_id() AS current_tenant_id))"


def squeezed(expression: str | None) -> str:
    return " ".join((expression or "").split())


async def test_the_only_permissive_policy_for_the_api_is_the_tenant_rule(
    app_engine: AsyncEngine,
) -> None:
    # Permissive policies are ORed together, so one extra policy such as `USING (true)` would show
    # every tenant's rows. Each tenant table must have exactly the one rule, in its exact form.
    async with app_engine.connect() as connection:
        tenant_tables = {
            name for name, *_ in (await connection.execute(text(TABLES_WITH_A_TENANT))).all()
        } - {NOT_THE_PLAIN_TENANT_RULE}
        rows = (await connection.execute(text(PERMISSIVE_POLICIES))).all()
    found: dict[str, list[tuple[str, str, str, str]]] = {}
    for table, policy, command, using, with_check in rows:
        found.setdefault(table, []).append((policy, command, squeezed(using), squeezed(with_check)))

    def rule(policy: str, column: str) -> list[tuple[str, str, str, str]]:
        return [(policy, "*", canonical(column), canonical(column))]

    assert tenant_tables >= KNOWN_TABLES
    expected = {table: rule("tenant_isolation", "tenant_id") for table in tenant_tables}
    expected["tenants"] = rule("tenant_self", "id")
    # Sessions have three rules of their own, no tenant-only one; test_sessions_rls.py pins them.
    assert sorted(policy for policy, *_ in found.pop("sessions")) == [
        "session_delete",
        "session_insert",
        "session_select",
    ]
    # The start counter has no tenant: the API must count every address, so its two rules are
    # `true`, one for reading and one for adding. Nothing else may apply to it.
    assert sorted(found.pop("sandbox_starts")) == [
        ("app_counts_every_start", "r", "true", ""),
        ("app_records_a_start", "a", "", "true"),
    ]
    # The ledger has no tenant either: the budget sums every sandbox, so the API's rules are `true`.
    assert sorted(found.pop("ai_spend_daily")) == [
        ("app_reads_the_ledger", "r", "true", ""),
        ("app_writes_the_ledger", "a", "", "true"),
    ]
    assert found == expected


async def test_the_start_counter_has_row_level_security_enabled_and_forced(
    app_engine: AsyncEngine,
) -> None:
    async with app_engine.connect() as connection:
        flags = (
            await connection.execute(
                text(
                    "SELECT relrowsecurity, relforcerowsecurity FROM pg_class"
                    " WHERE relname = 'sandbox_starts'"
                )
            )
        ).one()
    assert tuple(flags) == (True, True)


async def test_the_spend_ledger_has_row_level_security_enabled_but_not_forced(
    app_engine: AsyncEngine,
) -> None:
    """Enabled, so the API's and the cleanup login's rules apply; not forced, so the owner's spend
    scripts still see every row on a managed database whose owner is not a superuser."""
    async with app_engine.connect() as connection:
        flags = (
            await connection.execute(
                text(
                    "SELECT relrowsecurity, relforcerowsecurity FROM pg_class"
                    " WHERE relname = 'ai_spend_daily'"
                )
            )
        ).one()
    assert tuple(flags) == (True, False)
