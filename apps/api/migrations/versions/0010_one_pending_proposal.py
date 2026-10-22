"""Hold "one live proposal per conversation" in the database.

The proposal service replaces the pending card of a conversation whenever it stores a new one, and
it takes an advisory lock on the conversation first (the API's login may not lock the row itself)
so that two proposals made at once can't both see an empty
conversation. That is the rule's first guard. This index is its second: a unique partial index on
(tenant_id, conversation_id) where the status is `pending`, written like 0008's one-running-turn
index, so a second pending card in one conversation is refused by Postgres whatever the code does.

An expired card that nothing has marked yet is still `pending` in the table. The service marks
those expired before it stores a new card, so the index never blocks one.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX = "uq_ai_proposals_one_pending_per_conversation"


def upgrade() -> None:
    op.create_index(
        INDEX,
        "ai_proposals",
        ["tenant_id", "conversation_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index(INDEX, table_name="ai_proposals")
