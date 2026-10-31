"""Hold the events the person may add to a case to the same limits as the summary (Phase 6).

Migration 0013 let code running as the person (no HR flag) add the kinds `opened`,
`summary_written`, and `summary_failed` to their own case with no limit on time or number, while
the summary itself is held to one per case in the case's first 10 minutes. So that code could put
a `summary_failed` or a second `opened` on HR's timeline days later. No real path does that: the
open transaction writes `opened` (and, for a crisis or unscreened case, `summary_failed`) when the
case is made, the first summary job writes one `summary_written` or `summary_failed` in the first
10 minutes, and HR's retry runs with the HR flag.

What changes, for a session without the HR flag:

  - every event is added only in the case's first 10 minutes (the window the summary rule uses)
  - at most one `opened` and at most one summary event (`summary_written` or `summary_failed`) per
    case. The person cannot read the timeline, so a trigger cannot count rows; instead each row
    carries `written_by_hr`, stamped by the trigger the way 0013 stamps the summary's: true only
    for HR acting on a case that is not their own (HR on their own case is held to the person's
    rules, and the seed, which sets no person, is not HR). Two partial unique indexes cover the
    rows where it is false. HR's retries on other people's cases are unlimited.

The refusal is SQLSTATE OD003 like the other insert refusals; a second event is the unique
index's own error (23505), as with the second summary.

It also adds the index that serves the retry throttle: a partial index on the audit rows of
summary retries, read under the case's row lock. It is partial so that every other audit insert
does not maintain it.

Existing rows: `written_by_hr` follows the trigger for every kind: true on a row whose actor is set
and is someone other than the case's person (HR on another's case), false otherwise. Of the three
kinds the person may add, every later row of each group per case is also set true, so the unique
indexes can be built. The backfill runs between NO FORCE and FORCE ROW LEVEL SECURITY on
`case_events` and `cases` (see BACKFILL_STATEMENTS).

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | Sequence[str] | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EVENT_TRIGGER = """
    CREATE OR REPLACE FUNCTION app.enforce_case_event_insert() RETURNS trigger
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
        -- The database's word, not the statement's, and the same rule as the summary's (0013):
        -- HR's flag counts only on someone else's case. On their own case HR is held to the
        -- person's rules. The seed (no person set) is not HR, so its rows are not by HR either.
        NEW.written_by_hr := app.current_is_hr()
            AND case_person IS DISTINCT FROM app.current_person_id();
        IF app.current_person_id() IS NOT NULL THEN
            NEW.occurred_at := pg_catalog.now();
        END IF;
        -- HR on another person's case, and the seed (no person set), may add any event.
        IF NEW.written_by_hr OR app.current_person_id() IS NULL THEN
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
        IF case_person IS DISTINCT FROM app.current_person_id() THEN
            RAISE EXCEPTION 'an event can be added only to your own case' USING ERRCODE = 'OD003';
        END IF;
        IF case_created < pg_catalog.now() - interval '10 minutes' THEN
            RAISE EXCEPTION 'an event can be added to your own case only in its first 10 minutes'
                USING ERRCODE = 'OD003';
        END IF;
        RETURN NEW;
    END
    $$
"""

# The 0013 body, for the downgrade.
OLD_EVENT_TRIGGER = """
    CREATE OR REPLACE FUNCTION app.enforce_case_event_insert() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path = pg_catalog, pg_temp
    AS $$
    DECLARE
        case_person uuid;
    BEGIN
        IF app.current_person_id() IS NOT NULL THEN
            NEW.occurred_at := pg_catalog.now();
        END IF;
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
"""

# Rows made before this migration get the trigger's definition of `written_by_hr` for every kind:
# true when the actor is set and is not the case's person (HR on another's case), false otherwise.
# Of the three kinds the person may add, all but the oldest of each group count as HR's too, so the
# unique indexes can be built.
BACKFILL = """
    UPDATE case_events e SET written_by_hr = true
    FROM (
        SELECT ev.id,
            (ev.actor_person_id IS NOT NULL
                AND ev.actor_person_id IS DISTINCT FROM c.person_id) AS by_other,
            (ev.kind IN ('opened', 'summary_written', 'summary_failed')) AS limited,
            row_number() OVER (
                PARTITION BY ev.tenant_id, ev.case_id, (ev.kind = 'opened'),
                    (ev.kind IN ('opened', 'summary_written', 'summary_failed'))
                ORDER BY (ev.actor_person_id IS NOT NULL
                    AND ev.actor_person_id IS DISTINCT FROM c.person_id), ev.occurred_at, ev.id
            ) AS position
        FROM case_events ev
        JOIN cases c ON c.tenant_id = ev.tenant_id AND c.id = ev.case_id
    ) ranked
    WHERE e.id = ranked.id AND (ranked.by_other OR (ranked.limited AND ranked.position > 1))
"""

# Row-level security is forced on both tables and its policies name only od_app, so under FORCE a
# non-superuser owner's UPDATE (and its read of cases) sees no rows. The backfill runs between NO
# FORCE and FORCE, which the owner can always do (as 0011, 0012, and 0013 do). DDL is
# transactional, so a failure in between rolls back the NO FORCE too: FORCE cannot be left off.
BACKFILL_STATEMENTS: tuple[str, ...] = (
    "ALTER TABLE case_events NO FORCE ROW LEVEL SECURITY",
    "ALTER TABLE cases NO FORCE ROW LEVEL SECURITY",
    BACKFILL,
    "ALTER TABLE case_events FORCE ROW LEVEL SECURITY",
    "ALTER TABLE cases FORCE ROW LEVEL SECURITY",
)


def upgrade() -> None:
    op.add_column(
        "case_events",
        sa.Column("written_by_hr", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    for statement in BACKFILL_STATEMENTS:
        op.execute(statement)
    op.create_index(
        "uq_case_events_one_opened_not_by_hr_per_case",
        "case_events",
        ["tenant_id", "case_id"],
        unique=True,
        postgresql_where=sa.text("kind = 'opened' AND NOT written_by_hr"),
    )
    op.create_index(
        "uq_case_events_one_summary_not_by_hr_per_case",
        "case_events",
        ["tenant_id", "case_id"],
        unique=True,
        postgresql_where=sa.text(
            "kind IN ('summary_written', 'summary_failed') AND NOT written_by_hr"
        ),
    )
    op.execute(EVENT_TRIGGER)
    op.create_index(
        "ix_audit_events_target_action",
        "audit_events",
        ["tenant_id", "target_id", "occurred_at"],
        postgresql_where=sa.text("action = 'case.summary.retried'"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_audit_events_target_action",
        table_name="audit_events",
    )
    op.execute(OLD_EVENT_TRIGGER)
    op.drop_index("uq_case_events_one_summary_not_by_hr_per_case", table_name="case_events")
    op.drop_index("uq_case_events_one_opened_not_by_hr_per_case", table_name="case_events")
    op.drop_column("case_events", "written_by_hr")
