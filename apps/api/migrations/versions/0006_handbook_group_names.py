"""Store each handbook version's chapter and addendum names on the version.

Retrieval shows a hit's group ("Time off", "California addendum"), and the handbook list needs the
same names, so they live in the database with the version they belong to. Ingestion writes them
from handbook.yaml: `{"chapters": {"1": "Welcome", ...}, "addenda": {"CA": "California addendum"}}`.

The column is NOT NULL with a default of `{}`, so an insert that omits it still works (a reader
shows no group name for it). A version loaded before this migration is backfilled with the names
in handbook 2026.10, the only edition that exists, so an existing development database works
without a reload. Re-ingesting reports "unchanged" and leaves them in place. The roundtrip
(downgrade drops the column, upgrade re-adds and backfills it) works the same way.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-12
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The names in handbook/handbook.yaml for edition 2026.10, copied here so the migration doesn't
# depend on files that change after it.
EDITION_2026_10 = {
    "chapters": {
        "1": "Welcome",
        "2": "Working here",
        "3": "Hours and pay",
        "4": "Time off",
        "5": "Leaves of absence",
        "6": "Health, safety, and support",
        "7": "Privacy and confidential cases",
    },
    "addenda": {"CA": "California addendum", "CO": "Colorado addendum", "TX": "Texas addendum"},
}


def upgrade() -> None:
    op.add_column(
        "handbook_versions",
        sa.Column(
            "group_names",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.get_bind().execute(
        sa.text(
            "UPDATE handbook_versions SET group_names = CAST(:names AS jsonb) WHERE label = :label"
        ),
        {"names": json.dumps(EDITION_2026_10), "label": "2026.10"},
    )


def downgrade() -> None:
    op.drop_column("handbook_versions", "group_names")
