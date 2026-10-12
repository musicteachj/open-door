"""The tables. Migration 0003 creates the tenant tables, with their row-level security and grants.
Migration 0004 adds the handbook tables at the end of this file, which are global and read-only to
the API.

Every table except `tenants` and `sessions` is a tenant table: it has a tenant_id, and Postgres
shows the API only the rows of the tenant its transaction is scoped to (see app/db/tenancy.py).
Three rules keep tenants apart inside the schema:

- Unique rules start with tenant_id, so they never reveal whether a value exists in another
  tenant. A single-column primary key on a server-generated UUID is the only exception.
- Every reference is a composite foreign key that includes tenant_id, against a parent's
  UNIQUE (tenant_id, id), so a row can only point at rows in its own tenant.
- Children are deleted with their tenant (ON DELETE CASCADE from tenants). References between
  children use the default NO ACTION, so one cascading delete removes them together.
"""

import uuid
from datetime import date, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    Computed,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Text,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

TENANT_FK = "tenants.id"


class Tenant(Base):
    """One sandbox company. It and everything in it are deleted 24 hours after it is created."""

    __tablename__ = "tenants"
    __table_args__ = (
        # A sandbox lives 24 hours. The hour of slack allows for clock differences, and the rule
        # means no bug or request can create a sandbox that is never cleaned up.
        CheckConstraint("expires_at <= created_at + interval '25 hours'", name="lifetime"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    # A trigger (migration 0003) overwrites this with now() on insert, so it can't be chosen.
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    expires_at: Mapped[datetime]
    # The date the seed data is relative to, so "last week" always means last week.
    anchor_date: Mapped[date]
    # The handbook version this sandbox answers from. A trigger (migration 0005) sets it on insert
    # to the newest published version, whatever the caller supplies, and refuses the insert if none
    # is published. Null only for sandboxes created before migration 0004. RESTRICT: a version in
    # use can't be deleted.
    handbook_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("handbook_versions.id", ondelete="RESTRICT")
    )


class Location(Base):
    __tablename__ = "locations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(TENANT_FK, ondelete="CASCADE"))
    code: Mapped[str]
    name: Mapped[str]
    city: Mapped[str]
    state: Mapped[str]
    # An IANA zone such as America/Denver. Leave dates are calendar dates in this zone.
    timezone: Mapped[str]


class Department(Base):
    __tablename__ = "departments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(TENANT_FK, ondelete="CASCADE"))
    name: Mapped[str]


class Person(Base):
    """The directory tier. Being a manager is derived from manager_id, never stored."""

    __tablename__ = "people"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "work_email"),
        UniqueConstraint("tenant_id", "persona_key"),
        ForeignKeyConstraint(
            ["tenant_id", "department_id"], ["departments.tenant_id", "departments.id"]
        ),
        ForeignKeyConstraint(["tenant_id", "location_id"], ["locations.tenant_id", "locations.id"]),
        ForeignKeyConstraint(["tenant_id", "manager_id"], ["people.tenant_id", "people.id"]),
        CheckConstraint("employment_type IN ('salaried', 'hourly')", name="employment_type"),
        CheckConstraint("persona_key IN ('priya', 'mateo', 'marcus', 'dana')", name="persona_key"),
        # Directory paging, and the recursive query for a manager's reports.
        Index(None, "tenant_id", "family_name", "given_name", "id"),
        Index(None, "tenant_id", "manager_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(TENANT_FK, ondelete="CASCADE"))
    given_name: Mapped[str]
    family_name: Mapped[str]
    title: Mapped[str]
    department_id: Mapped[uuid.UUID]
    location_id: Mapped[uuid.UUID]
    manager_id: Mapped[uuid.UUID | None]
    work_email: Mapped[str]
    employment_type: Mapped[str]
    hire_date: Mapped[date]
    is_hr_admin: Mapped[bool] = mapped_column(server_default=false())
    persona_key: Mapped[str | None]


class PersonPrivate(Base):
    """Private details. Postgres shows a row only to the person themselves and to HR."""

    __tablename__ = "person_private"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "person_id"], ["people.tenant_id", "people.id"]),
        Index(None, "tenant_id", "person_id"),
    )

    person_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(TENANT_FK, ondelete="CASCADE"))
    personal_email: Mapped[str]
    phone: Mapped[str]
    home_address: Mapped[str]
    date_of_birth: Mapped[date]


class Holiday(Base):
    """A company holiday at one location, for the Phase 5 time-off engine."""

    __tablename__ = "holidays"
    __table_args__ = (
        UniqueConstraint("tenant_id", "location_id", "holiday_date"),
        ForeignKeyConstraint(["tenant_id", "location_id"], ["locations.tenant_id", "locations.id"]),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(TENANT_FK, ondelete="CASCADE"))
    location_id: Mapped[uuid.UUID]
    holiday_date: Mapped[date]
    name: Mapped[str]


