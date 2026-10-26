"""Record which cards' outcomes each stored context told the model about.

The per-turn context carries a line about cards that ended since the model last heard (ADR 0013).
It used to decide "since" by comparing timestamps taken in different transactions: a confirm that
began before a turn but locked the card after the turn read it commits with an `ended_at` earlier
than the turn's `started_at`, so the next turn skipped it and the model was never told.

ai_messages.reported_outcomes fixes that by recording what was told, not when. It is set on a
`system` (context) message, in the same INSERT, to one "<proposal id>:<status>" entry for each card
whose outcome that context reported, with the status the context showed (a card whose time ran out
shows as `expired` even while its row is still `pending`). It is null on every other message. The
next turn reports each ended card whose current shown status no stored context has told, so a
(card, status) pair is told once, a card that changes again (expired by the clock, then confirmed
by a transaction already in flight) is told again, and a turn that stored no context (it failed,
crashed, or ended in a crisis) leaves its cards to be reported by the next one.

A plain array with no foreign key, like the other lists on this table: it is a record of what the
model was shown, and the insert-only table needs no new grant.

Existing contexts are backfilled with the cards of their conversation that had ended, or expired,
by the start of their turn, so no old outcome is told a second time. That includes any card the
original race left untold: those stay untold, since nothing recorded what was told, and no card is
ever told twice.

The backfill reads and writes tables that force row-level security with policies only for od_app,
which applies even to the table owner. So it runs between `NO FORCE ROW LEVEL SECURITY` and
`FORCE ROW LEVEL SECURITY` on those tables, which the owner can always do and which needs no
superuser or BYPASSRLS. Alembic runs the whole migration in one transaction and Postgres DDL is
transactional, so a failure in between rolls back the NO FORCE too: FORCE cannot be left off.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("ai_messages", "ai_turns", "ai_proposals")

BACKFILL = """
UPDATE ai_messages AS m
SET reported_outcomes = found.entries
FROM (
    SELECT m2.id AS message_id,
           array_agg(
               p.id::text || ':' ||
               CASE WHEN p.ended_at IS NOT NULL AND p.ended_at <= t.started_at THEN p.status
                    ELSE 'expired' END
           ) AS entries
    FROM ai_messages AS m2
    JOIN ai_turns AS t ON t.tenant_id = m2.tenant_id AND t.id = m2.turn_id
    JOIN ai_proposals AS p
      ON p.tenant_id = m2.tenant_id
     AND p.conversation_id = m2.conversation_id
     AND (p.ended_at <= t.started_at OR p.expires_at <= t.started_at)
    WHERE m2.role = 'system'
    GROUP BY m2.id
) AS found
WHERE m.id = found.message_id
"""


def upgrade() -> None:
    op.add_column(
        "ai_messages",
        sa.Column("reported_outcomes", postgresql.ARRAY(sa.Text()), nullable=True),
    )
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
    op.execute(BACKFILL)
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_column("ai_messages", "reported_outcomes")
