"""Add the assistant's tables: conversations, messages, turns, feedback, and the budget ledgers.

Five are tenant tables, with row-level security enabled and forced and the usual tenant_isolation
policy. Four of them belong to one person (ai_conversations, ai_messages, ai_turns, ai_feedback)
and carry a second, RESTRICTIVE policy, own_rows: a row is visible, and writable, only when its
person_id is the person the transaction is scoped to. HR is no exception in Phase 4. The rule
covers writes too, so no one can add a row for someone else. It is restrictive, like
private_self_or_hr, because the row-level security test allows only the tenant rule as a
permissive policy: permissive policies are ORed, and one extra would widen what a tenant sees.

ai_spend has no person_id, and own_rows does not apply to it. It is the sandbox's budget ledger, and
the cap is the whole sandbox's, so the sum must cover every person's spending. It has the tenant
rule only. A known consequence: its turn_id column lets people in one sandbox see each other's turn
IDs and the timing of their calls, though never a question or an answer. A sandbox is one visitor
playing fictional personas, so that is accepted. No route may ever return ai_spend rows.

ai_spend_daily has no tenant_id and sits outside row-level security, like the handbook tables: it
holds a UTC day, a kind, and an amount, so every sandbox's spending can be summed into the demo's
daily cap. It holds no personal data. Both ledgers refuse nonsense amounts, because one negative
daily row would reset the shared cap: a `reserve` is never negative, and no amount is beyond
plus or minus 10. A single call's worst case is under $1 (8,000 output tokens at $20 per million
is $0.16, plus the input), so 10 is far above anything real and still stops a runaway or hostile
row. A `settle` row is the actual cost minus the reservation, so it can be negative. In
ai_spend_daily a BEFORE INSERT trigger (0003's app.stamp_tenant_created_at, reused: it only sets
created_at to now()) overrides created_at, `day` defaults to the current UTC date, and a check ties
the two together, so a row can't be forward-dated, and only a `settle` may be back-dated, by one
day, so it can land on the day of the reservation it settles across midnight.

The plus or minus 10 bound is per row, so a writer with direct database access could insert many
rows. That is accepted: the API is the only writer.

The API's grants are the least that works. Everything is insert-only except ai_turns, which is
added as `running` and may change only while it runs. The update grant is per column, and names
only the outcome and trace columns: id, tenant_id, person_id, conversation_id, question, and
started_at can never be updated. A BEFORE UPDATE trigger, app.refuse_finished_turn_update, then
raises SQLSTATE OD002 (a custom code, like 0005's OD001) when the row's status is anything but
`running`, so a finished turn is frozen and the code can tell that refusal from any other. The
trigger is written like 0003's created_at trigger: the caller's rights, a pinned search_path. A
turn changes only while it is running, through finish_turn (once, at its end; a stopped turn's
partial answer is written then) and recover_abandoned (which marks an abandoned one `failed`); once
it has ended, the trigger freezes it. Nothing is deleted: a sandbox's rows
go with its tenant (ON DELETE CASCADE, which runs as the table owner), so od_cleanup needs no grant.

Every key that points at a person's conversation or turn carries person_id as well as tenant_id, so
it has three columns where the earlier tables' keys have two. Postgres checks a foreign key without
row-level security, so a plain (tenant_id, conversation_id) key would let one person add a turn to
another person's conversation if they knew its random ID. The three-column key makes that fail.
The keys are named by hand, because the naming convention would make them longer than Postgres's
63-character limit.

ai_messages.content is `json`, not `jsonb`. Postgres keeps `json` as the exact text it was given,
and `jsonb` reorders keys and drops whitespace. The model's thinking blocks are signed over their
exact bytes, and the API refuses a history whose thinking blocks differ from what it sent, so the
stored messages must come back unchanged. The other JSON columns are for display and tracing, and
use `jsonb`.

ai_messages.sources is a nullable `jsonb` list with one entry per `search_result` block in that
message, in block order, written in the same INSERT as the message: the section ID, the passage IDs
of each text block, the title, the group name, the audience label, the last-updated date, and the
deep link. The block's own text can't give those back reliably, and the conversation's list of
search sources must include blocks in messages of turns that later failed or were stopped, whose
ai_turns trace is never filled in.

ai_turns holds the turn's status and its trace, which Phase 7's console reads as they are:
  status                  running, completed, stopped, failed, crisis, or guard_unavailable
  error_code              set when status is failed
  answer_text, citations  what the person sees after a reload; a stopped turn keeps its partial text
  guard_verdict           the guard's verdict (null if the guard did not run)
  tool_calls              [{name, inputSummary, ok, durationMs}] in call order
  sections_retrieved      [{sectionId, passageIds}] that the search tool returned
  served_by_models        the model IDs that served the turn; more than one after a fallback
  effort, prompt_version, toolset_version
  input_tokens, output_tokens, cache_read_tokens, cache_write_tokens
  cost_usd                the turn's cost at list price, guard included
  first_event_ms          start of the turn to the first event the person could see
  total_ms                start of the turn to its end
  refusal, fallback, injection_suspected

Stored unencrypted in Phase 4, questions and answers the guard flagged included; Phase 6 encrypts
case narratives and flagged content together. docs/DATA-INVENTORY.md says so.

app/db/models.py describes the same tables, and `alembic check` keeps the two in step (it doesn't
compare the policies or the grants, which tests cover).

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-14
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_TABLES = ("ai_conversations", "ai_turns", "ai_messages", "ai_feedback", "ai_spend")
# The tables a person owns. ai_spend is the sandbox's, and ai_spend_daily is global.
PERSON_TABLES = ("ai_conversations", "ai_turns", "ai_messages", "ai_feedback")

# Created in this order, dropped in reverse: a table comes after the ones its keys point at.
ALL_TABLES = (*TENANT_TABLES, "ai_spend_daily")

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
    *(
        f"""
        CREATE POLICY own_rows ON {table} AS RESTRICTIVE FOR ALL TO od_app
            USING (person_id = (SELECT app.current_person_id()))
            WITH CHECK (person_id = (SELECT app.current_person_id()))
        """
        for table in PERSON_TABLES
    ),
)

# The columns of a turn that change while it runs. The test_grants exact-grants test lists the same.
UPDATABLE_TURN_COLUMNS = (
    "status",
    "error_code",
    "ended_at",
    "answer_text",
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
)

# Insert-only, except a running turn's update, per column. Never DELETE or TRUNCATE (which ignores
# row-level security), and nothing for od_cleanup.
GRANTS = (
    "GRANT SELECT, INSERT ON ai_conversations, ai_messages, ai_turns, ai_feedback, ai_spend,"
    " ai_spend_daily TO od_app",
    f"GRANT UPDATE ({', '.join(UPDATABLE_TURN_COLUMNS)}) ON ai_turns TO od_app",
)

# A finished turn is frozen. Like 0003's created_at trigger, this runs as the caller (not SECURITY
# DEFINER), and its search_path is pinned so that no other schema can supply the names it uses.
FINISHED_TURN_TRIGGER = (
    """
    CREATE FUNCTION app.refuse_finished_turn_update() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path = pg_catalog, pg_temp
    AS $$
    BEGIN
        IF OLD.status <> 'running' THEN
            RAISE EXCEPTION 'a finished turn cannot be changed' USING ERRCODE = 'OD002';
        END IF;
        RETURN NEW;
    END
    $$
    """,
    """
    CREATE TRIGGER refuse_finished_turn_update BEFORE UPDATE ON ai_turns
        FOR EACH ROW EXECUTE FUNCTION app.refuse_finished_turn_update()
    """,
    # A trigger function needs no EXECUTE for the role that fires it, so nobody can call it.
    "REVOKE EXECUTE ON FUNCTION app.refuse_finished_turn_update() FROM PUBLIC",
)

# ai_spend_daily.created_at is the server's clock, whatever an insert says. The function is 0003's.
DAILY_CREATED_AT_TRIGGER = """
    CREATE TRIGGER stamp_created_at BEFORE INSERT ON ai_spend_daily
        FOR EACH ROW EXECUTE FUNCTION app.stamp_tenant_created_at()
