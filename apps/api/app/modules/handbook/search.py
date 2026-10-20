"""`search_handbook`: hybrid search over one handbook version, for one asker.

This is the service Phase 4's tool calls. It has no HTTP route in Phase 3. Two searches run over
the applicable sections of the version (full-text on the question's own words, and the vector
search on its embedding) and reciprocal-rank fusion merges them. If the embedding fails, the
full-text results stand alone and the result says so.

The caller embeds the question first (`embed_query`), before opening a database session, then
passes the vector in. The caller supplies `version_id` and `asker`. Both must come from the server
session: the asker from `load_asker`, the version from `pinned_version_id`. Never from a request or
a tool input.
"""

import logging
import unicodedata
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import DIMENSIONS, Embedder, is_unit_vector
from app.db.models import HandbookChunk, HandbookSection, HandbookVersion, Location, Tenant
from app.domain.handbook.applicability import Asker, audience_label
from app.domain.handbook.models import Audience
from app.domain.retrieval import MAX_QUERY_CHARACTERS, Fused, fuse
from app.modules.handbook.queries import fulltext_candidates, vector_candidates

logger = logging.getLogger(__name__)

# Control and format characters (they include the excerpt markers), lone surrogates, private use,
# and unassigned code points. A lone surrogate can't be encoded for the database at all.
_DROPPED_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co", "Cn"})


@dataclass(frozen=True, slots=True)
class Hit:
    """One chunk, with what Phase 4 needs for a `search_result` block: `deep_link` is its
    `source`, `passages` are its content blocks."""

    section_id: str
    title: str
    # The chapter's name, or the addendum's ("California addendum").
    group_name: str
    audience_label: str
    last_updated: date
    passage_ids: tuple[str, ...]
    passages: tuple[str, ...]
    deep_link: str
    # 1-based place in each search's results; None where the search didn't return it.
    fulltext_rank: int | None
    vector_rank: int | None


@dataclass(frozen=True, slots=True)
class SearchResult:
    mode: Literal["hybrid", "fulltext"]
    # The location code whose policies the search used: the asker's own unless one was asked for.
    location_used: str
    hits: tuple[Hit, ...]


async def pinned_version_id(db: AsyncSession) -> UUID | None:
    """The handbook version the current tenant is pinned to, or None for an old sandbox.

    Read it from the session's own tenant row, under row-level security. Routes and tools take the
    version from here and never from a request, so no input can name another version.
    """
    return (await db.scalars(select(Tenant.handbook_version_id))).first()


def clean_query(query: str, *, max_characters: int | None = MAX_QUERY_CHARACTERS) -> str:
    """The question with control, format, surrogate, private-use and unassigned characters turned
    into spaces (the excerpt markers among them), whitespace collapsed, and the length capped (not
    with `max_characters=None`, for a caller that checks the length itself). An empty result is
    refused."""
    spaced = "".join(
        " " if unicodedata.category(char) in _DROPPED_CATEGORIES else char for char in query
    )
    collapsed = " ".join(spaced.split())
    cleaned = (collapsed if max_characters is None else collapsed[:max_characters]).strip()
    if not cleaned:
        msg = "The search query is empty."
        raise ValueError(msg)
    return cleaned


async def embed_query(embedder: Embedder, query: str) -> list[float] | None:
    """The embedding of `query`, or None if embedding failed.

    **Call this before opening the database session**, so a slow embedding call never holds a
    transaction or a connection. It cleans the query the way `search_handbook` does, so both use
    the same string, and raises `ValueError` for an empty one. Any failure from the embedder, or a
    vector of the wrong size or length, logs one warning with the exception type and no query text,
    and returns None. Pass the result to `search_handbook` either way.
    """
    question = clean_query(query)
    try:
        [vector] = await embedder.embed([question], input_type="query")
        if len(vector) != DIMENSIONS or not is_unit_vector(vector):
            msg = "the embedder returned an unusable vector"
            raise ValueError(msg)
    except Exception as error:
        # The type only: a message could repeat the question.
        logger.warning(
            "Query embedding failed, so the search is full-text only: %s", type(error).__name__
        )
        return None
    return vector


