"""Loading a handbook version, as the database owner, inside a transaction that never commits."""

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.ai.embeddings import DIMENSIONS, Embedder, FakeEmbedder, InputType
from app.db.models import HandbookChunk, HandbookSection, HandbookVersion
from app.domain.handbook.chunks import chunks_for
from app.domain.handbook.models import Handbook
from app.modules.handbook import load
from app.modules.handbook.load import IngestError, ingest
from app.modules.handbook.source import read_handbook

pytestmark = pytest.mark.integration

FIXTURE = Path(__file__).parent.parent / "fixtures" / "handbook"


def fixture_handbook() -> Handbook:
    # A fresh label each time, so a handbook already loaded in the development database can't
    # collide with it.
    return replace(read_handbook(FIXTURE), version=f"test-{uuid4()}")


@asynccontextmanager
async def rolled_back(engine: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    async with engine.connect() as connection:
        transaction = await connection.begin()
        try:
            yield connection
        finally:
            await transaction.rollback()


async def count(connection: AsyncConnection, table: object) -> int:
    return int(await connection.scalar(select(func.count()).select_from(table)) or 0)  # type: ignore[arg-type]


async def counts(connection: AsyncConnection) -> tuple[int, int, int]:
    return (
        await count(connection, HandbookVersion),
        await count(connection, HandbookSection),
        await count(connection, HandbookChunk),
    )


class WrongSize:
    async def embed(self, texts: Sequence[str], *, input_type: InputType) -> list[list[float]]:
        vectors = await FakeEmbedder().embed(texts, input_type=input_type)
        vectors[-1] = vectors[-1][:10]
        return vectors


class NotANumber:
    """Right size, but pgvector refuses NaN, so the insert fails after the earlier rows went in."""

    async def embed(self, texts: Sequence[str], *, input_type: InputType) -> list[list[float]]:
        vectors = await FakeEmbedder().embed(texts, input_type=input_type)
        vectors[-1] = [float("nan")] * DIMENSIONS
        return vectors


class Counting(FakeEmbedder):
    def __init__(self) -> None:
        self.calls: list[tuple[int, str]] = []

    async def embed(self, texts: Sequence[str], *, input_type: InputType) -> list[list[float]]:
        self.calls.append((len(texts), input_type))
        return await super().embed(texts, input_type=input_type)


async def test_a_handbook_loads_with_its_sections_blocks_chunks_and_embeddings(
    owner_engine: AsyncEngine,
) -> None:
    handbook = fixture_handbook()
    embedder = Counting()
    async with rolled_back(owner_engine) as connection:
        before = await counts(connection)
        result = await ingest(connection, handbook, embedder, publish=False)
        assert result.status == "loaded"

        version = (
            await connection.execute(
                select(HandbookVersion).where(HandbookVersion.id == result.version_id)
            )
        ).one()
        assert version.label == handbook.version
        assert version.embedding_model == "voyage-4"
        assert version.embedding_dimensions == DIMENSIONS
        assert version.published_at is None
        assert version.updated_on == handbook.updated_on
        assert version.title == handbook.title
        assert version.group_names == {
            "chapters": {"1": "Welcome", "4": "Time off"},
            "addenda": {"CA": "California addendum", "TX": "Texas addendum"},
        }

        sections = (
            await connection.execute(
                select(HandbookSection)
                .where(HandbookSection.version_id == result.version_id)
                .order_by(HandbookSection.position)
            )
        ).all()
        assert [row.section_key for row in sections] == [s.id for s in handbook.sections]
        assert [row.position for row in sections] == list(range(len(sections)))
        first = handbook.sections[0]
        assert sections[0].title == first.title
        assert sections[0].audience == first.audience.to_json()
        assert set(sections[0].audience) == {"states", "employmentTypes", "locations"}
        assert sections[0].blocks  # the structured body, as JSON

        expected = sum(len(chunks_for(section)) for section in handbook.sections)
        chunks = (
            await connection.execute(
                select(HandbookChunk).where(HandbookChunk.version_id == result.version_id)
            )
        ).all()
        assert len(chunks) == expected > 0
        assert embedder.calls == [(expected, "document")]
        by_id = {row.id: row for row in sections}
        for chunk in chunks:
            assert chunk.section_key == by_id[chunk.section_id].section_key
            assert chunk.section_title == by_id[chunk.section_id].title
            assert chunk.passage_ids
            assert len(chunk.embedding) == DIMENSIONS

        assert await counts(connection) == (
            before[0] + 1,
            before[1] + len(sections),
            before[2] + expected,
        )


async def test_the_search_column_is_filled_from_the_text(owner_engine: AsyncEngine) -> None:
    handbook = fixture_handbook()
    async with rolled_back(owner_engine) as connection:
        result = await ingest(connection, handbook, FakeEmbedder(), publish=False)
        row = (
            await connection.execute(
                select(HandbookChunk.section_key, HandbookChunk.text)
                .where(HandbookChunk.version_id == result.version_id)
                .where(HandbookChunk.search.op("@@")(func.websearch_to_tsquery("english", "sick")))
            )
        ).first()
        assert row is not None


async def test_publishing_sets_the_publish_time(owner_engine: AsyncEngine) -> None:
    async with rolled_back(owner_engine) as connection:
        result = await ingest(connection, fixture_handbook(), FakeEmbedder(), publish=True)
        published = await connection.scalar(
            select(HandbookVersion.published_at).where(HandbookVersion.id == result.version_id)
        )
        assert published is not None


async def test_a_second_run_is_unchanged_and_writes_nothing(owner_engine: AsyncEngine) -> None:
    handbook = fixture_handbook()
    async with rolled_back(owner_engine) as connection:
        first = await ingest(connection, handbook, FakeEmbedder(), publish=False)
        after_first = await counts(connection)
        embedder = Counting()
        second = await ingest(connection, handbook, embedder, publish=False)
        assert (second.status, second.version_id) == ("unchanged", first.version_id)
        # The vectors are part of the version's hash, so they are looked up (from the cache, in
        # production) before the comparison, but nothing is written.
        assert len(embedder.calls) == 1
        assert await counts(connection) == after_first


async def test_publishing_an_unpublished_version_that_is_otherwise_unchanged(
    owner_engine: AsyncEngine,
) -> None:
    handbook = fixture_handbook()
    async with rolled_back(owner_engine) as connection:
        first = await ingest(connection, handbook, FakeEmbedder(), publish=False)
        second = await ingest(connection, handbook, FakeEmbedder(), publish=True)
        assert (second.status, second.version_id) == ("unchanged", first.version_id)
        published = await connection.scalar(
            select(HandbookVersion.published_at).where(HandbookVersion.id == first.version_id)
        )
        assert published is not None
        # Publishing again keeps the first publish time.
        again = await ingest(connection, handbook, FakeEmbedder(), publish=True)
        assert again.status == "unchanged"
        assert (
            await connection.scalar(
                select(HandbookVersion.published_at).where(HandbookVersion.id == first.version_id)
            )
            == published
        )


async def test_a_changed_file_under_the_same_label_asks_for_a_new_label(
    owner_engine: AsyncEngine,
) -> None:
    handbook = fixture_handbook()
    edited_files = (
        replace(handbook.files[0], text=handbook.files[0].text + "\nAn extra line.\n"),
        *handbook.files[1:],
    )
    edited = replace(handbook, files=edited_files)
    async with rolled_back(owner_engine) as connection:
        await ingest(connection, handbook, FakeEmbedder(), publish=False)
        with pytest.raises(IngestError, match="new label") as caught:
            await ingest(connection, edited, FakeEmbedder(), publish=False)
        assert handbook.version in str(caught.value)
        assert "handbook.yaml" in str(caught.value)


class NotUnit:
    async def embed(self, texts: Sequence[str], *, input_type: InputType) -> list[list[float]]:
        vectors = await FakeEmbedder().embed(texts, input_type=input_type)
        vectors[-1] = [3.0e38] + [0.0] * (DIMENSIONS - 1)
        return vectors


@pytest.mark.parametrize("embedder", [NotUnit(), NotANumber()])
async def test_a_vector_that_is_not_a_finite_unit_vector_is_refused_before_any_row_goes_in(
    owner_engine: AsyncEngine, embedder: Embedder
) -> None:
    async with rolled_back(owner_engine) as connection:
        before = await counts(connection)
        with pytest.raises(IngestError, match="unit"):
            await ingest(connection, fixture_handbook(), embedder, publish=False)
        assert await counts(connection) == before


async def test_changing_only_a_vector_under_the_same_label_asks_for_a_new_label(
    owner_engine: AsyncEngine,
) -> None:
    class OneVectorEdited:
        async def embed(self, texts: Sequence[str], *, input_type: InputType) -> list[list[float]]:
            vectors = await FakeEmbedder().embed(texts, input_type=input_type)
            vectors[0] = FakeEmbedder._vector("another text")
            return vectors

    handbook = fixture_handbook()
    async with rolled_back(owner_engine) as connection:
        await ingest(connection, handbook, FakeEmbedder(), publish=False)
        with pytest.raises(IngestError, match="new label"):
            await ingest(connection, handbook, OneVectorEdited(), publish=False)


async def test_a_wrong_sized_vector_is_refused_before_any_row_goes_in(
    owner_engine: AsyncEngine,
) -> None:
    async with rolled_back(owner_engine) as connection:
        before = await counts(connection)
        with pytest.raises(IngestError, match=str(DIMENSIONS)):
            await ingest(connection, fixture_handbook(), WrongSize(), publish=False)
        assert await counts(connection) == before


async def test_a_failure_partway_through_leaves_no_rows(
    owner_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The vector check would refuse NaN first, so switch it off to reach the database's own refusal.
    monkeypatch.setattr(load, "_check_vectors", lambda *_: None)
    async with rolled_back(owner_engine) as connection:
        before = await counts(connection)
        savepoint = await connection.begin_nested()
        with pytest.raises(DBAPIError):
            await ingest(connection, fixture_handbook(), NotANumber(), publish=True)
        await savepoint.rollback()
        assert await counts(connection) == before


async def test_values_are_bound_not_pasted_into_the_sql(owner_engine: AsyncEngine) -> None:
    hostile = "x'); DROP TABLE handbook_versions; --"
    handbook = replace(fixture_handbook(), version=hostile)
    async with rolled_back(owner_engine) as connection:
        result = await ingest(connection, handbook, FakeEmbedder(), publish=False)
        label = await connection.scalar(
            select(HandbookVersion.label).where(HandbookVersion.id == result.version_id)
        )
        assert label == hostile
        assert await connection.scalar(text("SELECT to_regclass('handbook_versions')")) is not None


async def test_a_published_version_keeps_its_original_publish_time(
    owner_engine: AsyncEngine,
) -> None:
    handbook = fixture_handbook()
    past = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    async with rolled_back(owner_engine) as connection:
        first = await ingest(connection, handbook, FakeEmbedder(), publish=True)
        # now() is fixed inside one transaction, so only a fixed past time can show a re-publish.
        await connection.execute(
            update(HandbookVersion)
            .where(HandbookVersion.id == first.version_id)
            .values(published_at=past)
        )
        again = await ingest(connection, handbook, FakeEmbedder(), publish=True)
        assert (again.status, again.version_id) == ("unchanged", first.version_id)
        assert (
            await connection.scalar(
                select(HandbookVersion.published_at).where(HandbookVersion.id == first.version_id)
            )
            == past
        )


async def test_an_older_published_version_is_unchanged_but_not_current(
    owner_engine: AsyncEngine,
) -> None:
    first = fixture_handbook()
    edited_files = (
        replace(first.files[0], text=first.files[0].text + "\nAn extra line.\n"),
        *first.files[1:],
    )
    second = replace(first, version=f"test-{uuid4()}", files=edited_files)
    async with rolled_back(owner_engine) as connection:
        one = await ingest(connection, first, FakeEmbedder(), publish=True)
        two = await ingest(connection, second, FakeEmbedder(), publish=True)
        # Fixed times, far ahead of any version really published in the development database.
        for version_id, when in (
            (one.version_id, datetime(2099, 1, 1, tzinfo=UTC)),
            (two.version_id, datetime(2099, 2, 1, tzinfo=UTC)),
        ):
            await connection.execute(
                update(HandbookVersion)
                .where(HandbookVersion.id == version_id)
                .values(published_at=when)
            )

        older = await ingest(connection, first, FakeEmbedder(), publish=True)
        assert (older.status, older.version_id) == ("unchanged", one.version_id)
        assert older.current is False
        assert older.current_label == second.version
        # It was left as it was: no new publish time.
        assert await connection.scalar(
            select(HandbookVersion.published_at).where(HandbookVersion.id == one.version_id)
        ) == datetime(2099, 1, 1, tzinfo=UTC)

        newest = await ingest(connection, second, FakeEmbedder(), publish=True)
        assert (newest.status, newest.current) == ("unchanged", True)
        assert newest.current_label == second.version