"""


def tenant_column() -> sa.Column[Any]:
    return sa.Column("tenant_id", sa.Uuid(), nullable=False)


def id_column() -> sa.Column[Any]:
    return sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def created_at_column() -> sa.Column[Any]:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def tenant_foreign_key(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["tenant_id"],
        ["tenants.id"],
        name=op.f(f"fk_{table}_tenant_id_tenants"),
        ondelete="CASCADE",
    )


def upgrade() -> None:
    op.create_table(
        "ai_conversations",
        id_column(),
        tenant_column(),
        sa.Column("person_id", sa.Uuid(), nullable=False),
        created_at_column(),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("guard_model", sa.Text(), nullable=False),
        sa.Column("effort", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("toolset_version", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "person_id"],
            ["people.tenant_id", "people.id"],
            name=op.f("fk_ai_conversations_tenant_id_person_id_people"),
        ),
        tenant_foreign_key("ai_conversations"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_conversations")),
        sa.UniqueConstraint(
            "tenant_id", "id", "person_id", name=op.f("uq_ai_conversations_tenant_id_id_person_id")
        ),
    )
    op.create_index(
        op.f("ix_ai_conversations_tenant_id_person_id_created_at"),
        "ai_conversations",
        ["tenant_id", "person_id", "created_at"],
    )
    op.create_table(
        "ai_turns",
        id_column(),
        tenant_column(),
        sa.Column("person_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("answer_text", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column(
            "citations",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
        sa.Column("guard_verdict", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "tool_calls",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
        sa.Column(
            "sections_retrieved",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
        sa.Column(
            "served_by_models",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column("effort", sa.Text(), nullable=True),
        sa.Column("prompt_version", sa.Text(), nullable=True),
        sa.Column("toolset_version", sa.Text(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("output_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("cache_read_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("cache_write_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("cost_usd", sa.Numeric(12, 6), server_default=sa.text("0"), nullable=False),
        sa.Column("first_event_ms", sa.Integer(), nullable=True),
        sa.Column("total_ms", sa.Integer(), nullable=True),
        sa.Column("refusal", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("fallback", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("injection_suspected", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'stopped', 'failed', 'crisis',"
            " 'guard_unavailable')",
            name=op.f("ck_ai_turns_status"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "conversation_id", "person_id"],
            ["ai_conversations.tenant_id", "ai_conversations.id", "ai_conversations.person_id"],
            name="fk_ai_turns_conversation_owner",
        ),
        tenant_foreign_key("ai_turns"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_turns")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_ai_turns_tenant_id_id")),
        sa.UniqueConstraint(
            "tenant_id", "id", "person_id", name=op.f("uq_ai_turns_tenant_id_id_person_id")
        ),
    )
    op.create_index(
        op.f("ix_ai_turns_tenant_id_conversation_id_started_at"),
        "ai_turns",
        ["tenant_id", "conversation_id", "started_at"],
    )
    op.create_index(
        "uq_ai_turns_one_running_per_conversation",
        "ai_turns",
        ["tenant_id", "conversation_id"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
    )
    op.create_table(
        "ai_messages",
        id_column(),
        tenant_column(),
        sa.Column("person_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("turn_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("sources", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        created_at_column(),
        sa.CheckConstraint(
            "role IN ('user', 'assistant', 'system')", name=op.f("ck_ai_messages_role")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "conversation_id", "person_id"],
            ["ai_conversations.tenant_id", "ai_conversations.id", "ai_conversations.person_id"],
            name="fk_ai_messages_conversation_owner",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "turn_id", "person_id"],
            ["ai_turns.tenant_id", "ai_turns.id", "ai_turns.person_id"],
            name="fk_ai_messages_turn_owner",
        ),
        tenant_foreign_key("ai_messages"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_messages")),
        sa.UniqueConstraint(
            "tenant_id",
            "conversation_id",
            "position",
            name=op.f("uq_ai_messages_tenant_id_conversation_id_position"),
        ),
    )
    # For the foreign key to the turn: deleting a turn looks here for messages that refer to it.
    op.create_index(
        op.f("ix_ai_messages_tenant_id_turn_id"), "ai_messages", ["tenant_id", "turn_id"]
    )
    op.create_table(
        "ai_feedback",
        id_column(),
        tenant_column(),
        sa.Column("person_id", sa.Uuid(), nullable=False),
        sa.Column("turn_id", sa.Uuid(), nullable=False),
        sa.Column("helpful", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        created_at_column(),
        sa.CheckConstraint("char_length(reason) <= 500", name=op.f("ck_ai_feedback_reason_length")),
        sa.ForeignKeyConstraint(
            ["tenant_id", "turn_id", "person_id"],
            ["ai_turns.tenant_id", "ai_turns.id", "ai_turns.person_id"],
            name="fk_ai_feedback_turn_owner",
        ),
        tenant_foreign_key("ai_feedback"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_feedback")),
        sa.UniqueConstraint("tenant_id", "turn_id", name=op.f("uq_ai_feedback_tenant_id_turn_id")),
    )
    op.create_table(
        "ai_spend",
        id_column(),
        tenant_column(),
        sa.Column("turn_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("amount_usd", sa.Numeric(12, 6), nullable=False),
        created_at_column(),
        sa.CheckConstraint("kind IN ('reserve', 'settle')", name=op.f("ck_ai_spend_kind")),
        sa.CheckConstraint(
            "kind <> 'reserve' OR amount_usd >= 0", name=op.f("ck_ai_spend_reserve_not_negative")
        ),
        sa.CheckConstraint("amount_usd BETWEEN -10 AND 10", name=op.f("ck_ai_spend_amount_range")),
        sa.ForeignKeyConstraint(
            ["tenant_id", "turn_id"],
            ["ai_turns.tenant_id", "ai_turns.id"],
            name="fk_ai_spend_turn",
        ),
        tenant_foreign_key("ai_spend"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_spend")),
    )
    # The sandbox's sum under the budget lock uses the prefix (tenant_id). The whole index serves
    # the foreign key to the turn: deleting a turn looks here for rows that refer to it.
    op.create_index(op.f("ix_ai_spend_tenant_id_turn_id"), "ai_spend", ["tenant_id", "turn_id"])
    op.create_table(
        "ai_spend_daily",
        id_column(),
        sa.Column(
            "day",
            sa.Date(),
            server_default=sa.text("(now() AT TIME ZONE 'UTC')::date"),
            nullable=False,
        ),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("amount_usd", sa.Numeric(12, 6), nullable=False),
        created_at_column(),
        sa.CheckConstraint("kind IN ('reserve', 'settle')", name=op.f("ck_ai_spend_daily_kind")),
        sa.CheckConstraint(
            "kind <> 'reserve' OR amount_usd >= 0",
            name=op.f("ck_ai_spend_daily_reserve_not_negative"),
        ),
        sa.CheckConstraint(
            "amount_usd BETWEEN -10 AND 10", name=op.f("ck_ai_spend_daily_amount_range")
        ),
        # A reserve is pinned to today. A settle may also land on yesterday: a reservation made at
        # 23:59:59 and settled at 00:00:05 belongs to the day it was reserved on, and forcing the
        # settle onto the new day would credit it with yesterday's unused reservation, which errs
        # toward spending more.
        sa.CheckConstraint(
            "day = (created_at AT TIME ZONE 'UTC')::date"
            " OR (kind = 'settle' AND day = (created_at AT TIME ZONE 'UTC')::date - 1)",
            name=op.f("ck_ai_spend_daily_day_matches_created_at"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_spend_daily")),
    )
    op.create_index(op.f("ix_ai_spend_daily_day"), "ai_spend_daily", ["day"])
    for statement in (
        *ROW_LEVEL_SECURITY,
        *GRANTS,
        *FINISHED_TURN_TRIGGER,
        DAILY_CREATED_AT_TRIGGER,
    ):
        op.execute(statement)


def downgrade() -> None:
    # The trigger goes with its table; the function it calls is ours to drop, and is not 0003's.
    # Dropping a table also drops its indexes, policies, triggers, and grants. Children go first.
    for table in reversed(ALL_TABLES):
        op.drop_table(table)
    op.execute("DROP FUNCTION app.refuse_finished_turn_update()")
