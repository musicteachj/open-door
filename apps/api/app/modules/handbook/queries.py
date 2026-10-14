"""The handbook's database queries: who a section applies to, and the two searches.

Everything the asker or the question supplies is a bound parameter. Nothing here builds SQL from
text. The tables are global (no tenant), and the API's login can only read them.
"""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import (
    ColumnElement,
    Row,
    Select,
    and_,
    bindparam,
    cast,
    func,
    literal_column,
    or_,
    select,
)
from sqlalchemy.dialects.postgresql import TSQUERY
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import HandbookChunk, HandbookSection
from app.domain.handbook.applicability import Asker
from app.domain.retrieval import ChunkKey

CANDIDATE_LIMIT = 20
ENGLISH: ColumnElement[object] = literal_column("'english'::regconfig")


def _allows(key: str, value: str) -> ColumnElement[bool]:
    """One audience list admits `value`: the list is missing, empty, or contains it."""
    listed = HandbookSection.audience[key]
    return or_(
        listed.is_(None),
        func.jsonb_array_length(listed) == 0,
        listed.contains([value]),
    )


def applies_to(asker: Asker) -> ColumnElement[bool]:
    """The SQL twin of `applicability.applies`, on `handbook_sections.audience`.

    A test compares the two for every section against every state, employment type, and location
    in the seed, so they can't drift apart.
    """
    return and_(
        _allows("states", asker.state),
        _allows("employmentTypes", asker.employment_type),
        _allows("locations", asker.location_code),
    )


def _keys(version_id: UUID, asker: Asker) -> Select[UUID, UUID, int, int]:
    """Every chunk of the version's applicable sections, as the columns of a `ChunkKey`."""
    return (
        select(
            HandbookChunk.id,
            HandbookChunk.section_id,
            HandbookSection.position,
            HandbookChunk.position,
        )
        .join(HandbookSection, HandbookSection.id == HandbookChunk.section_id)
        .where(
            HandbookChunk.version_id == version_id,
            HandbookSection.version_id == version_id,
            applies_to(asker),
        )
    )


def _or_query(query: str) -> ColumnElement[object]:
    """A tsquery that matches any of the question's own lexemes.

    The database lexes the question, so stop words ("how", "do") drop out and the rest are
    stemmed the way the chunks are. Each lexeme is quoted, so punctuation in one (an address, a
    URL) can't be read as tsquery syntax. A question of only stop words has no lexemes, so
    `string_agg` gives NULL and `search @@ NULL` matches nothing. The question is a bound
    parameter throughout.
    """
    lexemes = func.unnest(
        func.tsvector_to_array(func.to_tsvector(ENGLISH, bindparam("question", query)))
    ).column_valued("lexeme")
    escaped = func.replace(func.replace(lexemes, "\\", "\\\\"), "'", "''")
    quoted = func.concat("'", escaped, "'")
    joined = select(func.string_agg(quoted, " | ")).scalar_subquery()
    # mypy's SQLAlchemy stubs type TSQUERY as a class, not the TypeEngine that cast() expects.
    return cast(joined, TSQUERY)  # type: ignore[arg-type]


async def fulltext_candidates(
    db: AsyncSession, version_id: UUID, asker: Asker, query: str, limit: int = CANDIDATE_LIMIT
) -> list[ChunkKey]:
    """Chunks matching any word of `query`, best first by `ts_rank_cd`. Ties go to the earlier
    section, then the earlier chunk."""
    tsquery = _or_query(query)
    statement = (
        _keys(version_id, asker)
        .where(HandbookChunk.search.op("@@")(tsquery))
        .order_by(
            func.ts_rank_cd(HandbookChunk.search, tsquery).desc(),
            HandbookSection.position,
            HandbookChunk.position,
        )
        .limit(limit)
    )
    return _as_keys((await db.execute(statement)).all())


async def vector_candidates(
    db: AsyncSession,
    version_id: UUID,
    asker: Asker,
    embedding: Sequence[float],
    limit: int = CANDIDATE_LIMIT,
) -> list[ChunkKey]:
    """The chunks nearest `embedding` by cosine distance, nearest first. An exact scan: there is
    no approximate index, so the order never varies."""
    distance = HandbookChunk.embedding.cosine_distance(list(embedding))
    statement = (
        _keys(version_id, asker)
        .order_by(distance, HandbookSection.position, HandbookChunk.position)
        .limit(limit)
    )
    return _as_keys((await db.execute(statement)).all())


def _as_keys(rows: Sequence[Row[UUID, UUID, int, int]]) -> list[ChunkKey]:
    return [ChunkKey(*row) for row in rows]
