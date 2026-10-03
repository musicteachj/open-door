"""Create the database roles and the functions row-level security reads the tenant from.

od_app is the API's role and od_cleanup the expired-tenant cleanup's. Neither can log in: the
bootstrap script (scripts/bootstrap_db_users.py) creates the login users and grants them these
roles. Migration 0003 grants the roles their table privileges.

A role that already exists under either name is reused only if it has no extra power (see
CREATE_ROLES), because the login users inherit everything the roles can do.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-03
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Roles belong to the whole Postgres server, not to one database, so another database on the same
# server may have created them already. An existing role is reused only if it is exactly what this
# migration would have made: it can't log in, has none of the powers below, and belongs to no other
# role. Otherwise every login granted od_app or od_cleanup would inherit those powers, including
# BYPASSRLS, which skips row-level security.
CREATE_ROLES = """
DO $$
DECLARE
    wanted text;
    existing record;
BEGIN
    FOREACH wanted IN ARRAY ARRAY['od_app', 'od_cleanup'] LOOP
        SELECT * INTO existing FROM pg_roles WHERE rolname = wanted;
        IF NOT FOUND THEN
            EXECUTE format('CREATE ROLE %I NOLOGIN', wanted);
        ELSIF existing.rolcanlogin OR existing.rolsuper OR existing.rolbypassrls
              OR existing.rolcreaterole OR existing.rolcreatedb OR existing.rolreplication
              OR EXISTS (SELECT FROM pg_auth_members WHERE member = existing.oid) THEN
            RAISE EXCEPTION USING MESSAGE = format(
                'The existing role %s is not safe to reuse: it must be NOLOGIN, have no '
                'SUPERUSER, BYPASSRLS, CREATEROLE, CREATEDB, or REPLICATION, and belong to no '
                'other role. Fix or drop it, then migrate again.',
                wanted
            );
        END IF;
    END LOOP;
END
$$
"""

# Each setting is set per transaction with set_config(..., true). Once a transaction has set one,
# later transactions on the same connection read '' instead of NULL, and ''::uuid raises an error.
# NULLIF turns '' back into NULL, which matches no row. Never LEAKPROOF, never SECURITY DEFINER.
#
# The bodies use the SQL-standard form (RETURN expression), which Postgres parses and binds when
# the function is created. A body in quotes would look up its names on every call, along the
# caller's search_path.
CONTEXT_FUNCTIONS = (
    """
    CREATE FUNCTION app.current_tenant_id() RETURNS uuid
    LANGUAGE sql STABLE
    RETURN NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::uuid
    """,
    """
    CREATE FUNCTION app.current_person_id() RETURNS uuid
    LANGUAGE sql STABLE
    RETURN NULLIF(pg_catalog.current_setting('app.person_id', true), '')::uuid
    """,
    """
    CREATE FUNCTION app.current_is_hr() RETURNS boolean
    LANGUAGE sql STABLE
    RETURN coalesce(NULLIF(pg_catalog.current_setting('app.is_hr', true), '')::boolean, false)
    """,
)


def upgrade() -> None:
    op.execute(CREATE_ROLES)
    op.execute("CREATE SCHEMA app")
    for function in CONTEXT_FUNCTIONS:
        op.execute(function)
    op.execute("GRANT USAGE ON SCHEMA public TO od_app, od_cleanup")
    # Only the API's role calls the context functions. The cleanup role's policies don't, and a
    # cascading delete runs as the table owner.
    op.execute("GRANT USAGE ON SCHEMA app TO od_app")


def downgrade() -> None:
    op.execute("REVOKE USAGE ON SCHEMA public FROM od_app, od_cleanup")
    op.execute("DROP FUNCTION app.current_is_hr()")
    op.execute("DROP FUNCTION app.current_person_id()")
    op.execute("DROP FUNCTION app.current_tenant_id()")
    op.execute("DROP SCHEMA app")
    # The roles stay. Other databases on the server may use them, and dropping them would also
    # drop the login users' memberships. Upgrading again reuses them.
