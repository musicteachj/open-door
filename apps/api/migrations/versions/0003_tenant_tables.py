"""Create the Phase 1 tables, with row-level security, their policies, and the roles' grants.

Every table except tenants and sessions is a tenant table: row-level security is enabled and
forced, and the tenant_isolation policy shows od_app only the rows of the tenant its transaction
is scoped to. app/db/models.py describes the same tables, and `alembic check` keeps the two in step
(it doesn't compare the policies, the grants, or the trigger below, which tests cover).

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_TABLES = ("locations", "departments", "people", "person_private", "holidays", "audit_events")

# Created in this order, dropped in reverse.
ALL_TABLES = (
    "tenants",
    "locations",
    "departments",
    "people",
    "person_private",
    "holidays",
    "sessions",
    "audit_events",
)

# The ck_tenants_lifetime check compares expires_at with created_at, so a created_at the caller
# picks would defeat it. This trigger overwrites it with the current time on every insert. Postgres
# runs BEFORE triggers ahead of constraint checks. The function runs as the caller (not SECURITY
# DEFINER), and its search_path is pinned so that no other schema can supply the names it uses.
CREATED_AT_TRIGGER = (
    """
    CREATE FUNCTION app.stamp_tenant_created_at() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path = pg_catalog, pg_temp
    AS $$
    BEGIN
        NEW.created_at := pg_catalog.now();
        RETURN NEW;
    END
    $$
    """,
    """
    CREATE TRIGGER stamp_created_at BEFORE INSERT ON tenants
        FOR EACH ROW EXECUTE FUNCTION app.stamp_tenant_created_at()
    """,
)

# Policies call the functions as (SELECT ...), so Postgres evaluates them once per query, not once
# per row.
ROW_LEVEL_SECURITY = (
    *(
        statement
        for table in TENANT_TABLES
        for statement in (
            f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
            f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
            f"""
            CREATE POLICY tenant_isolation ON {table} FOR ALL TO od_app
                USING (tenant_id = (SELECT app.current_tenant_id()))
                WITH CHECK (tenant_id = (SELECT app.current_tenant_id()))
            """,
        )
    ),
    "ALTER TABLE tenants ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE tenants FORCE ROW LEVEL SECURITY",
    """
    CREATE POLICY tenant_self ON tenants FOR ALL TO od_app
        USING (id = (SELECT app.current_tenant_id()))
        WITH CHECK (id = (SELECT app.current_tenant_id()))
    """,
    # Scoped TO od_cleanup, so the API never inherits them.
    """
    CREATE POLICY cleanup_select ON tenants FOR SELECT TO od_cleanup
        USING (expires_at < now())
    """,
    """
    CREATE POLICY cleanup_delete ON tenants FOR DELETE TO od_cleanup
        USING (expires_at < now())
    """,
    # A second, restrictive rule: a private-details row is visible only to its person and to HR.
    # It covers reads only, so seeding can still insert the rows.
    """
    CREATE POLICY private_self_or_hr ON person_private AS RESTRICTIVE FOR SELECT TO od_app
        USING (person_id = (SELECT app.current_person_id()) OR (SELECT app.current_is_hr()))
    """,
)

# No UPDATE anywhere yet; later phases add exactly what they need. Never TRUNCATE, which ignores
# row-level security, and never REFERENCES or TRIGGER.
GRANTS = (
    "GRANT SELECT, INSERT ON tenants, locations, departments, people, person_private, holidays,"
    " audit_events TO od_app",
    "GRANT SELECT, INSERT, DELETE ON sessions TO od_app",
    "GRANT SELECT, DELETE ON tenants TO od_cleanup",
)


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("anchor_date", sa.Date(), nullable=False),
        sa.CheckConstraint(
            "expires_at <= created_at + interval '25 hours'", name=op.f("ck_tenants_lifetime")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenants")),
    )
    op.create_table(
        "locations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("city", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("timezone", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_locations_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_locations")),
        sa.UniqueConstraint("tenant_id", "code", name=op.f("uq_locations_tenant_id_code")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_locations_tenant_id_id")),
    )
    op.create_table(
        "departments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_departments_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_departments")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_departments_tenant_id_id")),
        sa.UniqueConstraint("tenant_id", "name", name=op.f("uq_departments_tenant_id_name")),
    )
    op.create_table(
        "people",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("given_name", sa.Text(), nullable=False),
        sa.Column("family_name", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("department_id", sa.Uuid(), nullable=False),
        sa.Column("location_id", sa.Uuid(), nullable=False),
        sa.Column("manager_id", sa.Uuid(), nullable=True),
        sa.Column("work_email", sa.Text(), nullable=False),
        sa.Column("employment_type", sa.Text(), nullable=False),
        sa.Column("hire_date", sa.Date(), nullable=False),
        sa.Column("is_hr_admin", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("persona_key", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "employment_type IN ('salaried', 'hourly')",
            name=op.f("ck_people_employment_type"),
        ),
        sa.CheckConstraint(
            "persona_key IN ('priya', 'mateo', 'marcus', 'dana')",
            name=op.f("ck_people_persona_key"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "department_id"],
            ["departments.tenant_id", "departments.id"],
            name=op.f("fk_people_tenant_id_department_id_departments"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "location_id"],
            ["locations.tenant_id", "locations.id"],
            name=op.f("fk_people_tenant_id_location_id_locations"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "manager_id"],
            ["people.tenant_id", "people.id"],
            name=op.f("fk_people_tenant_id_manager_id_people"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_people_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_people")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_people_tenant_id_id")),
        sa.UniqueConstraint(
            "tenant_id", "persona_key", name=op.f("uq_people_tenant_id_persona_key")
        ),
        sa.UniqueConstraint("tenant_id", "work_email", name=op.f("uq_people_tenant_id_work_email")),
    )
    op.create_index(
        op.f("ix_people_tenant_id_family_name_given_name_id"),
        "people",
        ["tenant_id", "family_name", "given_name", "id"],
    )
    op.create_index(op.f("ix_people_tenant_id_manager_id"), "people", ["tenant_id", "manager_id"])
    op.create_table(
        "person_private",
        sa.Column("person_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("personal_email", sa.Text(), nullable=False),
        sa.Column("phone", sa.Text(), nullable=False),
        sa.Column("home_address", sa.Text(), nullable=False),
        sa.Column("date_of_birth", sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "person_id"],
            ["people.tenant_id", "people.id"],
            name=op.f("fk_person_private_tenant_id_person_id_people"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_person_private_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("person_id", name=op.f("pk_person_private")),
    )
    op.create_index(
        op.f("ix_person_private_tenant_id_person_id"),
        "person_private",
        ["tenant_id", "person_id"],
    )
    op.create_table(
        "holidays",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("location_id", sa.Uuid(), nullable=False),
        sa.Column("holiday_date", sa.Date(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "location_id"],
            ["locations.tenant_id", "locations.id"],
            name=op.f("fk_holidays_tenant_id_location_id_locations"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_holidays_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_holidays")),
        sa.UniqueConstraint(
            "tenant_id",
            "location_id",
            "holiday_date",
            name=op.f("uq_holidays_tenant_id_location_id_holiday_date"),
        ),
    )
    op.create_table(
        "sessions",
        sa.Column("token_hash", sa.LargeBinary(), nullable=False),
        sa.Column("csrf_hash", sa.LargeBinary(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("person_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "octet_length(csrf_hash) = 32", name=op.f("ck_sessions_csrf_hash_is_sha256")
        ),
        sa.CheckConstraint(
            "octet_length(token_hash) = 32", name=op.f("ck_sessions_token_hash_is_sha256")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "person_id"],
            ["people.tenant_id", "people.id"],
            name=op.f("fk_sessions_tenant_id_person_id_people"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_sessions_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("token_hash", name=op.f("pk_sessions")),
    )
    op.create_index(op.f("ix_sessions_tenant_id_person_id"), "sessions", ["tenant_id", "person_id"])
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("actor_person_id", sa.Uuid(), nullable=True),
        sa.Column("via", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("target_type", sa.Text(), nullable=True),
        sa.Column("target_id", sa.Uuid(), nullable=True),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("proposal_id", sa.Uuid(), nullable=True),
        sa.Column("request_id", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "via IN ('ui', 'assistant', 'system')", name=op.f("ck_audit_events_via")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "actor_person_id"],
            ["people.tenant_id", "people.id"],
            name=op.f("fk_audit_events_tenant_id_actor_person_id_people"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_audit_events_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    op.create_index(
        op.f("ix_audit_events_tenant_id_actor_person_id"),
        "audit_events",
        ["tenant_id", "actor_person_id"],
    )
    op.create_index(
        op.f("ix_audit_events_tenant_id_occurred_at"),
        "audit_events",
        ["tenant_id", "occurred_at"],
    )
    for statement in (*CREATED_AT_TRIGGER, *ROW_LEVEL_SECURITY, *GRANTS):
        op.execute(statement)


def downgrade() -> None:
    # The trigger goes before its function, which it depends on. The function lives in the app
    # schema, which migration 0002 drops, so it has to be gone first.
    op.execute("DROP TRIGGER stamp_created_at ON tenants")
    op.execute("DROP FUNCTION app.stamp_tenant_created_at()")
    # Dropping a table also drops its indexes, policies, and grants.
    for table in reversed(ALL_TABLES):
        op.drop_table(table)
