"""The two candidate searches, over the real ingested handbook and a throwaway second version."""

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from app.ai.embeddings import FakeEmbedder
from app.db.models import HandbookSection
from app.domain.handbook.applicability import Asker
from app.domain.retrieval import ChunkKey
from app.modules.handbook.load import ingest
from app.modules.handbook.queries import fulltext_candidates, vector_candidates
from app.modules.handbook.source import read_handbook

pytestmark = pytest.mark.integration

TEXAS = Asker("TX", "hourly", "aus")
OAKLAND = Asker("CA", "salaried", "oak")
FIXTURE = Path(__file__).parent.parent / "fixtures" / "handbook"


async def current_version(session: AsyncSession) -> UUID:
    version_id = await session.scalar(
        text(
            "SELECT id FROM handbook_versions WHERE published_at IS NOT NULL"
            " ORDER BY published_at DESC, created_at DESC, id DESC LIMIT 1"
        )
    )
    assert isinstance(version_id, UUID)
    return version_id


async def keys_of(session: AsyncSession, chunk_keys: Sequence[ChunkKey]) -> list[str]:
    ids = [k.section_id for k in chunk_keys]
    rows = (
        await session.execute(
            select(HandbookSection.id, HandbookSection.section_key).where(
                HandbookSection.id.in_(ids)
            )
        )
    ).all()
    by_id = {row.id: row.section_key for row in rows}
    return [by_id[i] for i in ids]


async def test_a_natural_question_finds_the_section_even_though_some_words_are_nowhere(
    app_engine: AsyncEngine,
) -> None:
    async with AsyncSession(app_engine) as session:
        version_id = await current_version(session)

        found = await fulltext_candidates(
            session, version_id, TEXAS, "How much sick leave do I get?"
        )

        assert "4.3" in await keys_of(session, found)


async def test_a_question_of_only_stop_words_matches_nothing(app_engine: AsyncEngine) -> None:
    async with AsyncSession(app_engine) as session:
        version_id = await current_version(session)

        assert await fulltext_candidates(session, version_id, TEXAS, "how do I do this?") == []


async def test_tsquery_syntax_in_a_question_is_just_words(app_engine: AsyncEngine) -> None:
    async with AsyncSession(app_engine) as session:
        version_id = await current_version(session)

        for odd in ["sick & ! ( leave", "a:b | 'c' \\ d", "http://x.example/a?b=1:2", "'; DROP--"]:
            await fulltext_candidates(session, version_id, TEXAS, odd)


async def test_the_full_text_search_is_deterministic(app_engine: AsyncEngine) -> None:
    async with AsyncSession(app_engine) as session:
        version_id = await current_version(session)

        first = await fulltext_candidates(session, version_id, OAKLAND, "paid sick leave")

        assert first
        assert len(first) <= 20
        assert await fulltext_candidates(session, version_id, OAKLAND, "paid sick leave") == first


async def test_the_limit_caps_the_results(app_engine: AsyncEngine) -> None:
    async with AsyncSession(app_engine) as session:
        version_id = await current_version(session)

        found = await fulltext_candidates(session, version_id, TEXAS, "leave pay work", limit=3)

        assert len(found) == 3


async def test_the_vector_order_is_deterministic_with_the_fake_embedder(
    app_engine: AsyncEngine,
) -> None:
    [vector] = await FakeEmbedder().embed(["How much sick leave do I get?"], input_type="query")
    async with AsyncSession(app_engine) as session:
        version_id = await current_version(session)

        first = await vector_candidates(session, version_id, TEXAS, vector)

        assert len(first) == 20
        assert len({k.chunk_id for k in first}) == 20
        assert await vector_candidates(session, version_id, TEXAS, vector) == first
        assert len(await vector_candidates(session, version_id, TEXAS, vector, limit=5)) == 5


