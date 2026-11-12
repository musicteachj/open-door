"""Count sandbox starts per address, so one visitor can't fill the database (ADR 0021).

Phase 8, stage 4. `sandbox_starts` holds one row per sandbox started: a keyed hash of the visitor's
address (HMAC-SHA256 under SANDBOX_IP_HASH_KEY, always 32 bytes, checked) and the time. The API
counts them to apply the limits: so many an hour and a day per address, and so many a UTC day in
all. It holds no raw address and no tenant: a start is counted whether or not its sandbox still
exists.

`created_at` is stamped by 0003's `app.stamp_tenant_created_at` trigger (it only sets the column to
now()), so a client can't backdate a start to dodge the count. The table has row-level security,
enabled and forced, with two permissive policies for the API's login (read and insert): it must
count every address, so they are `true`. The grant is the least that works, SELECT and INSERT,
with no UPDATE and no DELETE. The trigger function runs as the caller (not SECURITY DEFINER), as
0003 wrote it.

Part two, the cleanup job (Phase 8, stage 4, task 26). The cleanup login (od_cleanup) may now also
SELECT and DELETE `sandbox_starts` rows older than 24 hours, `ai_spend_daily` rows whose UTC day is
more than 30 days back, and `handbook_versions` (sections and chunks go by cascade). Each rule is
a policy scoped TO od_cleanup, so the API never inherits it, and the table's grant to od_cleanup
is the only new privilege. `ai_spend_daily` had no row-level security (it has no tenant); it gets
it now, enabled but not forced (the owner, who runs the spend scripts, keeps reading it without a
policy), with two permissive policies for the API's login (`true`, as for the
start counter) so the budget code is unchanged. `handbook_versions` stays outside row-level
security: a policy that reads its own table recurses. Its safety net is instead a plain
BEFORE DELETE trigger (not SECURITY DEFINER) that refuses to delete the newest published version,
the one every new sandbox is pinned to, with SQLSTATE OD006. A version a live tenant uses is
refused by the foreign key from `tenants` (RESTRICT), which the job treats as "in use, skip".

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | Sequence[str] | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATEMENTS = (
    "ALTER TABLE sandbox_starts ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sandbox_starts FORCE ROW LEVEL SECURITY",
    "CREATE POLICY app_counts_every_start ON sandbox_starts FOR SELECT TO od_app USING (true)",
    "CREATE POLICY app_records_a_start ON sandbox_starts FOR INSERT TO od_app WITH CHECK (true)",
    "GRANT SELECT, INSERT ON sandbox_starts TO od_app",
    """
    CREATE TRIGGER stamp_created_at BEFORE INSERT ON sandbox_starts
        FOR EACH ROW EXECUTE FUNCTION app.stamp_tenant_created_at()
    """,
)


SPEND_CUTOFF = "(now() AT TIME ZONE 'UTC')::date - 30"

# The same order 0005's pin trigger uses to choose the newest published version.
NEWEST_FUNCTION = """
    CREATE FUNCTION app.refuse_newest_handbook_version_delete() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path = pg_catalog, pg_temp
    AS $$
    DECLARE
        newest uuid;
    BEGIN
        SELECT v.id INTO newest
        FROM public.handbook_versions v
        WHERE v.published_at IS NOT NULL
        ORDER BY v.published_at DESC, v.created_at DESC, v.id DESC
        LIMIT 1;
        IF OLD.id = newest THEN
            RAISE EXCEPTION 'the newest published handbook version cannot be deleted'
                USING ERRCODE = 'OD006';
        END IF;
        RETURN OLD;
    END
    $$
"""

CLEANUP_STATEMENTS = (
    "GRANT SELECT, DELETE ON ai_spend_daily, sandbox_starts, handbook_versions TO od_cleanup",
    """
    CREATE POLICY cleanup_select ON sandbox_starts FOR SELECT TO od_cleanup
        USING (created_at < now() - interval '24 hours')
    """,
    """
    CREATE POLICY cleanup_delete ON sandbox_starts FOR DELETE TO od_cleanup
        USING (created_at < now() - interval '24 hours')
    """,
    # Enabled, not forced: the owner keeps reading and deleting the ledger without a policy of its
    # own (scripts/clear_browser_test_spend.py, app/db/spend_cleanup.py), which a forced table would
    # quietly turn into matching nothing on a managed database whose owner is not a superuser.
    "ALTER TABLE ai_spend_daily ENABLE ROW LEVEL SECURITY",
    "CREATE POLICY app_reads_the_ledger ON ai_spend_daily FOR SELECT TO od_app USING (true)",
    "CREATE POLICY app_writes_the_ledger ON ai_spend_daily FOR INSERT TO od_app WITH CHECK (true)",
    f"""
    CREATE POLICY cleanup_select ON ai_spend_daily FOR SELECT TO od_cleanup
        USING (day < {SPEND_CUTOFF})
    """,
    f"""
    CREATE POLICY cleanup_delete ON ai_spend_daily FOR DELETE TO od_cleanup
        USING (day < {SPEND_CUTOFF})
    """,
    NEWEST_FUNCTION,
    "REVOKE EXECUTE ON FUNCTION app.refuse_newest_handbook_version_delete() FROM PUBLIC",
    """
    CREATE TRIGGER refuse_newest_version_delete BEFORE DELETE ON handbook_versions
        FOR EACH ROW EXECUTE FUNCTION app.refuse_newest_handbook_version_delete()
    """,
)

CLEANUP_DOWNGRADE = (
    "DROP TRIGGER refuse_newest_version_delete ON handbook_versions",
    "DROP FUNCTION app.refuse_newest_handbook_version_delete()",
    "DROP POLICY cleanup_delete ON ai_spend_daily",
    "DROP POLICY cleanup_select ON ai_spend_daily",
    "DROP POLICY app_writes_the_ledger ON ai_spend_daily",
    "DROP POLICY app_reads_the_ledger ON ai_spend_daily",
    # Clears a force flag too, should one have been set by hand: DISABLE leaves it in place.
    "ALTER TABLE ai_spend_daily NO FORCE ROW LEVEL SECURITY",
    "ALTER TABLE ai_spend_daily DISABLE ROW LEVEL SECURITY",
    "DROP POLICY cleanup_delete ON sandbox_starts",
    "DROP POLICY cleanup_select ON sandbox_starts",
    "REVOKE SELECT, DELETE ON ai_spend_daily, sandbox_starts, handbook_versions FROM od_cleanup",
)


def upgrade() -> None:
    op.create_table(
        "sandbox_starts",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("ip_hash", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "octet_length(ip_hash) = 32", name=op.f("ck_sandbox_starts_ip_hash_is_32_bytes")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sandbox_starts")),
    )
    op.create_index(
        op.f("ix_sandbox_starts_ip_hash_created_at"), "sandbox_starts", ["ip_hash", "created_at"]
    )
    op.create_index(op.f("ix_sandbox_starts_created_at"), "sandbox_starts", ["created_at"])
    for statement in STATEMENTS:
        op.execute(statement)
    for statement in CLEANUP_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    # Part two first, then part one.
    for statement in CLEANUP_DOWNGRADE:
        op.execute(statement)
    # Dropping the table drops its indexes, policy, trigger, and grants.
    op.drop_table("sandbox_starts")
