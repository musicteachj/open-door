"""Put sessions under row-level security, give each a family, and store audit NULLs as NULL.

Phase 8, stage 1. Three changes, each closing a gap the backlog has carried since Phase 1.

Row-level security on `sessions`. Until now the table sat outside it, because a session is looked up
by its token before the tenant is known. So the API's login could read, insert, and delete every
sandbox's sessions, and the Phase 1 close-out review inserted an HR session in another sandbox
from `psql`. Now (a code path can no longer do that; raw SQL as the login can still set another
sandbox's context itself, an accepted risk in the threat model):

  - Reads (SELECT) and deletes match a row when its token hash equals the one the lookup
    presented (`app.session_token_hash`, set with set_config inside the transaction and read by
    `app.current_session_token_hash()`), or when its tenant is the transaction's tenant. A bare
    SELECT with no context sees nothing.
  - Inserts must be for the transaction's tenant, with an expiry no later than that sandbox's.
    The expiry check reads `tenants` under its own rule, which shows the current sandbox only.
  - There is still no UPDATE grant. The rules are written TO od_app and use the (SELECT ...) form
    of the other tables, so Postgres evaluates the functions once per query. No SECURITY DEFINER.
  - Deleting a sandbox still removes its sessions: that is a foreign key's ON DELETE CASCADE, a
    referential action that row-level security does not apply to.

`family_id`. Each session belongs to a family: a new sandbox's first session starts one, and a
persona switch copies it to the replacement. Sign-out deletes the whole family, so a switch in one
tab racing a sign-out in another can no longer leave the new persona signed in. Existing rows each
get a family of their own, so no one is signed out.

Audit NULLs. `audit_events.before` and `after` stored the JSON value `null` for "nothing", not SQL
NULL, so `IS NULL` never found them. The model now stores SQL NULL, and this migration converts the
rows already written. The UPDATE runs as the table's owner, which sees these rows only if it
bypasses row-level security (a superuser, as in development and CI). On a managed database whose
owner is not a superuser it matches nothing, which is fine because Phase 9 starts from an empty
database. Nothing forbids updating audit rows as the owner: the API's login has no UPDATE grant.

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-09
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0017"
down_revision: str | Sequence[str] | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The presented token's hash, hex encoded in the setting (a setting is text). Same style as the
# other context functions in 0002.
SESSION_HASH_FUNCTION = """
    CREATE FUNCTION app.current_session_token_hash() RETURNS bytea
    LANGUAGE sql STABLE
    RETURN decode(NULLIF(pg_catalog.current_setting('app.session_token_hash', true), ''), 'hex')
"""

POLICIES = (
    "ALTER TABLE sessions ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sessions FORCE ROW LEVEL SECURITY",
    """
    CREATE POLICY session_select ON sessions FOR SELECT TO od_app
        USING (
            token_hash = (SELECT app.current_session_token_hash())
            OR tenant_id = (SELECT app.current_tenant_id())
        )
    """,
    """
    CREATE POLICY session_insert ON sessions FOR INSERT TO od_app
        WITH CHECK (
            tenant_id = (SELECT app.current_tenant_id())
            AND expires_at <= (SELECT t.expires_at FROM tenants t WHERE t.id = sessions.tenant_id)
        )
    """,
    """
    CREATE POLICY session_delete ON sessions FOR DELETE TO od_app
        USING (
            token_hash = (SELECT app.current_session_token_hash())
            OR tenant_id = (SELECT app.current_tenant_id())
        )
    """,
)

# Exposed as constants so a test can run the very statements on a legacy row.
AUDIT_NULLS_UP = (
    "UPDATE audit_events SET before = NULL WHERE before = 'null'::jsonb",
    "UPDATE audit_events SET after = NULL WHERE after = 'null'::jsonb",
)
AUDIT_NULLS_DOWN = (
    "UPDATE audit_events SET after = 'null'::jsonb WHERE after IS NULL",
    "UPDATE audit_events SET before = 'null'::jsonb WHERE before IS NULL",
)


def upgrade() -> None:
    # Before row-level security is forced, so the owner sees every row it backfills. Each existing
    # session gets a family of its own; the default is dropped so new rows must name one.
    op.execute("ALTER TABLE sessions ADD COLUMN family_id uuid NOT NULL DEFAULT gen_random_uuid()")
    op.execute("ALTER TABLE sessions ALTER COLUMN family_id DROP DEFAULT")
    op.create_index(op.f("ix_sessions_family_id"), "sessions", ["family_id"])
    op.execute(SESSION_HASH_FUNCTION)
    for statement in POLICIES:
        op.execute(statement)
    for statement in AUDIT_NULLS_UP:
        op.execute(statement)


def downgrade() -> None:
    # Back to the JSON null the old model wrote. Same caveat as the upgrade: the owner must see
    # the rows.
    for statement in AUDIT_NULLS_DOWN:
        op.execute(statement)
    op.execute("DROP POLICY session_delete ON sessions")
    op.execute("DROP POLICY session_insert ON sessions")
    op.execute("DROP POLICY session_select ON sessions")
    op.execute("ALTER TABLE sessions NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE sessions DISABLE ROW LEVEL SECURITY")
    op.execute("DROP FUNCTION app.current_session_token_hash()")
    op.drop_index(op.f("ix_sessions_family_id"), table_name="sessions")
    op.drop_column("sessions", "family_id")
