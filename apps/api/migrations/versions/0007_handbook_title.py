"""Store each handbook version's title on the version.

The handbook page shows the title ("Juniper Row Employee Handbook") next to the version label, so
it lives in the database with the version it belongs to. Ingestion writes it from handbook.yaml.

The column is NOT NULL with a default of the empty string, so an insert that omits it still works.
A version loaded before this migration is backfilled with the title of handbook 2026.10, the only
edition that exists, so an existing development database works without a reload. The roundtrip
(downgrade drops the column, upgrade re-adds and backfills it) works the same way.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The title in handbook/handbook.yaml for edition 2026.10, copied here so the migration doesn't
# depend on files that change after it.
TITLE_2026_10 = "Juniper Row Employee Handbook"


def upgrade() -> None:
    op.add_column(
        "handbook_versions",
        sa.Column("title", sa.Text(), server_default=sa.text("''"), nullable=False),
    )
    op.get_bind().execute(
        sa.text("UPDATE handbook_versions SET title = :title WHERE label = :label"),
        {"title": TITLE_2026_10, "label": "2026.10"},
    )


def downgrade() -> None:
    op.drop_column("handbook_versions", "title")