class UserSession(Base):
    """A signed-in visitor. Outside row-level security: it is looked up before the tenant is known.

    Both hashes are SHA-256 digests. The raw tokens live only in the visitor's cookies.
    """

    __tablename__ = "sessions"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "person_id"], ["people.tenant_id", "people.id"]),
        CheckConstraint("octet_length(token_hash) = 32", name="token_hash_is_sha256"),
        CheckConstraint("octet_length(csrf_hash) = 32", name="csrf_hash_is_sha256"),
        Index(None, "tenant_id", "person_id"),
    )

    token_hash: Mapped[bytes] = mapped_column(primary_key=True)
    csrf_hash: Mapped[bytes]
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(TENANT_FK, ondelete="CASCADE"))
    person_id: Mapped[uuid.UUID]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    # Copied from the tenant: a session never outlives its sandbox.
    expires_at: Mapped[datetime]


class AuditEvent(Base):
    """One recorded action. The API may only add and read these rows, never change them.

    IDs are random UUIDs, not a sequence, which would let one tenant estimate another's activity.
    """

    __tablename__ = "audit_events"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "actor_person_id"], ["people.tenant_id", "people.id"]),
        CheckConstraint("via IN ('ui', 'assistant', 'system')", name="via"),
        Index(None, "tenant_id", "occurred_at"),
        Index(None, "tenant_id", "actor_person_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(TENANT_FK, ondelete="CASCADE"))
    occurred_at: Mapped[datetime] = mapped_column(server_default=func.now())
    actor_person_id: Mapped[uuid.UUID | None]
    via: Mapped[str]
    action: Mapped[str]
    target_type: Mapped[str | None]
    target_id: Mapped[uuid.UUID | None]
    # Directory fields only. A read of private details records the field names, never the values.
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    proposal_id: Mapped[uuid.UUID | None]
    request_id: Mapped[str | None]


class HandbookVersion(Base):
    """One loaded edition of the handbook. Global: no tenant_id. The API reads, ingestion writes."""

    __tablename__ = "handbook_versions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    label: Mapped[str] = mapped_column(unique=True)
    # A SHA-256 over the source files, the chunker's version, and the embedding model and size.
    content_hash: Mapped[str] = mapped_column(unique=True)
    embedding_model: Mapped[str]
    embedding_dimensions: Mapped[int]
    # The latest section's `updated` date: the "Handbook updated" figure.
    updated_on: Mapped[date]
    # Null for a version that is loaded but not published.
    published_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class HandbookSection(Base):
    __tablename__ = "handbook_sections"
    __table_args__ = (
        UniqueConstraint("version_id", "section_key"),
        CheckConstraint("kind IN ('company', 'addendum')", name="kind"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("handbook_versions.id", ondelete="CASCADE")
    )
    # "4.3" for a company section, "CA-4.3" for a state addendum.
    section_key: Mapped[str]
    # The handbook's order.
    position: Mapped[int]
    kind: Mapped[str]
    chapter: Mapped[int | None]
    addendum_state: Mapped[str | None]
    title: Mapped[str]
    supplements_key: Mapped[str | None]
    # {"states": [...], "employmentTypes": [...], "locations": [...]}
    audience: Mapped[dict[str, Any]] = mapped_column(JSONB)
    updated_on: Mapped[date]
    sources: Mapped[list[str]] = mapped_column(JSONB)
    # The structured body: headings, passages with their IDs, and inline runs.
    blocks: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)


class HandbookChunk(Base):
    """What retrieval searches: a run of whole passages under one heading."""

    __tablename__ = "handbook_chunks"
    __table_args__ = (Index(None, "search", postgresql_using="gin"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("handbook_versions.id", ondelete="CASCADE")
    )
    section_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("handbook_sections.id", ondelete="CASCADE")
    )
    # Copies of the section's key and title. A generated column can read only its own row, and the
    # search vector weights both above the text.
    section_key: Mapped[str]
    section_title: Mapped[str]
    position: Mapped[int]
    # The `##` heading this chunk sits under; null for text before the section's first heading.
    heading: Mapped[str | None]
    # The passages this chunk covers, in order. A passage is never split across chunks.
    passage_ids: Mapped[list[str]] = mapped_column(ARRAY(Text))
    text: Mapped[str]
    # 'english' is written as a literal so the expression is immutable.
    search: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed(
            "setweight(to_tsvector('english',"
            " coalesce(section_key, '') || ' ' || coalesce(section_title, '') || ' '"
            " || coalesce(heading, '')), 'A')"
            " || setweight(to_tsvector('english', text), 'B')",
            persisted=True,
        ),
    )
    # voyage-4 at 1024 dimensions. No approximate index: an exact scan over a few hundred rows.
    embedding: Mapped[list[float]] = mapped_column(Vector(1024))