async def test_the_nearest_chunk_is_the_one_whose_vector_is_the_query(
    app_engine: AsyncEngine,
) -> None:
    async with AsyncSession(app_engine) as session:
        version_id = await current_version(session)
        row = (
            await session.execute(
                text(
                    "SELECT c.id, c.embedding::text AS embedding FROM handbook_chunks c"
                    " JOIN handbook_sections s ON s.id = c.section_id"
                    " WHERE c.version_id = :v AND s.audience = '{}'::jsonb OR"
                    " (c.version_id = :v AND s.section_key = '1.1') LIMIT 1"
                ),
                {"v": version_id},
            )
        ).one()
        vector = [float(x) for x in row.embedding.strip("[]").split(",")]

        found = await vector_candidates(session, version_id, TEXAS, vector, limit=1)

        assert [k.chunk_id for k in found] == [row.id]


@pytest.mark.parametrize("asker", [TEXAS, OAKLAND, Asker("CO", "salaried", "den")])
async def test_both_searches_stay_inside_the_applicable_sections(
    app_engine: AsyncEngine, asker: Asker
) -> None:
    [vector] = await FakeEmbedder().embed(["sick leave overtime meal breaks"], input_type="query")
    other_states = {"CA", "CO", "TX"} - {asker.state}
    async with AsyncSession(app_engine) as session:
        version_id = await current_version(session)
        full = await fulltext_candidates(session, version_id, asker, "sick leave overtime meal", 50)
        near = await vector_candidates(session, version_id, asker, vector, 500)

        for found in (full, near):
            section_keys = await keys_of(session, found)
            assert section_keys
            assert not any(
                key.startswith(f"{state}-") for key in section_keys for state in other_states
            )
        # With no limit in the way, every applicable section's chunks are in the vector results.
        applicable = await session.scalar(
            text(
                "SELECT count(*) FROM handbook_chunks c JOIN handbook_sections s"
                " ON s.id = c.section_id WHERE c.version_id = :v AND ("
                " s.audience->'states' IS NULL OR jsonb_array_length(s.audience->'states') = 0"
                " OR s.audience->'states' @> to_jsonb(CAST(:state AS text)))"
                " AND (s.audience->'employmentTypes' IS NULL"
                " OR jsonb_array_length(s.audience->'employmentTypes') = 0"
                " OR s.audience->'employmentTypes' @> to_jsonb(CAST(:kind AS text)))"
                " AND (s.audience->'locations' IS NULL"
                " OR jsonb_array_length(s.audience->'locations') = 0"
                " OR s.audience->'locations' @> to_jsonb(CAST(:loc AS text)))"
            ),
            {
                "v": version_id,
                "state": asker.state,
                "kind": asker.employment_type,
                "loc": asker.location_code,
            },
        )
        assert len(near) == applicable


@asynccontextmanager
async def second_version(engine: AsyncEngine) -> AsyncIterator[tuple[AsyncConnection, UUID]]:
    """A second, published version of a small handbook, loaded as the owner and rolled back."""
    async with engine.connect() as connection:
        transaction = await connection.begin()
        try:
            handbook = replace(read_handbook(FIXTURE), version=f"test-{uuid4()}")
            result = await ingest(connection, handbook, FakeEmbedder(), publish=True)
            yield connection, result.version_id
        finally:
            await transaction.rollback()


async def test_another_versions_chunks_never_appear(owner_engine: AsyncEngine) -> None:
    [vector] = await FakeEmbedder().embed(["sick leave"], input_type="query")
    async with second_version(owner_engine) as (connection, new_id):
        # Pinned to the new version, the real handbook's chunks must not appear...
        session = AsyncSession(bind=connection)
        old_id = await session.scalar(
            text("SELECT id FROM handbook_versions WHERE id <> :new AND label = '2026.10'"),
            {"new": new_id},
        )
        assert isinstance(old_id, UUID)
        for version_id, other_id in ((new_id, old_id), (old_id, new_id)):
            found = [
                *await fulltext_candidates(session, version_id, TEXAS, "sick leave pay", 100),
                *await vector_candidates(session, version_id, TEXAS, vector, 500),
            ]
            ids = {k.chunk_id for k in found}
            assert ids
            wrong = await session.scalar(
                text(
                    "SELECT count(*) FROM handbook_chunks"
                    " WHERE id = ANY(:ids) AND version_id = :other"
                ),
                {"ids": list(ids), "other": other_id},
            )
            assert wrong == 0
