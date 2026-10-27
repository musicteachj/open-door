"""The tables. Migration 0003 creates the tenant tables, with their row-level security and grants.
Migration 0004 adds the handbook tables, which are global and read-only to the API, migration
0008 adds the assistant's tables, and migration 0009 adds the time-off tables and proposals at the
end of this file.

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
from decimal import Decimal
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    Computed,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    LargeBinary,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    false,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR, ExcludeConstraint
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
        CheckConstraint(
            "cardinality(scheduled_weekdays) >= 1"
            " AND scheduled_weekdays <@ ARRAY[1, 2, 3, 4, 5, 6, 7]::smallint[]",
            name="scheduled_weekdays",
        ),
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
    # The ISO weekdays the person works (1 is Monday, 7 is Sunday), which the time-off engine counts
    # against. The default is Monday to Friday, kept on purpose (migration 0009): sandboxes that
    # predate the column get it, and the seed writes every person's days explicitly.
    scheduled_weekdays: Mapped[list[int]] = mapped_column(
        ARRAY(SmallInteger), server_default=text("'{1,2,3,4,5}'")
    )


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
        # An event can name only a proposal of its own sandbox (migration 0009). Deleting a
        # sandbox removes both tables' rows in one statement, so this key never blocks it.
        ForeignKeyConstraint(
            ["tenant_id", "proposal_id"], ["ai_proposals.tenant_id", "ai_proposals.id"]
        ),
        CheckConstraint("via IN ('ui', 'assistant', 'system')", name="via"),
        Index(None, "tenant_id", "occurred_at"),
        Index(None, "tenant_id", "actor_person_id"),
        # For the key to the proposal: deleting a proposal looks here for events that name it.
        Index(None, "tenant_id", "proposal_id"),
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
    # {"chapters": {"1": "Welcome", ...}, "addenda": {"CA": "California addendum", ...}}, from
    # handbook.yaml. '{}' for an insert that omits it.
    group_names: Mapped[dict[str, dict[str, str]]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb")
    )
    # The handbook's title, from handbook.yaml. '' for an insert that omits it.
    title: Mapped[str] = mapped_column(server_default=text("''"))
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


class AiConversation(Base):
    """One person's conversation with the assistant, pinned to the models and prompts it began
    with. Postgres shows a row only to its person, HR included (migration 0008)."""

    __tablename__ = "ai_conversations"
    __table_args__ = (
        # The target of the children's ownership keys: a turn or message can point only at a
        # conversation that belongs to the same person (see AiTurn).
        UniqueConstraint("tenant_id", "id", "person_id"),
        ForeignKeyConstraint(["tenant_id", "person_id"], ["people.tenant_id", "people.id"]),
        # The newest conversation for a person.
        Index(None, "tenant_id", "person_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(TENANT_FK, ondelete="CASCADE"))
    person_id: Mapped[uuid.UUID]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    # The pins. A conversation keeps its model, system prompt, and tool list for its whole life,
    # so the cached prefix stays valid and an old conversation never changes under the person.
    model: Mapped[str]
    guard_model: Mapped[str]
    effort: Mapped[str]
    prompt_version: Mapped[str]
    toolset_version: Mapped[str]
    # This conversation's data key, wrapped by the key-encryption key named by key_id (ADR 0015,
    # migration 0012). Every sealed value in the conversation's rows opens with it.
    key_id: Mapped[str]
    wrapped_key: Mapped[bytes] = mapped_column(LargeBinary)


class AiTurn(Base):
    """One question and its answer, and the trace of how the assistant produced it.

    The only assistant row that changes, and only while it is `running`: `finish_turn` records its
    end, and `recover_abandoned` fails one whose task died. Once it has ended, a trigger freezes it.
    """

    __tablename__ = "ai_turns"
    __table_args__ = (
        # Targets of the keys from messages, feedback (with the person), spend (without), and
        # proposals (with the conversation too: a proposal's turn is in its own conversation).
        UniqueConstraint("tenant_id", "id", "person_id"),
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "id", "conversation_id", "person_id"),
        # Ownership keys. Postgres checks a foreign key without row-level security, so a plain
        # (tenant_id, conversation_id) key would let one person add a turn to another's
        # conversation, if they knew its random ID. Carrying person_id makes that impossible.
        ForeignKeyConstraint(
            ["tenant_id", "conversation_id", "person_id"],
            ["ai_conversations.tenant_id", "ai_conversations.id", "ai_conversations.person_id"],
            name="fk_ai_turns_conversation_owner",
        ),
        CheckConstraint(
            "status IN ('running', 'completed', 'stopped', 'failed', 'crisis',"
            " 'guard_unavailable')",
            name="status",
        ),
        # One turn at a time per conversation.
        Index(
            "uq_ai_turns_one_running_per_conversation",
            "tenant_id",
            "conversation_id",
            unique=True,
            postgresql_where=text("status = 'running'"),
        ),
        # A conversation's turns, oldest first.
        Index(None, "tenant_id", "conversation_id", "started_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(TENANT_FK, ondelete="CASCADE"))
    person_id: Mapped[uuid.UUID]
    conversation_id: Mapped[uuid.UUID]
    # Sealed with the conversation's data key (migration 0012); so is the answer below.
    question_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    status: Mapped[str]
    # Set when status is `failed`: the stream's error code, such as `model-unavailable`.
    error_code: Mapped[str | None]
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())
    ended_at: Mapped[datetime | None]
    # What the person sees after a reload. A stopped turn keeps its partial answer here. Null until
    # the turn first saves an answer, and read as "".
    answer_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, server_default=text("'[]'"))

    # The trace, filled in when the turn ends (docs/specs/2026-10-14-phase-4-assistant-core.md,
    # "Ending a turn"). Phase 7's console reads these columns as they are.
    # The guard's verdict, or null if the guard didn't run (a budget refusal, say).
    # none_as_null: Python None is SQL NULL, not the JSON value null, so `IS NULL` finds it.
    guard_verdict: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    # [{name, inputSummary, ok, durationMs}], in call order. Each inputSummary is the base64 of a
    # sealed value (migration 0012); the names, results, and durations stay readable.
    tool_calls: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, server_default=text("'[]'"))
    # The handbook sections the search tool returned, as [{sectionId, passageIds}].
    sections_retrieved: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, server_default=text("'[]'")
    )
    # The model IDs that served the turn. More than one if a fallback happened.
    served_by_models: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default=text("'{}'::text[]")
    )
    effort: Mapped[str | None]
    prompt_version: Mapped[str | None]
    toolset_version: Mapped[str | None]
    input_tokens: Mapped[int] = mapped_column(server_default=text("0"))
    output_tokens: Mapped[int] = mapped_column(server_default=text("0"))
    cache_read_tokens: Mapped[int] = mapped_column(server_default=text("0"))
    cache_write_tokens: Mapped[int] = mapped_column(server_default=text("0"))
    # The turn's cost at list price, guard included.
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), server_default=text("0"))
    # Milliseconds from the start of the turn to the first event the person could see.
    first_event_ms: Mapped[int | None]
    total_ms: Mapped[int | None]
    refusal: Mapped[bool] = mapped_column(server_default=false())
    fallback: Mapped[bool] = mapped_column(server_default=false())
    injection_suspected: Mapped[bool] = mapped_column(server_default=false())


class AiMessage(Base):
    """One message of the conversation's history, stored exactly as the Messages API takes it.

    Insert-only. `content_ciphertext` seals the content's JSON text exactly as it was serialized, so
    it opens to the same bytes: the model's thinking blocks are signed over their exact bytes, and
    the history must go back to the API unchanged (ADR 0015, migration 0012).
    """

    __tablename__ = "ai_messages"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "conversation_id", "person_id"],
            ["ai_conversations.tenant_id", "ai_conversations.id", "ai_conversations.person_id"],
            name="fk_ai_messages_conversation_owner",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "turn_id", "person_id"],
            ["ai_turns.tenant_id", "ai_turns.id", "ai_turns.person_id"],
            name="fk_ai_messages_turn_owner",
        ),
        UniqueConstraint("tenant_id", "conversation_id", "position"),
        CheckConstraint("role IN ('user', 'assistant', 'system')", name="role"),
        # For the foreign key to the turn: deleting a turn looks here for messages that refer to it.
        Index(None, "tenant_id", "turn_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(TENANT_FK, ondelete="CASCADE"))
    person_id: Mapped[uuid.UUID]
    conversation_id: Mapped[uuid.UUID]
    turn_id: Mapped[uuid.UUID]
    # The message's place in the conversation, from 0.
    position: Mapped[int]
    role: Mapped[str]
    content_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    # One entry per `search_result` block in `content`, in block order, written with the message:
    # the section ID, the passage IDs of each text block, the title, the group name, the audience
    # label, the last-updated date, and the deep link. The block's own text can't give those back
    # reliably. Null for a message with no search results.
    sources: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB(none_as_null=True))
    # On a `system` (context) message: "<proposal id>:<status>" for each card whose outcome that
    # context told the model, so the next turn reports each (card, status) only once and a card
    # that changes again (expired by the clock, then confirmed) is told again (migration 0011).
    # Null on other messages.
    reported_outcomes: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class AiFeedback(Base):
    """A person's thumbs up or down on one answer. One per turn."""

    __tablename__ = "ai_feedback"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "turn_id", "person_id"],
            ["ai_turns.tenant_id", "ai_turns.id", "ai_turns.person_id"],
            name="fk_ai_feedback_turn_owner",
        ),
        UniqueConstraint("tenant_id", "turn_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(TENANT_FK, ondelete="CASCADE"))
    person_id: Mapped[uuid.UUID]
    turn_id: Mapped[uuid.UUID]
    helpful: Mapped[bool]
    reason_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class AiSpend(Base):
    """The sandbox's budget ledger: the most a call could cost, reserved before it, and the
    difference to its real cost, settled after it. Insert-only; the sandbox's spend is the sum.

    It has no person_id, and the per-person rule doesn't apply to it: the budget is the whole
    sandbox's, whoever asked.
    """

    __tablename__ = "ai_spend"
    __table_args__ = (
        # No person_id here, so this key is the plain (tenant_id, turn_id) one. It still keeps a
        # spend row inside its own tenant.
        ForeignKeyConstraint(
            ["tenant_id", "turn_id"],
            ["ai_turns.tenant_id", "ai_turns.id"],
            name="fk_ai_spend_turn",
        ),
        CheckConstraint("kind IN ('reserve', 'settle')", name="kind"),
        CheckConstraint("kind <> 'reserve' OR amount_usd >= 0", name="reserve_not_negative"),
        CheckConstraint("amount_usd BETWEEN -10 AND 10", name="amount_range"),
        # The sum of a sandbox's rows, under the budget lock, uses the prefix (tenant_id). The whole
        # index serves the foreign key to the turn: deleting a turn looks here for its rows.
        Index(None, "tenant_id", "turn_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(TENANT_FK, ondelete="CASCADE"))
    turn_id: Mapped[uuid.UUID]
    kind: Mapped[str]
    # A settle row is the actual cost minus the reservation, so it can be negative.
    amount_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class AiSpendDaily(Base):
    """What all sandboxes together have spent on the assistant, by UTC day. Global: no tenant_id.

    It holds amounts only, so the demo's daily cap can sum every sandbox. Insert-only, with the
    same kinds and checks as AiSpend, plus a day that must be today: a trigger stamps created_at
    with the current time, and a check ties `day` to it. Only a settle may be dated yesterday.
    """

    __tablename__ = "ai_spend_daily"
    __table_args__ = (
        CheckConstraint("kind IN ('reserve', 'settle')", name="kind"),
        CheckConstraint("kind <> 'reserve' OR amount_usd >= 0", name="reserve_not_negative"),
        CheckConstraint("amount_usd BETWEEN -10 AND 10", name="amount_range"),
        # A reserve is pinned to today. A settle may also land on yesterday, the day its reservation
        # was made, when the two straddle midnight.
        CheckConstraint(
            "day = (created_at AT TIME ZONE 'UTC')::date"
            " OR (kind = 'settle' AND day = (created_at AT TIME ZONE 'UTC')::date - 1)",
            name="day_matches_created_at",
        ),
        # The sum for one day, under the budget lock.
        Index(None, "day"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    # The UTC date of the spend. It defaults to today (UTC). A settle is written with its
    # reservation's day, which the check allows to be yesterday.
    day: Mapped[date] = mapped_column(server_default=text("(now() AT TIME ZONE 'UTC')::date"))
    kind: Mapped[str]
    amount_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class AiProposal(Base):
    """Something the assistant wants done, waiting for the person it was made for to confirm.

    The model proposes and never writes: this row holds the validated input (`payload`) and the
    card the person is shown, and the server runs the stored payload, never the client's, when they
    confirm. Postgres shows a row only to its person, HR included. Its status moves from `pending`
    to one final status, once, and a trigger (migration 0009) refuses every other change. The API
    may update only status, ended_at, and outcome.
    """

    __tablename__ = "ai_proposals"
    __table_args__ = (
        # Targets of the audit key, and of a request's key (with the person).
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "id", "person_id"),
        # Ownership keys, as for the assistant's other rows: the conversation is the person's own,
        # and the turn is in that conversation and is the person's own.
        ForeignKeyConstraint(
            ["tenant_id", "conversation_id", "person_id"],
            ["ai_conversations.tenant_id", "ai_conversations.id", "ai_conversations.person_id"],
            name="fk_ai_proposals_conversation_owner",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "turn_id", "conversation_id", "person_id"],
            ["ai_turns.tenant_id", "ai_turns.id", "ai_turns.conversation_id", "ai_turns.person_id"],
            name="fk_ai_proposals_turn_owner",
        ),
        CheckConstraint(
            "action IN ('timeoff.request', 'timeoff.decide', 'timeoff.cancel')", name="action"
        ),
        CheckConstraint(
            "status IN ('pending', 'executed', 'failed', 'canceled', 'expired')", name="status"
        ),
        CheckConstraint(
            "(ended_at IS NULL) = (status = 'pending')", name="ended_at_matches_status"
        ),
        CheckConstraint("expires_at > created_at", name="expires_after_created"),
        CheckConstraint(
            "expires_at <= created_at + interval '15 minutes'", name="expires_within_15_minutes"
        ),
        # One live proposal per conversation (migration 0010): the service replaces the pending
        # card before it stores a new one, and this refuses a second pending card outright.
        Index(
            "uq_ai_proposals_one_pending_per_conversation",
            "tenant_id",
            "conversation_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        # A conversation's proposals, oldest first.
        Index(None, "tenant_id", "conversation_id", "created_at"),
        # For the key to the turn: deleting a turn looks here for proposals that name it.
        Index(None, "tenant_id", "turn_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(TENANT_FK, ondelete="CASCADE"))
    person_id: Mapped[uuid.UUID]
    conversation_id: Mapped[uuid.UUID]
    turn_id: Mapped[uuid.UUID]
    # timeoff.request, timeoff.decide, or timeoff.cancel.
    action: Mapped[str]
    # The validated tool input. The confirm runs this, not anything the client sends.
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    # The details the server built for the card the person sees. Never model text.
    card: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    expires_at: Mapped[datetime]
    # Set exactly when the status is not `pending`.
    ended_at: Mapped[datetime | None]
    # The request ID made or changed, or the failure's code and its fixed text.
    outcome: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))


class TimeOffOpening(Base):
    """A person's PTO balance on `as_of`, in minutes. The engine counts forward from it, and a
    balance is worked out on every read, never stored (ADR 0012). One row per person."""

    __tablename__ = "time_off_openings"
    __table_args__ = (
        UniqueConstraint("tenant_id", "person_id"),
        ForeignKeyConstraint(["tenant_id", "person_id"], ["people.tenant_id", "people.id"]),
        CheckConstraint("amount_minutes >= 0", name="amount_not_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(TENANT_FK, ondelete="CASCADE"))
    person_id: Mapped[uuid.UUID]
    as_of: Mapped[date]
    amount_minutes: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class TimeOffRequest(Base):
    """A PTO request or a recorded sick day. Its checks hold the engine's rules, and a trigger
    (migration 0009) lets its status move only one way. The API may update only the status, the
    decision columns, and canceled_at. Postgres shows a row to the whole sandbox, and the policy
    layer decides who reads which."""

    __tablename__ = "time_off_requests"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "person_id"], ["people.tenant_id", "people.id"]),
        ForeignKeyConstraint(["tenant_id", "decided_by"], ["people.tenant_id", "people.id"]),
        # The proposal that made a request is that person's own.
        ForeignKeyConstraint(
            ["tenant_id", "proposal_id", "person_id"],
            ["ai_proposals.tenant_id", "ai_proposals.id", "ai_proposals.person_id"],
            name="fk_time_off_requests_proposal_owner",
        ),
        CheckConstraint("type IN ('pto', 'sick')", name="type"),
        CheckConstraint(
            "status IN ('pending', 'approved', 'denied', 'recorded', 'canceled')", name="status"
        ),
        CheckConstraint("created_via IN ('ui', 'assistant')", name="created_via"),
        # Each half reads as "if it is this type, then...", so an unknown type passes here and
        # fails only the type check.
        CheckConstraint(
            "(type <> 'pto' OR status <> 'recorded')"
            " AND (type <> 'sick' OR status IN ('recorded', 'canceled'))",
            name="status_matches_type",
        ),
        CheckConstraint("end_date >= start_date", name="dates_in_order"),
        CheckConstraint("end_date - start_date <= 30", name="at_most_31_days"),
        CheckConstraint(
            "partial_minutes IS NULL OR (start_date = end_date AND ("
            "(type = 'pto' AND partial_minutes = 240)"
            " OR (type = 'sick' AND partial_minutes % 60 = 0"
            " AND partial_minutes BETWEEN 60 AND 480)))",
            name="partial_minutes_match_the_engine",
        ),
        CheckConstraint("amount_minutes > 0", name="amount_is_positive"),
        # Written as implications, one per status, so an unknown status passes here and fails only
        # the status check.
        CheckConstraint(
            "(status NOT IN ('pending', 'recorded') OR (decided_by IS NULL AND decided_at IS NULL"
            " AND decision_note IS NULL AND canceled_at IS NULL))"
            " AND (status NOT IN ('approved', 'denied') OR (decided_by IS NOT NULL"
            " AND decided_at IS NOT NULL AND canceled_at IS NULL))"
            " AND (status <> 'canceled' OR (canceled_at IS NOT NULL"
            " AND (decided_by IS NULL) = (decided_at IS NULL)))",
            name="decision_matches_status",
        ),
        CheckConstraint(
            "decision_note IS NULL OR (char_length(decision_note) <= 300 AND status = 'denied')",
            name="decision_note_is_a_short_denial_note",
        ),
        CheckConstraint(
            "(proposal_id IS NOT NULL) = (created_via = 'assistant')",
            name="proposal_matches_created_via",
        ),
        # Two open requests for one person can't share a day. Both ends are inclusive. A canceled
        # or denied request frees its days. The engine checks first, so a person sees the friendly
        # reason; this catches two requests that race.
        ExcludeConstraint(
            ("tenant_id", "="),
            ("person_id", "="),
            (text("daterange(start_date, end_date, '[]')"), "&&"),
            using="gist",
            where=text("status IN ('pending', 'approved', 'recorded')"),
            name="ex_time_off_requests_no_overlap",
        ),
        # Nobody decides their own request. A null decided_by passes.
        CheckConstraint("decided_by IS DISTINCT FROM person_id", name="no_self_decision"),
        # A person's requests by date.
        Index(None, "tenant_id", "person_id", "start_date"),
        # For the key to the decider: deleting a person looks here.
        Index(None, "tenant_id", "decided_by"),
        # A proposal makes at most one request. It also serves the key to the proposal.
        Index(
            "uq_time_off_requests_tenant_id_proposal_id",
            "tenant_id",
            "proposal_id",
            unique=True,
            postgresql_where=text("proposal_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(TENANT_FK, ondelete="CASCADE"))
    person_id: Mapped[uuid.UUID]
    # pto or sick.
    type: Mapped[str]
    # Calendar dates in the person's location's time zone. Both ends are inclusive.
    start_date: Mapped[date]
    end_date: Mapped[date]
    # Null for whole days. Otherwise 240 for a half-day of PTO, or a whole number of hours from
    # 60 to 480 for sick leave, on a single day.
    partial_minutes: Mapped[int | None]
    # The engine's count when the request was made, kept for the record.
    amount_minutes: Mapped[int]
    # pending, approved, denied, recorded, or canceled. A PTO request is never recorded, and a sick
    # one is only recorded or canceled.
    status: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    # ui or assistant.
    created_via: Mapped[str]
    # Set exactly when created_via is assistant.
    proposal_id: Mapped[uuid.UUID | None]
    decided_by: Mapped[uuid.UUID | None]
    decided_at: Mapped[datetime | None]
    # A denial's note, up to 300 characters. Written by a person, shown on pages and cards, and
    # never sent to a model.
    decision_note: Mapped[str | None]
    canceled_at: Mapped[datetime | None]
