"""Encrypt the conversation text (ADR 0015).

Handbook section 7.2 promises that confidential text is stored encrypted, and Phase 6 delivers it
for all conversation text. The API seals each value with AES-256-GCM under a data key, one per
conversation, and the database stores only ciphertext. This migration swaps the plaintext columns
for ciphertext ones:

  ai_conversations   gains key_id (the key-encryption key that wrapped the data key) and
                     wrapped_key (the conversation's data key, wrapped); both not null
  ai_messages        content (json)       -> content_ciphertext (bytea, not null)
  ai_turns           question (text)      -> question_ciphertext (bytea, not null)
                     answer_text (text)   -> answer_ciphertext (bytea, null until the turn ends,
                                             read as "")
  ai_feedback        reason (text)        -> reason_ciphertext (bytea, null), and the reason's
                                             500-character CHECK goes: the API enforces the limit
                                             before sealing, as it does the question's 2,000

ai_turns.tool_calls keeps its column and its type. Each entry's `inputSummary` is stored as a
string, the base64 of the sealed summary, inside the same JSON, so the grants, the frozen-turn
trigger, and the console's read of names, results, and durations stay as they were. The key's place
for an entry is decided in the store (migration 0012 only changes the schema).

The guard's verdict, statuses, citations (handbook passages), retrieved sections, tokens, and costs
stay readable, for the console.

Every sandbox is deleted first, in both directions. Nothing is deployed and each sandbox expires
within 24 hours, so no plaintext read path is kept, and the new NOT NULL columns need no backfill.
Deleting a tenant cascades to every row in it. Row-level security is forced on the tables, and
under FORCE even the owner's DELETE sees no rows, so the delete runs between `NO FORCE ROW LEVEL
SECURITY` and `FORCE ROW LEVEL SECURITY` on `tenants` (as 0011 does for its backfill), which the
owner can always do. Alembic runs the whole migration in one transaction and Postgres DDL is
transactional, so a failure in between rolls back the NO FORCE too: FORCE cannot be left off.

The UPDATE grant on ai_turns is per column. Dropping answer_text drops its privilege, so the new
answer_ciphertext column is granted in its place; tool_calls keeps its grant. The finished-turn
trigger (0008) names no column, so a finished turn is still frozen.

Plaintext that the old columns held can linger in Postgres's dead rows and write-ahead log until a
vacuum. docs/DATA-INVENTORY.md says so.

The downgrade also deletes every sandbox, and cannot restore them: the ciphertext is dropped with
its keys, and the plaintext is gone. It puts back the empty plaintext columns, the CHECK, and the
grant, so 0011's schema works again.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | Sequence[str] | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


DELETE_EVERY_TENANT = (
    "ALTER TABLE tenants NO FORCE ROW LEVEL SECURITY",
    "DELETE FROM tenants",
    "ALTER TABLE tenants FORCE ROW LEVEL SECURITY",
)


def delete_every_tenant() -> None:
    for statement in DELETE_EVERY_TENANT:
        op.execute(statement)


def upgrade() -> None:
    delete_every_tenant()
    op.add_column("ai_conversations", sa.Column("key_id", sa.Text(), nullable=False))
    op.add_column("ai_conversations", sa.Column("wrapped_key", sa.LargeBinary(), nullable=False))

    op.drop_column("ai_messages", "content")
    op.add_column("ai_messages", sa.Column("content_ciphertext", sa.LargeBinary(), nullable=False))

    # Dropping answer_text takes its UPDATE privilege with it.
    op.drop_column("ai_turns", "question")
    op.drop_column("ai_turns", "answer_text")
    op.add_column("ai_turns", sa.Column("question_ciphertext", sa.LargeBinary(), nullable=False))
    op.add_column("ai_turns", sa.Column("answer_ciphertext", sa.LargeBinary(), nullable=True))
    op.execute("GRANT UPDATE (answer_ciphertext) ON ai_turns TO od_app")

    op.drop_constraint(op.f("ck_ai_feedback_reason_length"), "ai_feedback", type_="check")
    op.drop_column("ai_feedback", "reason")
    op.add_column("ai_feedback", sa.Column("reason_ciphertext", sa.LargeBinary(), nullable=True))


def downgrade() -> None:
    delete_every_tenant()
    op.drop_column("ai_feedback", "reason_ciphertext")
    op.add_column("ai_feedback", sa.Column("reason", sa.Text(), nullable=True))
    op.create_check_constraint(
        op.f("ck_ai_feedback_reason_length"), "ai_feedback", "char_length(reason) <= 500"
    )

    op.drop_column("ai_turns", "answer_ciphertext")
    op.drop_column("ai_turns", "question_ciphertext")
    op.add_column("ai_turns", sa.Column("question", sa.Text(), nullable=False))
    op.add_column(
        "ai_turns",
        sa.Column("answer_text", sa.Text(), server_default=sa.text("''"), nullable=False),
    )
    op.execute("GRANT UPDATE (answer_text) ON ai_turns TO od_app")

    op.drop_column("ai_messages", "content_ciphertext")
    op.add_column("ai_messages", sa.Column("content", sa.JSON(), nullable=False))

    op.drop_column("ai_conversations", "wrapped_key")
    op.drop_column("ai_conversations", "key_id")
