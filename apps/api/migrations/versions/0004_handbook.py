"""Add the handbook: versions, sections, and the chunks that retrieval searches.

The three tables are global: they have no tenant_id, so they sit outside row-level security. The
API's login may only read them. Ingestion writes them as the database owner. A tenant (a sandbox)
is pinned to one handbook version through `tenants.handbook_version_id`, and a version in use can't
be deleted. app/db/models.py describes the same tables, and `alembic check` keeps the two in step
(it doesn't compare the grants, which tests cover).

The `search` column is generated from columns of its own row, so each chunk carries a copy of its
section's key and title for the weight-A part of the search vector. The configuration is written as
the literal 'english', which keeps the expression immutable, as a generated column requires. There
is no approximate (ANN) index on `embedding`: a version has a few hundred chunks, and an exact scan
takes milliseconds and never varies.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Created in this order, dropped in reverse.
HANDBOOK_TABLES = ("handbook_versions", "handbook_sections", "handbook_chunks")

SEARCH_EXPRESSION = (
    "setweight(to_tsvector('english',"
    " coalesce(section_key, '') || ' ' || coalesce(section_title, '') || ' '"
    " || coalesce(heading, '')), 'A')"
    " || setweight(to_tsvector('english', text), 'B')"
)

# Read-only for the API; nothing for od_cleanup. Ingestion runs as the owner.
GRANTS = ("GRANT SELECT ON handbook_versions, handbook_sections, handbook_chunks TO od_app",)


def upgrade() -> None:
    op.create_table(
        "handbook_versions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("embedding_model", sa.Text(), nullable=False),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=False),
        sa.Column("updated_on", sa.Date(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_handbook_versions")),
        sa.UniqueConstraint("label", name=op.f("uq_handbook_versions_label")),
        sa.UniqueConstraint("content_hash", name=op.f("uq_handbook_versions_content_hash")),
    )
    op.create_table(
        "handbook_sections",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("section_key", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("chapter", sa.Integer(), nullable=True),
        sa.Column("addendum_state", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("supplements_key", sa.Text(), nullable=True),
        sa.Column("audience", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("updated_on", sa.Date(), nullable=False),
        sa.Column("sources", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("blocks", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "kind IN ('company', 'addendum')", name=op.f("ck_handbook_sections_kind")
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["handbook_versions.id"],
            name=op.f("fk_handbook_sections_version_id_handbook_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_handbook_sections")),
        sa.UniqueConstraint(
            "version_id", "section_key", name=op.f("uq_handbook_sections_version_id_section_key")
        ),
    )
    op.create_table(
        "handbook_chunks",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("section_id", sa.Uuid(), nullable=False),
        sa.Column("section_key", sa.Text(), nullable=False),
        sa.Column("section_title", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("heading", sa.Text(), nullable=True),
        sa.Column("passage_ids", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "search",
            postgresql.TSVECTOR(),
            sa.Computed(SEARCH_EXPRESSION, persisted=True),
            nullable=False,
        ),
        sa.Column("embedding", Vector(1024), nullable=False),
        sa.ForeignKeyConstraint(
            ["section_id"],
            ["handbook_sections.id"],
            name=op.f("fk_handbook_chunks_section_id_handbook_sections"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["handbook_versions.id"],
            name=op.f("fk_handbook_chunks_version_id_handbook_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_handbook_chunks")),
    )
    op.create_index(
        op.f("ix_handbook_chunks_search"),
        "handbook_chunks",
        ["search"],
        postgresql_using="gin",
    )
    op.add_column("tenants", sa.Column("handbook_version_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_tenants_handbook_version_id_handbook_versions"),
        "tenants",
        "handbook_versions",
        ["handbook_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    for statement in GRANTS:
        op.execute(statement)


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_tenants_handbook_version_id_handbook_versions"), "tenants", type_="foreignkey"
    )
    op.drop_column("tenants", "handbook_version_id")
    # Dropping a table also drops its indexes and grants.
    for table in reversed(HANDBOOK_TABLES):
        op.drop_table(table)
