"""Pin each new sandbox to the newest published handbook version, in the database.

A BEFORE INSERT trigger on tenants sets `handbook_version_id` to the newest published version and
overrides any value the caller supplied, so a sandbox can't be pinned to a draft or an old version
by a bug or a crafted insert. With no published version it raises SQLSTATE OD001 (a custom code),
which the sandbox service turns into a 503 problem. Like the trigger that stamps `created_at`
(migration 0003), the function runs as the caller (not SECURITY DEFINER), so it needs only the
SELECT that the API's login already has on handbook_versions, and its search_path is pinned so no
other schema can supply the names it uses. The column stays nullable: sandboxes created before
migration 0004 have no version.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-12
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Names are schema-qualified because the search_path is pinned to pg_catalog.
PIN_FUNCTION = """
    CREATE FUNCTION app.pin_tenant_handbook_version() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path = pg_catalog, pg_temp
    AS $$
    BEGIN
        SELECT v.id INTO NEW.handbook_version_id
        FROM public.handbook_versions v
        WHERE v.published_at IS NOT NULL
        ORDER BY v.published_at DESC, v.created_at DESC, v.id DESC
        LIMIT 1;
        IF NEW.handbook_version_id IS NULL THEN
            RAISE EXCEPTION 'No published handbook version' USING ERRCODE = 'OD001';
        END IF;
        RETURN NEW;
    END
    $$
"""
PIN_TRIGGER = """
    CREATE TRIGGER pin_handbook_version BEFORE INSERT ON tenants
        FOR EACH ROW EXECUTE FUNCTION app.pin_tenant_handbook_version()
"""


# A trigger function needs no EXECUTE for the role whose insert fires it, so revoking the default
# grant to PUBLIC breaks nothing and stops anyone calling it directly. The same goes for migration
# 0003's trigger function, which 0005 also revokes (and its downgrade restores).
REVOKE_STAMP = "REVOKE EXECUTE ON FUNCTION app.stamp_tenant_created_at() FROM PUBLIC"
GRANT_STAMP = "GRANT EXECUTE ON FUNCTION app.stamp_tenant_created_at() TO PUBLIC"
REVOKE_PIN = "REVOKE EXECUTE ON FUNCTION app.pin_tenant_handbook_version() FROM PUBLIC"


def upgrade() -> None:
    op.execute(PIN_FUNCTION)
    op.execute(REVOKE_PIN)
    op.execute(PIN_TRIGGER)
    op.execute(REVOKE_STAMP)


def downgrade() -> None:
    op.execute(GRANT_STAMP)
    op.execute("DROP TRIGGER pin_handbook_version ON tenants")
    op.execute("DROP FUNCTION app.pin_tenant_handbook_version()")
