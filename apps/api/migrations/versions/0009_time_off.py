"""Add time off: a person's schedule, opening balances, requests, and the assistant's proposals.

Three new tenant tables, with row-level security enabled and forced and the usual tenant_isolation
policy: time_off_openings, time_off_requests, and ai_proposals. Only ai_proposals belongs to one
person and carries the second, RESTRICTIVE policy, own_rows, exactly as 0008's person tables do: a
proposal is visible, and writable, only to the person it was made for, HR included. The two
time-off tables have the tenant rule only, because a manager reads a report's requests and HR reads
everyone's. The policy layer (app/policy) decides who reads which. own_rows is restrictive for the
reason 0008 gives: the row-level security test allows only the tenant rule as a permissive policy.

people.scheduled_weekdays is a smallint[] of ISO weekdays (1 is Monday, 7 is Sunday) that the
person works. A check refuses an empty list and any value outside 1 to 7. The column keeps its
default of {1,2,3,4,5} on purpose: it gives every sandbox that exists when this migration runs a
Monday to Friday week, so the time-off engine has a schedule to count against, and an insert that
says nothing still gets one. The seed (a later stage) writes every person's days explicitly, so
the default is a fallback and not how the demo company gets its schedules.

time_off_openings holds one row per person: the PTO balance on `as_of` (in minutes), which the
engine counts forward from. A person's balance is worked out on every read, never stored (ADR 0012).

time_off_requests holds both kinds of request. A PTO request goes pending, then approved, denied,
or canceled. A sick request is only ever recorded, and then perhaps canceled: sick leave needs no
approval. The checks hold the same rules the engine does, so a bug in the service can't store a
row the engine would refuse:
  type and status are known, a PTO request is never `recorded`, and a sick one is only `recorded`
  or `canceled`
  the range is in order and at most 31 days (the engine's limit)
  partial_minutes is null, or the request is for one day and the amount is what the engine allows:
  4 hours for PTO, a whole number of hours from 1 to 8 for sick leave
  amount_minutes is positive
  the decision columns fit the status: pending and recorded have none, approved and denied have
  who and when, and canceled has when it was canceled (and who decided, if it was approved first)
  decision_note is a denial's alone, and at most 300 characters. It is text a person wrote, shown
  on pages and cards and never sent to a model
  proposal_id is set exactly when the request was made through the assistant
  nobody decides their own request: decided_by is never the request's own person. The policy layer
  and the service refuse it first, and this check is the backstop that holds even if both are wrong
A unique index lets one proposal make at most one request (where proposal_id is set), so a
confirm that runs twice, or two proposals' worth of requests from one, can't store a second row.
An exclusion constraint refuses two open requests (pending, approved, or recorded) for one person
whose days overlap. The engine checks first, so a person sees the friendly reason; the constraint
catches two requests that race. It needs the btree_gist extension, which lets a gist index compare
the uuid columns with `=` beside the date range. btree_gist is a trusted extension, so the owner
role can create it without being a superuser. The downgrade leaves it in place. 0001 also says
IF NOT EXISTS, but its downgrade drops `vector`, which it created for the handbook. This one leaves
`btree_gist`, because a downgrade can't tell whether it made the extension or found it already
there. Dropping something that may predate the migration is the worse mistake, and leaving it does
no harm.

ai_proposals is what the assistant writes when it wants something done: the action, the validated
input (payload), and the card the person is shown. The model proposes and never writes; a person
confirms, and the server re-validates and runs the stored payload once. Its status goes from
`pending` to one final status (executed, failed, canceled, or expired), and `ended_at` is set
exactly when it is not pending. The proposal's clock is the database's, so a caller can't stretch
it: a BEFORE INSERT trigger stamps `created_at` with now() (0003's app.stamp_tenant_created_at,
reused, because it does only that), and a check holds `expires_at` to at most 15 minutes after it
(and after it, not at it). A second BEFORE INSERT trigger, app.enforce_proposal_insert, refuses a
proposal that isn't born pending, with no `ended_at` and no `outcome`, so no row can start life
already executed. The update trigger sets `ended_at` to now() on the move from pending, whatever
the statement says, and refuses a move to `executed` after `expires_at` ("an expired proposal
cannot be executed"). A move to expired, canceled, or failed after expiry stays allowed. now() is
the start of the transaction, so a confirm that began before the expiry may finish after it.

The API's grants are the least that works. Everything is insert-only except two update grants, one
per column list. A request may change only its status, the decision columns, and canceled_at. A
proposal may change only its status, ended_at, and outcome. The type, the dates, the amount, the
person, the origin, the payload, the card, and the expiry can never be updated. Each table has a
BEFORE UPDATE trigger, written like 0008's finished-turn trigger (the caller's rights, a pinned
search_path, EXECUTE revoked from PUBLIC), that raises SQLSTATE OD003, a custom code like 0005's
OD001 and 0008's OD002, so the code can tell this refusal from any other:
  a request moves pending to approved, denied, or canceled, approved to canceled, or recorded to
  canceled, and nothing else: not out of denied or canceled, and not to the status it has
  decided_by, decided_at, and decision_note change only on pending to approved or denied (on
  approved to canceled they must stay as they were), and canceled_at only on a move to canceled
  a proposal moves from pending to one final status, and a final one never changes. It cannot be
  executed once expired, and its ended_at is the database's clock
Both tables share OD003 because both refuse the same thing, a change that isn't planned. So does
the insert trigger on proposals.
Nothing is deleted: a sandbox's rows go with its tenant (ON DELETE CASCADE, which runs as the table
owner), so od_cleanup needs no grant.

Every key that points at a person's conversation, turn, or proposal carries person_id as well as
tenant_id, as 0008's do, because Postgres checks a foreign key without row-level security. A
proposal's conversation must be its own person's, and its turn must be in that conversation and be
that person's, which needs a new unique constraint on ai_turns over (tenant_id, id,
conversation_id, person_id). A request's proposal must be its own person's. The keys are named by
hand where the naming convention would pass Postgres's 63-character limit.

audit_events.proposal_id has had no foreign key since 0003. It now points at ai_proposals through
(tenant_id, proposal_id), so an event can name only a proposal of its own sandbox. Deleting a
tenant deletes audit_events and ai_proposals in one statement, and a NO ACTION key is checked at
the end of the statement, after both are gone, so the cascade works (as it does for 0008's turns
and messages). The test that deletes a sandbox as the cleanup login covers it. An index on
(tenant_id, proposal_id) serves the key: each deleted proposal looks there for events that name it.

A request's proposal key is served by the unique index on (tenant_id, proposal_id): deleting a
proposal looks there for the request that names it.

app/db/models.py describes the same tables, and `alembic check` keeps the two in step (it doesn't
compare the policies, the grants, the triggers, or the checks, which tests cover).

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-21
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_TABLES = ("ai_proposals", "time_off_openings", "time_off_requests")
# The tables a person owns. The two time-off tables are the sandbox's: the policy layer decides who
# reads which.
PERSON_TABLES = ("ai_proposals",)

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

# The columns that change after a request or a proposal is added. The test_grants exact-grants test
# lists the same.
UPDATABLE_REQUEST_COLUMNS = ("status", "decided_by", "decided_at", "decision_note", "canceled_at")
UPDATABLE_PROPOSAL_COLUMNS = ("status", "ended_at", "outcome")

# Insert-only, except the per-column updates. Never DELETE or TRUNCATE (which ignores row-level
# security), and nothing for od_cleanup.
GRANTS = (
    "GRANT SELECT, INSERT ON time_off_openings, time_off_requests, ai_proposals TO od_app",
    f"GRANT UPDATE ({', '.join(UPDATABLE_REQUEST_COLUMNS)}) ON time_off_requests TO od_app",
    f"GRANT UPDATE ({', '.join(UPDATABLE_PROPOSAL_COLUMNS)}) ON ai_proposals TO od_app",
)

# Like 0008's finished-turn trigger, these run as the caller (not SECURITY DEFINER), and each
# function's search_path is pinned so that no other schema can supply the names it uses.
REQUEST_TRIGGER = (
    """
    CREATE FUNCTION app.enforce_time_off_request_update() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path = pg_catalog, pg_temp
    AS $$
    BEGIN
        IF NOT (
            (OLD.status = 'pending' AND NEW.status IN ('approved', 'denied', 'canceled'))
            OR (OLD.status IN ('approved', 'recorded') AND NEW.status = 'canceled')
        ) THEN
            RAISE EXCEPTION 'a time-off request cannot change from % to %', OLD.status, NEW.status
                USING ERRCODE = 'OD003';
        END IF;
        IF (NEW.decided_by, NEW.decided_at, NEW.decision_note)
                IS DISTINCT FROM (OLD.decided_by, OLD.decided_at, OLD.decision_note)
            AND NOT (OLD.status = 'pending' AND NEW.status IN ('approved', 'denied'))
        THEN
            RAISE EXCEPTION 'the decision on a time-off request is written only when it is decided'
                USING ERRCODE = 'OD003';
        END IF;
        IF NEW.canceled_at IS DISTINCT FROM OLD.canceled_at AND NEW.status <> 'canceled' THEN
            RAISE EXCEPTION 'canceled_at is written only when a time-off request is canceled'
                USING ERRCODE = 'OD003';
        END IF;
        RETURN NEW;
    END
    $$
    """,
    """
    CREATE TRIGGER enforce_time_off_request_update BEFORE UPDATE ON time_off_requests
        FOR EACH ROW EXECUTE FUNCTION app.enforce_time_off_request_update()
    """,
    # A trigger function needs no EXECUTE for the role that fires it, so nobody can call it.
    "REVOKE EXECUTE ON FUNCTION app.enforce_time_off_request_update() FROM PUBLIC",
)

PROPOSAL_TRIGGER = (
    """
    CREATE FUNCTION app.enforce_proposal_update() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path = pg_catalog, pg_temp
    AS $$
    BEGIN
        IF OLD.status <> 'pending'
            OR NEW.status NOT IN ('executed', 'failed', 'canceled', 'expired')
        THEN
            RAISE EXCEPTION 'a proposal cannot change from % to %', OLD.status, NEW.status
                USING ERRCODE = 'OD003';
        END IF;
        IF NEW.status = 'executed' AND pg_catalog.now() > OLD.expires_at THEN
            RAISE EXCEPTION 'an expired proposal cannot be executed' USING ERRCODE = 'OD003';
        END IF;
        -- The server's clock, not the caller's. Only a move out of pending reaches this line.
        NEW.ended_at := pg_catalog.now();
        RETURN NEW;
    END
    $$
    """,
    """
    CREATE TRIGGER enforce_proposal_update BEFORE UPDATE ON ai_proposals
        FOR EACH ROW EXECUTE FUNCTION app.enforce_proposal_update()
    """,
    "REVOKE EXECUTE ON FUNCTION app.enforce_proposal_update() FROM PUBLIC",
    # A proposal is born pending: no row may start in a final status, ended, or with an outcome.
    # Postgres runs BEFORE triggers ahead of the checks, so these refuse first, with OD003.
    """
    CREATE FUNCTION app.enforce_proposal_insert() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path = pg_catalog, pg_temp
    AS $$
    BEGIN
        IF NEW.status <> 'pending' OR NEW.ended_at IS NOT NULL OR NEW.outcome IS NOT NULL THEN
            RAISE EXCEPTION 'a proposal must be pending when it is created'
                USING ERRCODE = 'OD003';
        END IF;
        RETURN NEW;
    END
    $$
    """,
    """
    CREATE TRIGGER enforce_proposal_insert BEFORE INSERT ON ai_proposals
        FOR EACH ROW EXECUTE FUNCTION app.enforce_proposal_insert()
    """,
    "REVOKE EXECUTE ON FUNCTION app.enforce_proposal_insert() FROM PUBLIC",
    # created_at is the database's now(), so the 15-minute check below can't be dodged by
    # backdating it. 0003's function only sets created_at, which is all this table needs.
    """
    CREATE TRIGGER stamp_created_at BEFORE INSERT ON ai_proposals
        FOR EACH ROW EXECUTE FUNCTION app.stamp_tenant_created_at()
    """,
)

OPEN_STATUSES = "status IN ('pending', 'approved', 'recorded')"


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
    # The exclusion constraint on requests needs it. Trusted, so the owner role may create it.
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    op.add_column(
        "people",
        sa.Column(
            "scheduled_weekdays",
            postgresql.ARRAY(sa.SmallInteger()),
            server_default=sa.text("'{1,2,3,4,5}'"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f("ck_people_scheduled_weekdays"),
        "people",
        "cardinality(scheduled_weekdays) >= 1"
        " AND scheduled_weekdays <@ ARRAY[1, 2, 3, 4, 5, 6, 7]::smallint[]",
    )

    # A turn's key for the proposals that name it: the turn, its conversation, and its person.
    op.create_unique_constraint(
        op.f("uq_ai_turns_tenant_id_id_conversation_id_person_id"),
        "ai_turns",
        ["tenant_id", "id", "conversation_id", "person_id"],
    )

    op.create_table(
        "ai_proposals",
        id_column(),
        tenant_column(),
        sa.Column("person_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("turn_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("card", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        created_at_column(),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.CheckConstraint(
            "action IN ('timeoff.request', 'timeoff.decide', 'timeoff.cancel')",
            name=op.f("ck_ai_proposals_action"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'executed', 'failed', 'canceled', 'expired')",
            name=op.f("ck_ai_proposals_status"),
        ),
        sa.CheckConstraint(
            "(ended_at IS NULL) = (status = 'pending')",
            name=op.f("ck_ai_proposals_ended_at_matches_status"),
        ),
        sa.CheckConstraint(
            "expires_at > created_at", name=op.f("ck_ai_proposals_expires_after_created")
        ),
        sa.CheckConstraint(
            "expires_at <= created_at + interval '15 minutes'",
            name=op.f("ck_ai_proposals_expires_within_15_minutes"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "conversation_id", "person_id"],
            ["ai_conversations.tenant_id", "ai_conversations.id", "ai_conversations.person_id"],
            name="fk_ai_proposals_conversation_owner",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "turn_id", "conversation_id", "person_id"],
            ["ai_turns.tenant_id", "ai_turns.id", "ai_turns.conversation_id", "ai_turns.person_id"],
            name="fk_ai_proposals_turn_owner",
        ),
        tenant_foreign_key("ai_proposals"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_proposals")),
        # The target of the audit key, and of the request's key (with the person).
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_ai_proposals_tenant_id_id")),
        sa.UniqueConstraint(
            "tenant_id", "id", "person_id", name=op.f("uq_ai_proposals_tenant_id_id_person_id")
        ),
    )
    # A conversation's proposals, oldest first, and the first column pair of the conversation key.
    op.create_index(
        op.f("ix_ai_proposals_tenant_id_conversation_id_created_at"),
        "ai_proposals",
        ["tenant_id", "conversation_id", "created_at"],
    )
    # For the key to the turn: deleting a turn looks here for proposals that name it.
    op.create_index(
        op.f("ix_ai_proposals_tenant_id_turn_id"), "ai_proposals", ["tenant_id", "turn_id"]
    )

    op.create_table(
        "time_off_openings",
        id_column(),
        tenant_column(),
        sa.Column("person_id", sa.Uuid(), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("amount_minutes", sa.Integer(), nullable=False),
        created_at_column(),
        sa.CheckConstraint(
            "amount_minutes >= 0", name=op.f("ck_time_off_openings_amount_not_negative")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "person_id"],
            ["people.tenant_id", "people.id"],
            name=op.f("fk_time_off_openings_tenant_id_person_id_people"),
        ),
        tenant_foreign_key("time_off_openings"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_time_off_openings")),
        sa.UniqueConstraint(
            "tenant_id", "person_id", name=op.f("uq_time_off_openings_tenant_id_person_id")
        ),
    )

    op.create_table(
        "time_off_requests",
        id_column(),
        tenant_column(),
        sa.Column("person_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("partial_minutes", sa.Integer(), nullable=True),
        sa.Column("amount_minutes", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        created_at_column(),
        sa.Column("created_via", sa.Text(), nullable=False),
        sa.Column("proposal_id", sa.Uuid(), nullable=True),
        sa.Column("decided_by", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("type IN ('pto', 'sick')", name=op.f("ck_time_off_requests_type")),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'denied', 'recorded', 'canceled')",
            name=op.f("ck_time_off_requests_status"),
        ),
        sa.CheckConstraint(
            "created_via IN ('ui', 'assistant')", name=op.f("ck_time_off_requests_created_via")
        ),
        # Each half reads as "if it is this type, then...", so an unknown type passes here and
        # fails only the type check above.
        sa.CheckConstraint(
            "(type <> 'pto' OR status <> 'recorded')"
            " AND (type <> 'sick' OR status IN ('recorded', 'canceled'))",
            name=op.f("ck_time_off_requests_status_matches_type"),
        ),
        sa.CheckConstraint(
            "end_date >= start_date", name=op.f("ck_time_off_requests_dates_in_order")
        ),
        sa.CheckConstraint(
            "end_date - start_date <= 30", name=op.f("ck_time_off_requests_at_most_31_days")
        ),
        sa.CheckConstraint(
            "partial_minutes IS NULL OR (start_date = end_date AND ("
            "(type = 'pto' AND partial_minutes = 240)"
            " OR (type = 'sick' AND partial_minutes % 60 = 0"
            " AND partial_minutes BETWEEN 60 AND 480)))",
            name=op.f("ck_time_off_requests_partial_minutes_match_the_engine"),
        ),
        sa.CheckConstraint(
            "amount_minutes > 0", name=op.f("ck_time_off_requests_amount_is_positive")
        ),
        # Written as implications, one per status, so an unknown status passes here and fails only
        # the status check above.
        sa.CheckConstraint(
            "(status NOT IN ('pending', 'recorded') OR (decided_by IS NULL AND decided_at IS NULL"
            " AND decision_note IS NULL AND canceled_at IS NULL))"
            " AND (status NOT IN ('approved', 'denied') OR (decided_by IS NOT NULL"
            " AND decided_at IS NOT NULL AND canceled_at IS NULL))"
            " AND (status <> 'canceled' OR (canceled_at IS NOT NULL"
            " AND (decided_by IS NULL) = (decided_at IS NULL)))",
            name=op.f("ck_time_off_requests_decision_matches_status"),
        ),
        sa.CheckConstraint(
            "decision_note IS NULL OR (char_length(decision_note) <= 300 AND status = 'denied')",
            name=op.f("ck_time_off_requests_decision_note_is_a_short_denial_note"),
        ),
        sa.CheckConstraint(
            "(proposal_id IS NOT NULL) = (created_via = 'assistant')",
            name=op.f("ck_time_off_requests_proposal_matches_created_via"),
        ),
        # A null decided_by passes: the comparison is DISTINCT FROM, not <>.
        sa.CheckConstraint(
            "decided_by IS DISTINCT FROM person_id",
            name=op.f("ck_time_off_requests_no_self_decision"),
        ),
        # Two open requests for one person can't share a day. Both ends are inclusive, so the
        # range is closed on both sides. A canceled or denied request frees its days.
        postgresql.ExcludeConstraint(
            ("tenant_id", "="),
            ("person_id", "="),
            (sa.text("daterange(start_date, end_date, '[]')"), "&&"),
            using="gist",
            where=sa.text(OPEN_STATUSES),
            name="ex_time_off_requests_no_overlap",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "person_id"],
            ["people.tenant_id", "people.id"],
            name=op.f("fk_time_off_requests_tenant_id_person_id_people"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "decided_by"],
            ["people.tenant_id", "people.id"],
            name=op.f("fk_time_off_requests_tenant_id_decided_by_people"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "proposal_id", "person_id"],
            ["ai_proposals.tenant_id", "ai_proposals.id", "ai_proposals.person_id"],
            name="fk_time_off_requests_proposal_owner",
        ),
        tenant_foreign_key("time_off_requests"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_time_off_requests")),
    )
    # A person's requests by date, for their list and for the engine's read.
    op.create_index(
        op.f("ix_time_off_requests_tenant_id_person_id_start_date"),
        "time_off_requests",
        ["tenant_id", "person_id", "start_date"],
    )
    # For the key to the decider: deleting a person looks here.
    op.create_index(
        op.f("ix_time_off_requests_tenant_id_decided_by"),
        "time_off_requests",
        ["tenant_id", "decided_by"],
    )
    # Unique, so a proposal makes at most one request. It also serves the key to the proposal.
    op.create_index(
        op.f("uq_time_off_requests_tenant_id_proposal_id"),
        "time_off_requests",
        ["tenant_id", "proposal_id"],
        unique=True,
        postgresql_where=sa.text("proposal_id IS NOT NULL"),
    )

    op.create_foreign_key(
        op.f("fk_audit_events_tenant_id_proposal_id_ai_proposals"),
        "audit_events",
        "ai_proposals",
        ["tenant_id", "proposal_id"],
        ["tenant_id", "id"],
    )
    # For that key: deleting a proposal looks here for events that name it.
    op.create_index(
        op.f("ix_audit_events_tenant_id_proposal_id"),
        "audit_events",
        ["tenant_id", "proposal_id"],
    )

    for statement in (
        *ROW_LEVEL_SECURITY,
        *GRANTS,
        *REQUEST_TRIGGER,
        *PROPOSAL_TRIGGER,
    ):
        op.execute(statement)


def downgrade() -> None:
    # The audit key points at ai_proposals, so it goes first, then the children before their
    # parents. Dropping a table also drops its indexes, policies, triggers, and grants.
    op.drop_index(op.f("ix_audit_events_tenant_id_proposal_id"), table_name="audit_events")
    op.drop_constraint(
        op.f("fk_audit_events_tenant_id_proposal_id_ai_proposals"),
        "audit_events",
        type_="foreignkey",
    )
    op.drop_table("time_off_requests")
    op.drop_table("time_off_openings")
    op.drop_table("ai_proposals")
    # The functions are ours to drop, now that no trigger uses them.
    op.execute("DROP FUNCTION app.enforce_time_off_request_update()")
    op.execute("DROP FUNCTION app.enforce_proposal_update()")
    op.execute("DROP FUNCTION app.enforce_proposal_insert()")
    op.drop_constraint(
        op.f("uq_ai_turns_tenant_id_id_conversation_id_person_id"), "ai_turns", type_="unique"
    )
    op.drop_constraint(op.f("ck_people_scheduled_weekdays"), "people", type_="check")
    op.drop_column("people", "scheduled_weekdays")
    # btree_gist stays: see the docstring.