async def search_handbook(
    db: AsyncSession,
    *,
    version_id: UUID,
    asker: Asker,
    query: str,
    query_vector: list[float] | None,
    location_code: str | None = None,
    limit: int = 5,
) -> SearchResult:
    """The `limit` best chunks for `query`.

    `query_vector` is `embed_query`'s result, computed before the session was opened. With None the
    search is full-text only and the result's mode says so.

    `location_code` answers "what's the California policy?" for someone elsewhere: it replaces the
    asker's state and location for the filter and keeps their employment type. An unknown code is
    a `ValueError`.
    """
    question = clean_query(query)

    locations = {location.code: location for location in (await db.scalars(select(Location))).all()}
    if location_code is not None:
        chosen = locations.get(location_code)
        if chosen is None:
            msg = "Unknown location code."
            raise ValueError(msg)
        asker = Asker(chosen.state, asker.employment_type, chosen.code)

    fulltext = await fulltext_candidates(db, version_id, asker, question)
    nearest = (
        [] if query_vector is None else await vector_candidates(db, version_id, asker, query_vector)
    )
    top = fuse(fulltext, nearest)[:limit]

    names = {code: location.name for code, location in locations.items()}
    hits = await _hits(db, version_id, top, names)
    mode: Literal["hybrid", "fulltext"] = "fulltext" if query_vector is None else "hybrid"
    return SearchResult(mode, asker.location_code, hits)


async def _hits(
    db: AsyncSession, version_id: UUID, fused: list[Fused], names: dict[str, str]
) -> tuple[Hit, ...]:
    if not fused:
        return ()
    group_names = await db.scalar(
        select(HandbookVersion.group_names).where(HandbookVersion.id == version_id)
    )
    group_names = group_names or {}
    rows = (
        await db.execute(
            select(HandbookChunk.id, HandbookChunk.passage_ids, HandbookSection)
            .join(HandbookSection, HandbookSection.id == HandbookChunk.section_id)
            .where(HandbookChunk.id.in_([f.key.chunk_id for f in fused]))
        )
    ).all()
    by_chunk = {row.id: row for row in rows}
    hits = []
    for item in fused:
        row = by_chunk[item.key.chunk_id]
        section: HandbookSection = row.HandbookSection
        passage_ids = tuple(row.passage_ids)
        texts = passage_texts(section.blocks)
        audience = section.audience
        hits.append(
            Hit(
                section_id=section.section_key,
                title=section.title,
                group_name=group_name(section, group_names),
                audience_label=audience_label(
                    Audience.from_json(audience),
                    names,
                ),
                last_updated=section.updated_on,
                passage_ids=passage_ids,
                passages=tuple(texts[passage_id] for passage_id in passage_ids),
                deep_link=f"/handbook/{section.section_key}?passage={passage_ids[0]}",
                fulltext_rank=item.ranks[0],
                vector_rank=item.ranks[1],
            )
        )
    return tuple(hits)


def group_name(section: HandbookSection, group_names: dict[str, dict[str, str]]) -> str:
    """The chapter's name, or the addendum's, from the version's own `group_names`."""
    if section.kind == "addendum":
        return group_names.get("addenda", {}).get(section.addendum_state or "", "")
    return group_names.get("chapters", {}).get(str(section.chapter), "")


def passage_texts(blocks: list[dict[str, Any]]) -> dict[str, str]:
    """Each passage as plain text: a paragraph's words, or a list as one `- item` line per item
    (the same text the chunks were built from)."""
    texts: dict[str, str] = {}
    for block in blocks:
        if block.get("type") != "passage":
            continue
        if block["kind"] == "paragraph":
            texts[block["id"]] = _plain(block["inlines"])
        else:
            texts[block["id"]] = "\n".join(f"- {_plain(item)}" for item in block["items"])
    return texts


def _plain(inlines: list[dict[str, Any]]) -> str:
    return "".join(inline["text"] for inline in inlines)
