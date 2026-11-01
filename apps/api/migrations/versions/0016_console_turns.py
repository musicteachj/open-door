"""Add the console's table (Phase 7): one row for each finished turn, with no person in it.

`ai_console_turns` is what HR's AI Ops console reads. It is written by the transaction that finishes
a turn (or that marks one abandoned), as labels copied from the turn: the asker's role and
location, the outcome, the safety check's verdict, tool names and durations, handbook section IDs,
the card's action, the model and versions, tokens, cost, and three timings. See ADR 0016.

  - No person ID, no conversation ID, no name, and no text, on any row. There is no foreign key to
    ai_turns either: nothing in the database links a console row to the person's turn rows. The
    row's turn_id is the API's own lookup key and is null on a flagged row.
  - abandoned is true only on the row written when a turn's process died before it stored a
    verdict. Such a row is always flagged (a check constraint says so), so it is redacted like
    one, but it is a turn that died and not an escalation. It names no one.
  - A flagged turn (the safety check said sensitive or crisis, an HR panel showed, or the turn was
    abandoned and so stored no verdict) is redacted when it is written: only its date, tokens,
    cost, timings, and the model's labels remain. A turn with no verdict for another reason (the
    safety check was unavailable or errored, or the budget stopped it first) is a normal timed
    row. A check constraint refuses a flagged row that holds anything more, so no later code can
    write one. An unflagged row must be complete, and its verdict, if any, ordinary.
  - Row-level security is enabled and forced. The permissive rule is the tenant rule. A restrictive
    SELECT rule admits HR only (the shape of 0013's summary_hr_only), so the person who asked, a
    manager, and an HR session without the flag read nothing. The rule is for SELECT only, so the
    person's own finishing transaction inserts under the tenant rule. That insert is a Core insert
    with no RETURNING, because Postgres checks RETURNING against the SELECT rule.
  - The API's login may SELECT and INSERT. No UPDATE, DELETE, or TRUNCATE, and nothing for the
    cleanup login: the rows go with their sandbox (ON DELETE CASCADE from tenants).

No SECURITY DEFINER anywhere, as in every migration since 0002.

occurred_on is the date in Denver HQ's time zone (America/Denver), the one calendar the sandbox
uses for dates that must be the same for everyone.

app/db/models.py describes the same table, and `alembic check` keeps the two in step (it doesn't
compare the policies, the grants, or the check expressions, which tests cover).

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-31
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016"
down_revision: str | Sequence[str] | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OUTCOMES = "'answered', 'not_found', 'refused', 'stopped', 'failed', 'budget', 'guard_unavailable'"
ROLES = "'employee', 'manager', 'hr'"
ACTIONS = "'timeoff.request', 'timeoff.decide', 'timeoff.cancel'"

# Every column that a flagged row must leave null.
REDACTED_ON_A_FLAGGED_ROW = (
    "turn_id",
    "occurred_at",
    "asker_role",
    "asker_location",
    "outcome",
    "refusal_category",
    "guard_category",
    "injection_suspected",
    "tools",
    "sections_retrieved",
    "sections_cited",
    "card_action",
)
# The columns that make an unflagged row complete.
REQUIRED_ON_AN_UNFLAGGED_ROW = (
    "turn_id",
    "occurred_at",
    "asker_role",
    "asker_location",
    "outcome",
    "injection_suspected",
    "tools",
    "sections_retrieved",
    "sections_cited",
)
NON_NEGATIVE = (
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "cost_usd",
    "guard_ms",
    "first_text_ms",
    "total_ms",
)

ROW_LEVEL_SECURITY = (
    "ALTER TABLE ai_console_turns ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE ai_console_turns FORCE ROW LEVEL SECURITY",
    # Policies call the functions as (SELECT ...), so Postgres evaluates them once per query.
    """
    CREATE POLICY tenant_isolation ON ai_console_turns FOR ALL TO od_app
        USING (tenant_id = (SELECT app.current_tenant_id()))
        WITH CHECK (tenant_id = (SELECT app.current_tenant_id()))
    """,
    # Only HR reads, whoever asked. Reads only, so the person's own turn can still insert.
    """
    CREATE POLICY console_hr_only ON ai_console_turns AS RESTRICTIVE FOR SELECT TO od_app
        USING ((SELECT app.current_is_hr()))
    """,
)

# Insert-only. Never UPDATE, DELETE, or TRUNCATE (which ignores row-level security), and nothing
# for od_cleanup: the rows go with their sandbox. The test_grants exact-grants test lists the same.
GRANTS = ("GRANT SELECT, INSERT ON ai_console_turns TO od_app",)


def count_column(name: str) -> sa.Column[Any]:
    return sa.Column(name, sa.Integer(), server_default=sa.text("0"), nullable=False)


def upgrade() -> None:
    redacted_are_null = " AND ".join(f"{name} IS NULL" for name in REDACTED_ON_A_FLAGGED_ROW)
    required = " AND ".join(f"{name} IS NOT NULL" for name in REQUIRED_ON_AN_UNFLAGGED_ROW)
    op.create_table(
        "ai_console_turns",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("turn_id", sa.Uuid(), nullable=True),
        sa.Column("occurred_on", sa.Date(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("flagged", sa.Boolean(), nullable=False),
        sa.Column("abandoned", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("asker_role", sa.Text(), nullable=True),
        sa.Column("asker_location", sa.Text(), nullable=True),
        sa.Column("outcome", sa.Text(), nullable=True),
        sa.Column("refusal_category", sa.Text(), nullable=True),
        sa.Column("guard_category", sa.Text(), nullable=True),
        sa.Column("injection_suspected", sa.Boolean(), nullable=True),
        sa.Column("tools", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("sections_retrieved", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("sections_cited", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("card_action", sa.Text(), nullable=True),
        sa.Column(
            "served_by",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column("fallback", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("effort", sa.Text(), nullable=True),
        sa.Column("prompt_version", sa.Text(), nullable=True),
        sa.Column("toolset_version", sa.Text(), nullable=True),
        count_column("input_tokens"),
        count_column("output_tokens"),
        count_column("cache_read_tokens"),
        count_column("cache_write_tokens"),
        sa.Column("cost_usd", sa.Numeric(12, 6), server_default=sa.text("0"), nullable=False),
        sa.Column("guard_ms", sa.Integer(), nullable=True),
        sa.Column("first_text_ms", sa.Integer(), nullable=True),
        sa.Column("total_ms", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            f"NOT flagged OR ({redacted_are_null})",
            name=op.f("ck_ai_console_turns_flagged_row_is_redacted"),
        ),
        sa.CheckConstraint(
            f"flagged OR ({required})",
            name=op.f("ck_ai_console_turns_unflagged_row_is_complete"),
        ),
        sa.CheckConstraint(
            "flagged OR guard_category IS NULL OR guard_category = 'ordinary'",
            name=op.f("ck_ai_console_turns_unflagged_row_is_ordinary"),
        ),
        sa.CheckConstraint(
            "NOT abandoned OR flagged", name=op.f("ck_ai_console_turns_abandoned_row_is_flagged")
        ),
        sa.CheckConstraint(
            "refusal_category IS NULL OR refusal_category ~ '^[A-Za-z][A-Za-z0-9_-]{0,39}$'",
            name=op.f("ck_ai_console_turns_refusal_category_is_a_word"),
        ),
        sa.CheckConstraint(f"outcome IN ({OUTCOMES})", name=op.f("ck_ai_console_turns_outcome")),
        sa.CheckConstraint(f"asker_role IN ({ROLES})", name=op.f("ck_ai_console_turns_asker_role")),
        sa.CheckConstraint(
            f"card_action IN ({ACTIONS})", name=op.f("ck_ai_console_turns_card_action")
        ),
        sa.CheckConstraint(
            " AND ".join(f"({name} IS NULL OR {name} >= 0)" for name in NON_NEGATIVE),
            name=op.f("ck_ai_console_turns_counts_not_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_ai_console_turns_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_console_turns")),
    )
    # The turn list: newest day first, a day's timed rows newest first, then its flagged rows.
    op.create_index(
        "ix_ai_console_turns_tenant_id_occurred_on_occurred_at_id",
        "ai_console_turns",
        [
            "tenant_id",
            sa.text("occurred_on DESC"),
            sa.text("occurred_at DESC NULLS LAST"),
            "id",
        ],
    )
    for statement in (*ROW_LEVEL_SECURITY, *GRANTS):
        op.execute(statement)


def downgrade() -> None:
    # Dropping a table drops its policies, indexes, and grants.
    op.drop_table("ai_console_turns")
