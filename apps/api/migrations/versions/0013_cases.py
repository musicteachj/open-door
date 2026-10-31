"""Add the case tables (Phase 6): a matter a person sends to HR, its summary, and its timeline.

Three tenant tables, each with row-level security enabled and forced and the one permissive
tenant_isolation rule:

  cases           the person's words (ciphertext under the case's own data key), its category, its
                  status, the date HR replies by, and the guard's verdict on the words. The API may
                  add a case and change only status and status_changed_at. Nothing is deleted.
  case_summaries  the AI's summary of a case, or the note that it could not write one. Insert-only.
  case_events     one step in a case's timeline. Insert-only, and it holds no text.

Who reads and changes what, by restrictive rules (they apply together with the tenant rule):
  cases           SELECT: the person who opened it, or HR. UPDATE: HR, and never their own case
                  (with no person set, nobody). INSERT: a person's own case, with status new; with
                  no person set (the seed), any case.
  case_summaries  SELECT: HR only.
  case_events     SELECT: HR only.
A person's insert of a summary or an event is a Core insert with no RETURNING, since Postgres checks
RETURNING against the SELECT rule and the person cannot read the row they wrote.

Triggers (plpgsql, the caller's rights, a pinned search_path, EXECUTE revoked from PUBLIC, as in
0008 and 0009):
  cases status        new -> in_review -> closed, or new -> closed, and nothing else (SQLSTATE
                      OD004, a code of its own so the service can tell a refused move from any
                      other change). It stamps status_changed_at with the database's clock.
  case_summaries      code running as anyone but HR may add a summary only to their own case, and
                      only in its first 10 minutes, so it cannot replace what HR sees later. HR may
                      add any number (a retry adds a row, and the newest counts).
  clocks              whenever a person is set (the person, or HR), a BEFORE INSERT trigger on each
                      table writes the database's clock over created_at and status_changed_at
                      (cases), created_at (case_summaries), and occurred_at (case_events), so
                      code running as the person cannot choose when a row was written: that would
                      move the 10-minute window, or make a forged summary the newest. With no
                      person set the supplied times stay, so the seed can backdate.
  case_events         code running as anyone but HR may add only `opened`, `summary_written`, and
                      `summary_failed`, to their own case, in their own name or the system's (no
                      actor). `viewed`, `text_read`, and `status_changed` are HR's, so the person
                      cannot forge HR's reading or a decision.
All the insert rules and triggers let an insert through when no person is set
(app.current_person_id() is null). The sandbox seed writes cases from people who aren't the visitor,
with backdated summaries and HR's `text_read`, and clears app.person_id around that block. The HR
flag alone is not a bypass for anything but what HR may do anyway, and no person set is not HR.

One summary per case from anyone but HR: "the case has no summary yet" cannot be read by a trigger
that runs as the person, because case_summaries is HR's alone to read. So the trigger stamps
written_by_hr from the transaction's HR flag, whatever the insert says, but only on someone else's
case: HR on their own case is held to the person's rules (one summary, in the first 10 minutes).
A partial unique index on (tenant_id, case_id) where it is false allows one such row. A second one
is a unique violation (23505), not an OD003. It also holds HR's rows on other people's cases apart:
HR's retry never counts against the person's first summary. Rows written with no person set (the
seed) count as not by HR.

The key from a case to its turn is (tenant_id, turn_id, person_id) against ai_turns, and a second
one (tenant_id, conversation_id, person_id) against ai_conversations, because Postgres checks a
foreign key without row-level security and so a plain key would let one person name another's turn.
Both columns are null for a case sent from "My cases", which skips the keys, and a check holds that
both are set or both are null. Two unique indexes start with tenant_id: one per (person, submission
ID), so a double click makes one case, and a partial one per (person, turn), so a turn opens one
case. person_id is in both, so a clash tells no one that someone else's turn or submission has a
case.

audit_events gains a restrictive SELECT rule: rows with target `case` are HR's alone, and
`escalation.offered` rows go to their actor or HR. Until now any transaction in the sandbox could
read any audit row. Inserts are untouched, but Postgres checks RETURNING against the SELECT rule, so
record_event now makes the row's ID itself and asks for nothing back.

ai_spend.turn_id becomes nullable and the table gains `purpose` (turn, case_screen, case_summary),
not null and defaulting to turn so every existing row keeps its meaning. A check holds that a turn's
row has its turn. A case's rows carry no case ID and no turn, so the sandbox-wide ledger tells no
one which case was screened or summarized. ai_spend_daily has no per-call detail to change, only a
day, a kind, and an amount; the daily cap sums those, so it already counts every purpose.

The downgrade deletes the non-turn spending rows first, because turn_id goes back to not null. Row
level security is forced on ai_spend, and under FORCE even a non-superuser owner's DELETE sees no
rows, so the delete runs between NO FORCE and FORCE (as 0012 does for tenants). It drops the three
tables with their rules and triggers, and the audit rule. The case rows go with them and cannot be
restored.

app/db/models.py describes the same tables, and `alembic check` keeps the two in step (it doesn't
compare the policies, the grants, the triggers, or the checks, which tests cover).

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-27
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | Sequence[str] | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CASE_TABLES = ("cases", "case_summaries", "case_events")

CATEGORIES = "'harassment_discrimination', 'safety', 'medical_accommodation', 'pay', 'other'"
STATUSES = "'new', 'in_review', 'closed'"

# Policies call the functions as (SELECT ...), so Postgres evaluates them once per query.
ROW_LEVEL_SECURITY = (
    *(
        statement
        for table in CASE_TABLES
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
    # The person who opened a case, and HR, read it. Reads only, so seeding can still insert.
    """
    CREATE POLICY case_opener_or_hr ON cases AS RESTRICTIVE FOR SELECT TO od_app
        USING (person_id = (SELECT app.current_person_id()) OR (SELECT app.current_is_hr()))
    """,
    # HR changes a case, and never their own. With no person set the comparison is null, so the
    # HR flag alone changes nothing (the seed never updates a case).
    """
    CREATE POLICY case_hr_not_own ON cases AS RESTRICTIVE FOR UPDATE TO od_app
        USING ((SELECT app.current_is_hr())
               AND person_id <> (SELECT app.current_person_id()))
        WITH CHECK ((SELECT app.current_is_hr())
                    AND person_id <> (SELECT app.current_person_id()))
    """,
    # A person opens only their own case, and a new one: not one in someone else's name, and not
    # one that starts closed. With no person set (the seed) any case goes in.
    """
    CREATE POLICY case_insert_own_new ON cases AS RESTRICTIVE FOR INSERT TO od_app
        WITH CHECK (
            (SELECT app.current_person_id()) IS NULL
            OR (person_id = (SELECT app.current_person_id()) AND status = 'new')
        )
    """,
    """
    CREATE POLICY summary_hr_only ON case_summaries AS RESTRICTIVE FOR SELECT TO od_app
        USING ((SELECT app.current_is_hr()))
    """,
    """
    CREATE POLICY event_hr_only ON case_events AS RESTRICTIVE FOR SELECT TO od_app
        USING ((SELECT app.current_is_hr()))
    """,
    # Case rows are HR's alone, and an offer to talk to HR is its actor's and HR's. Every other
    # audit row stays open to the sandbox, as before. A null target_type is not a case.
    """
    CREATE POLICY case_audit_hr_only ON audit_events AS RESTRICTIVE FOR SELECT TO od_app
        USING (
            (SELECT app.current_is_hr())
            OR (
                target_type IS DISTINCT FROM 'case'
                AND (
                    action <> 'escalation.offered'
                    OR actor_person_id = (SELECT app.current_person_id())
                )
            )
        )
    """,
)

# Insert-only, except a case's status. Never DELETE or TRUNCATE (which ignores row-level security),
# and nothing for od_cleanup: the rows go with their sandbox. The test_grants exact-grants test
# lists the same.
UPDATABLE_CASE_COLUMNS = ("status", "status_changed_at")
GRANTS = (
    "GRANT SELECT, INSERT ON cases, case_summaries, case_events TO od_app",
    f"GRANT UPDATE ({', '.join(UPDATABLE_CASE_COLUMNS)}) ON cases TO od_app",
)

# Like 0008's finished-turn trigger, these run as the caller (not SECURITY DEFINER), and each
# function's search_path is pinned so that no other schema can supply the names it uses. That is why
# a table is named public.cases below. A trigger function needs no EXECUTE for the role that fires
# it, so EXECUTE is revoked from PUBLIC and nobody can call it.
STATUS_TRIGGER = (
    """
    CREATE FUNCTION app.enforce_case_status() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path = pg_catalog, pg_temp
    AS $$
    BEGIN
        IF NOT (
            (OLD.status = 'new' AND NEW.status IN ('in_review', 'closed'))
            OR (OLD.status = 'in_review' AND NEW.status = 'closed')
        ) THEN
            RAISE EXCEPTION 'a case cannot change from % to %', OLD.status, NEW.status
                USING ERRCODE = 'OD004';
        END IF;
        -- The server's clock, whatever the statement says.
        NEW.status_changed_at := pg_catalog.now();
        RETURN NEW;
    END
    $$
    """,
    """
    CREATE TRIGGER enforce_case_status BEFORE UPDATE ON cases
        FOR EACH ROW EXECUTE FUNCTION app.enforce_case_status()
    """,
    "REVOKE EXECUTE ON FUNCTION app.enforce_case_status() FROM PUBLIC",
)

CASE_CLOCK_TRIGGER = (
    """
    CREATE FUNCTION app.stamp_case_clock() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path = pg_catalog, pg_temp
    AS $$
    BEGIN
        -- A new case is created and in its first status at the same moment. With no person set,
        -- the seed's own times stay.
        IF app.current_person_id() IS NOT NULL THEN
            NEW.created_at := pg_catalog.now();
            NEW.status_changed_at := pg_catalog.now();
        END IF;
        RETURN NEW;
    END
    $$
    """,
    """
    CREATE TRIGGER stamp_case_clock BEFORE INSERT ON cases
        FOR EACH ROW EXECUTE FUNCTION app.stamp_case_clock()
    """,
    "REVOKE EXECUTE ON FUNCTION app.stamp_case_clock() FROM PUBLIC",
)

SUMMARY_TRIGGER = (
    """
    CREATE FUNCTION app.enforce_case_summary_insert() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path = pg_catalog, pg_temp
    AS $$
    DECLARE
        case_person uuid;
        case_created timestamptz;
    BEGIN
        SELECT c.person_id, c.created_at INTO case_person, case_created
            FROM public.cases c
            WHERE c.tenant_id = NEW.tenant_id AND c.id = NEW.case_id;
        -- The database's word, not the statement's. HR's flag counts only on someone else's case:
        -- on their own case HR is held to the person's rules (one summary, first 10 minutes), so
        -- the unique index below applies to them too.
        NEW.written_by_hr := app.current_is_hr()
            AND case_person IS DISTINCT FROM app.current_person_id();
        IF app.current_person_id() IS NOT NULL THEN
            NEW.created_at := pg_catalog.now();
        END IF;
        -- HR on another person's case, and the seed (no person set), may add any summary.
        IF NEW.written_by_hr OR app.current_person_id() IS NULL THEN
            RETURN NEW;
        END IF;
        IF case_person IS DISTINCT FROM app.current_person_id() THEN
            RAISE EXCEPTION 'a summary can be added only to your own case'
                USING ERRCODE = 'OD003';
        END IF;
        IF case_created < pg_catalog.now() - interval '10 minutes' THEN
            RAISE EXCEPTION 'a summary can be added to your own case only in its first 10 minutes'
                USING ERRCODE = 'OD003';
        END IF;
        RETURN NEW;
    END
    $$
    """,
    """
    CREATE TRIGGER enforce_case_summary_insert BEFORE INSERT ON case_summaries
        FOR EACH ROW EXECUTE FUNCTION app.enforce_case_summary_insert()
    """,
    "REVOKE EXECUTE ON FUNCTION app.enforce_case_summary_insert() FROM PUBLIC",
)

EVENT_TRIGGER = (
    """
    CREATE FUNCTION app.enforce_case_event_insert() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path = pg_catalog, pg_temp
    AS $$
    DECLARE
        case_person uuid;
    BEGIN
        IF app.current_person_id() IS NOT NULL THEN
            NEW.occurred_at := pg_catalog.now();
        END IF;
        -- HR, and the seed (no person set), may add any event.
        IF app.current_is_hr() OR app.current_person_id() IS NULL THEN
            RETURN NEW;
        END IF;
        IF NEW.kind NOT IN ('opened', 'summary_written', 'summary_failed') THEN
            RAISE EXCEPTION 'only HR adds a % event', NEW.kind USING ERRCODE = 'OD003';
        END IF;
        IF NEW.actor_person_id IS NOT NULL
            AND NEW.actor_person_id <> app.current_person_id()
        THEN
            RAISE EXCEPTION 'an event cannot be added in someone else''s name'
                USING ERRCODE = 'OD003';
        END IF;
        SELECT c.person_id INTO case_person
            FROM public.cases c
            WHERE c.tenant_id = NEW.tenant_id AND c.id = NEW.case_id;
        IF case_person IS DISTINCT FROM app.current_person_id() THEN
            RAISE EXCEPTION 'an event can be added only to your own case' USING ERRCODE = 'OD003';
        END IF;
        RETURN NEW;
    END
    $$
    """,
    """
    CREATE TRIGGER enforce_case_event_insert BEFORE INSERT ON case_events
        FOR EACH ROW EXECUTE FUNCTION app.enforce_case_event_insert()
    """,
    "REVOKE EXECUTE ON FUNCTION app.enforce_case_event_insert() FROM PUBLIC",
)

# The downgrade's spending statements, run in this order. Row-level security is forced on ai_spend,
# and the delete must see the rows, so FORCE is lifted for it (the owner can always do that) and
# put back after. Alembic runs the whole migration in one transaction, and Postgres DDL is
# transactional, so a failure in between rolls back the NO FORCE too: FORCE cannot be left off.
DOWNGRADE_SPENDING = (
    "ALTER TABLE ai_spend NO FORCE ROW LEVEL SECURITY",
    "DELETE FROM ai_spend WHERE purpose <> 'turn'",
    "ALTER TABLE ai_spend FORCE ROW LEVEL SECURITY",
    "ALTER TABLE ai_spend DROP CONSTRAINT ck_ai_spend_turn_has_its_turn",
    "ALTER TABLE ai_spend DROP CONSTRAINT ck_ai_spend_purpose",
    "ALTER TABLE ai_spend DROP COLUMN purpose",
    "ALTER TABLE ai_spend ALTER COLUMN turn_id SET NOT NULL",
)


def tenant_column() -> sa.Column[Any]:
    return sa.Column("tenant_id", sa.Uuid(), nullable=False)


def id_column() -> sa.Column[Any]:
    return sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def tenant_foreign_key(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["tenant_id"],
        ["tenants.id"],
        name=op.f(f"fk_{table}_tenant_id_tenants"),
        ondelete="CASCADE",
    )


def now_column(name: str) -> sa.Column[Any]:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "cases",
        id_column(),
        tenant_column(),
        sa.Column("person_id", sa.Uuid(), nullable=False),
        sa.Column("submission_id", sa.Uuid(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="new", nullable=False),
        now_column("status_changed_at"),
        now_column("created_at"),
        sa.Column("reply_by", sa.Date(), nullable=False),
        sa.Column("screening", sa.Text(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("turn_id", sa.Uuid(), nullable=True),
        sa.Column("key_id", sa.Text(), nullable=False),
        sa.Column("wrapped_key", sa.LargeBinary(), nullable=False),
        sa.Column("text_ciphertext", sa.LargeBinary(), nullable=False),
        sa.CheckConstraint(f"category IN ({CATEGORIES})", name=op.f("ck_cases_category")),
        sa.CheckConstraint(f"status IN ({STATUSES})", name=op.f("ck_cases_status")),
        sa.CheckConstraint(
            "screening IN ('ordinary', 'sensitive', 'crisis', 'unscreened')",
            name=op.f("ck_cases_screening"),
        ),
        sa.CheckConstraint(
            "(turn_id IS NULL) = (conversation_id IS NULL)",
            name=op.f("ck_cases_turn_and_conversation"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "person_id"],
            ["people.tenant_id", "people.id"],
            name=op.f("fk_cases_tenant_id_person_id_people"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "turn_id", "person_id"],
            ["ai_turns.tenant_id", "ai_turns.id", "ai_turns.person_id"],
            name="fk_cases_turn_owner",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "conversation_id", "person_id"],
            ["ai_conversations.tenant_id", "ai_conversations.id", "ai_conversations.person_id"],
            name="fk_cases_conversation_owner",
        ),
        tenant_foreign_key("cases"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cases")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_cases_tenant_id_id")),
        sa.UniqueConstraint(
            "tenant_id",
            "person_id",
            "submission_id",
            name=op.f("uq_cases_tenant_id_person_id_submission_id"),
        ),
    )
    op.create_index(
        "uq_cases_tenant_id_person_id_turn_id",
        "cases",
        ["tenant_id", "person_id", "turn_id"],
        unique=True,
        postgresql_where=sa.text("turn_id IS NOT NULL"),
    )
    op.create_index(
        op.f("ix_cases_tenant_id_status_created_at"),
        "cases",
        ["tenant_id", "status", "created_at"],
    )
    op.create_table(
        "case_summaries",
        id_column(),
        tenant_column(),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("prompt_version", sa.Text(), nullable=True),
        now_column("created_at"),
        sa.Column("written_by_hr", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.CheckConstraint(
            "status IN ('written', 'failed')", name=op.f("ck_case_summaries_status")
        ),
        sa.CheckConstraint(
            "reason IS NULL OR reason IN ('transport', 'refusal', 'timeout', 'budget', 'checks',"
            " 'crisis', 'unscreened')",
            name=op.f("ck_case_summaries_reason"),
        ),
        sa.CheckConstraint(
            "(status = 'written' AND ciphertext IS NOT NULL AND reason IS NULL)"
            " OR (status = 'failed' AND ciphertext IS NULL AND reason IS NOT NULL)",
            name=op.f("ck_case_summaries_outcome"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "case_id"],
            ["cases.tenant_id", "cases.id"],
            name=op.f("fk_case_summaries_tenant_id_case_id_cases"),
        ),
        tenant_foreign_key("case_summaries"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_case_summaries")),
    )
    op.create_index(
        "uq_case_summaries_one_not_by_hr_per_case",
        "case_summaries",
        ["tenant_id", "case_id"],
        unique=True,
        postgresql_where=sa.text("NOT written_by_hr"),
    )
    op.create_index(
        op.f("ix_case_summaries_tenant_id_case_id_created_at"),
        "case_summaries",
        ["tenant_id", "case_id", "created_at"],
    )
    op.create_table(
        "case_events",
        id_column(),
        tenant_column(),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("actor_person_id", sa.Uuid(), nullable=True),
        now_column("occurred_at"),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("from_status", sa.Text(), nullable=True),
        sa.Column("to_status", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "kind IN ('opened', 'summary_written', 'summary_failed', 'viewed', 'text_read',"
            " 'status_changed')",
            name=op.f("ck_case_events_kind"),
        ),
        sa.CheckConstraint(f"from_status IN ({STATUSES})", name=op.f("ck_case_events_from_status")),
        sa.CheckConstraint(f"to_status IN ({STATUSES})", name=op.f("ck_case_events_to_status")),
        sa.CheckConstraint(
            "(kind = 'status_changed' AND from_status IS NOT NULL AND to_status IS NOT NULL)"
            " OR (kind <> 'status_changed' AND from_status IS NULL AND to_status IS NULL)",
            name=op.f("ck_case_events_statuses_only_on_a_change"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "case_id"],
            ["cases.tenant_id", "cases.id"],
            name=op.f("fk_case_events_tenant_id_case_id_cases"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "actor_person_id"],
            ["people.tenant_id", "people.id"],
            name=op.f("fk_case_events_tenant_id_actor_person_id_people"),
        ),
        tenant_foreign_key("case_events"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_case_events")),
    )
    op.create_index(
        op.f("ix_case_events_tenant_id_case_id_occurred_at"),
        "case_events",
        ["tenant_id", "case_id", "occurred_at"],
    )
    op.create_index(
        op.f("ix_case_events_tenant_id_actor_person_id"),
        "case_events",
        ["tenant_id", "actor_person_id"],
    )

    # The sandbox's budget ledger: a case's rows have no turn.
    op.add_column(
        "ai_spend",
        sa.Column("purpose", sa.Text(), server_default="turn", nullable=False),
    )
    op.alter_column("ai_spend", "turn_id", existing_type=sa.Uuid(), nullable=True)
    op.create_check_constraint(
        op.f("ck_ai_spend_purpose"),
        "ai_spend",
        "purpose IN ('turn', 'case_screen', 'case_summary')",
    )
    op.create_check_constraint(
        op.f("ck_ai_spend_turn_has_its_turn"),
        "ai_spend",
        "purpose <> 'turn' OR turn_id IS NOT NULL",
    )

    for statement in (
        *ROW_LEVEL_SECURITY,
        *GRANTS,
        *STATUS_TRIGGER,
        *CASE_CLOCK_TRIGGER,
        *SUMMARY_TRIGGER,
        *EVENT_TRIGGER,
    ):
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP POLICY case_audit_hr_only ON audit_events")
    for statement in DOWNGRADE_SPENDING:
        op.execute(statement)
    # Dropping a table drops its triggers, policies, indexes, and grants.
    for table in reversed(CASE_TABLES):
        op.drop_table(table)
    for function in (
        "enforce_case_event_insert",
        "enforce_case_summary_insert",
        "stamp_case_clock",
        "enforce_case_status",
    ):
        op.execute(f"DROP FUNCTION app.{function}()")
