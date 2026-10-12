"""Load a handbook version into the database: its sections, its chunks, and their embeddings.

Only ingestion, as the database owner, writes these tables; the API's login can only read them.
The owner is a superuser, so nothing here builds SQL from text: every value, including the label,
the passage text, the JSON, and the vectors, is a bound parameter of a SQLAlchemy Core statement.

`ingest` never opens or commits a transaction. The caller owns it, so a failure partway rolls the
whole version back and a test can roll everything back at the end.
"""

from dataclasses import dataclass
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy.sql import func

from app.ai.embeddings import DIMENSIONS, MODEL, Embedder, is_unit_vector
from app.db.models import HandbookChunk, HandbookSection, HandbookVersion
from app.domain.handbook.blocks import blocks_to_json
from app.domain.handbook.chunks import Chunk, chunks_for
from app.domain.handbook.hashing import content_hash
from app.domain.handbook.models import Handbook


class IngestError(Exception):
    """The handbook can't be loaded as it is."""


@dataclass(frozen=True)
class IngestResult:
    status: Literal["loaded", "unchanged"]
    version_id: UUID
    # Whether this is the version new sandboxes get: the newest published one.
    current: bool
    # That newest published version's label; None while nothing is published.
    current_label: str | None


async def ingest(
    conn: AsyncConnection, handbook: Handbook, embedder: Embedder, *, publish: bool
) -> IngestResult:
    chunks = [(section.id, chunk) for section in handbook.sections for chunk in chunks_for(section)]
    # The vectors are part of the version's hash, so they come first. In production the embedder
    # reads the committed cache and never calls Voyage. Checking them first writes nothing on a
    # bad one.
    vectors = await embedder.embed([chunk.embed_text for _, chunk in chunks], input_type="document")
    _check_vectors(vectors, len(chunks))
    digest = content_hash(handbook, model=MODEL, dimensions=DIMENSIONS, vectors=vectors)

    existing = (
        await conn.execute(
            select(HandbookVersion.id, HandbookVersion.published_at).where(
                HandbookVersion.content_hash == digest
            )
        )
    ).one_or_none()
    if existing is not None:
        if publish and existing.published_at is None:
            await conn.execute(
                update(HandbookVersion)
                .where(HandbookVersion.id == existing.id)
                .values(published_at=func.now())
            )
        return await _result(conn, "unchanged", existing.id)

    label_taken = await conn.scalar(
        select(HandbookVersion.id).where(HandbookVersion.label == handbook.version)
    )
    if label_taken is not None:
        msg = (
            f"Version {handbook.version!r} is already loaded with different content. "
            "Choose a new label (the `version` field in handbook.yaml) for this edition."
        )
        raise IngestError(msg)

    version_id = uuid4()
    await conn.execute(
        insert(HandbookVersion).values(
            id=version_id,
            label=handbook.version,
            content_hash=digest,
            embedding_model=MODEL,
            embedding_dimensions=DIMENSIONS,
            updated_on=handbook.updated_on,
            title=handbook.title,
            group_names={
                "chapters": {str(number): name for number, name in handbook.chapters.items()},
                "addenda": dict(handbook.addenda),
            },
            published_at=func.now() if publish else None,
        )
    )

    section_ids = {section.id: uuid4() for section in handbook.sections}
    await conn.execute(
        insert(HandbookSection),
        [
            {
                "id": section_ids[section.id],
                "version_id": version_id,
                "section_key": section.id,
                "position": position,
                "kind": section.kind,
                "chapter": section.chapter,
                "addendum_state": section.addendum_state,
                "title": section.title,
                "supplements_key": section.supplements,
                "audience": section.audience.to_json(),
                "updated_on": section.updated,
                "sources": list(section.sources),
                "blocks": blocks_to_json(section.blocks),
            }
            for position, section in enumerate(handbook.sections)
        ],
    )

    titles = {section.id: section.title for section in handbook.sections}
    await conn.execute(
        insert(HandbookChunk),
        [
            _chunk_row(version_id, section_ids[key], key, titles[key], chunk, vector)
            for (key, chunk), vector in zip(chunks, vectors, strict=True)
        ],
    )
    return await _result(conn, "loaded", version_id)


async def _result(
    conn: AsyncConnection, status: Literal["loaded", "unchanged"], version_id: UUID
) -> IngestResult:
    # The same order the trigger on tenants uses to pin a new sandbox (migration 0005).
    newest = (
        await conn.execute(
            select(HandbookVersion.id, HandbookVersion.label)
            .where(HandbookVersion.published_at.is_not(None))
            .order_by(
                HandbookVersion.published_at.desc(),
                HandbookVersion.created_at.desc(),
                HandbookVersion.id.desc(),
            )
            .limit(1)
        )
    ).one_or_none()
    if newest is None:
        return IngestResult(status, version_id, current=False, current_label=None)
    return IngestResult(
        status, version_id, current=newest.id == version_id, current_label=newest.label
    )


def _chunk_row(
    version_id: UUID,
    section_id: UUID,
    section_key: str,
    section_title: str,
    chunk: Chunk,
    vector: list[float],
) -> dict[str, object]:
    return {
        "version_id": version_id,
        "section_id": section_id,
        # Copies the generated search column reads, because it can see only its own row.
        "section_key": section_key,
        "section_title": section_title,
        "position": chunk.position,
        "heading": chunk.heading,
        "passage_ids": list(chunk.passage_ids),
        "text": chunk.text,
        "embedding": vector,
    }


def _check_vectors(vectors: list[list[float]], expected: int) -> None:
    if len(vectors) != expected:
        msg = f"The embedder returned {len(vectors)} vectors for {expected} chunks."
        raise IngestError(msg)
    for vector in vectors:
        if len(vector) != DIMENSIONS:
            msg = f"An embedding has {len(vector)} numbers; every one must have {DIMENSIONS}."
            raise IngestError(msg)
        if not is_unit_vector(vector):
            msg = "An embedding is not a finite unit vector, so it can't be loaded."
            raise IngestError(msg)
