"""`search_handbook` end to end, for the seed's Texas, California, and Colorado people."""

import logging
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from uuid import UUID, uuid5

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.ai.embeddings import DIMENSIONS, FakeEmbedder, InputType
from app.db.models import HandbookSection
from app.db.tenancy import TenantContext, tenant_session
from app.domain.handbook.applicability import Asker, applies
from app.domain.handbook.models import Audience
from app.domain.retrieval import MAX_QUERY_CHARACTERS
from app.modules.handbook.asker import load_asker
from app.modules.handbook.search import (
    clean_query,
    embed_query,
    pinned_version_id,
    search_handbook,
)
from app.modules.identity.actor import load_actor
from app.modules.sandbox.seed import SeedCompany

pytestmark = pytest.mark.integration

SICK = "How much sick leave do I get?"


@asynccontextmanager
async def as_persona(
    engine: AsyncEngine, company: SeedCompany, persona: str
) -> AsyncIterator[tuple[AsyncSession, Asker, UUID]]:
    tenant_id = company.tenant_id
    async with tenant_session(engine, TenantContext(tenant_id, None)) as session:
        actor = await load_actor(session, tenant_id, uuid5(tenant_id, f"person:{persona}"))
        assert actor is not None
        version_id = await pinned_version_id(session)
        assert version_id is not None
        yield session, await load_asker(session, actor), version_id


class Raising:
    async def embed(self, texts: Sequence[str], *, input_type: InputType) -> list[list[float]]:
        msg = f"boom while embedding {texts[0]}"
        raise RuntimeError(msg)


class Spy:
    """Records how many statements the engine had run when it was asked to embed."""

    def __init__(self, statements: list[str]) -> None:
        self.statements = statements
        self.seen_at: list[int] = []
        self.input_types: list[str] = []
        self.texts: list[str] = []

    async def embed(self, texts: Sequence[str], *, input_type: InputType) -> list[list[float]]:
        self.seen_at.append(len(self.statements))
        self.input_types.append(input_type)
        self.texts.append(texts[0])
        return await FakeEmbedder().embed(texts, input_type=input_type)


async def test_the_same_question_gives_the_same_hits_in_the_same_order(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    async with as_persona(app_engine, seeded_sandbox, "mateo") as (db, asker, version_id):
        results = [
            await search_handbook(
                db,
                version_id=version_id,
                asker=asker,
                query=SICK,
                query_vector=await embed_query(FakeEmbedder(), SICK),
            )
            for _ in range(3)
        ]

    assert results[0] == results[1] == results[2]
    first = results[0]
    assert first.mode == "hybrid"
    assert first.location_used == "aus"
    assert 1 <= len(first.hits) <= 5
    assert any(hit.section_id == "4.3" for hit in first.hits)
    assert not any(hit.section_id.startswith(("CA-", "CO-", "GA-")) for hit in first.hits)
    assert first.hits[0].fulltext_rank is not None


async def test_a_location_code_answers_for_that_location_and_keeps_the_employment_type(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    async with as_persona(app_engine, seeded_sandbox, "mateo") as (db, asker, version_id):
        assert asker == Asker("TX", "hourly", "aus")

        oak = await search_handbook(
            db,
            version_id=version_id,
            asker=asker,
            query=SICK,
            query_vector=await embed_query(FakeEmbedder(), SICK),
            location_code="oak",
            limit=10,
        )

    assert oak.location_used == "oak"
    assert "CA-4.3" in {hit.section_id for hit in oak.hits}
    assert not any(hit.section_id.startswith(("CO-", "TX-")) for hit in oak.hits)


async def test_an_unknown_location_code_is_a_clear_error(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    async with as_persona(app_engine, seeded_sandbox, "mateo") as (db, asker, version_id):
        with pytest.raises(ValueError, match="Unknown location code"):
            await search_handbook(
                db,
                version_id=version_id,
                asker=asker,
                query=SICK,
                query_vector=await embed_query(FakeEmbedder(), SICK),
                location_code="nowhere",
            )


async def test_a_failing_embedder_falls_back_to_full_text_with_one_warning_and_no_query_text(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    async with as_persona(app_engine, seeded_sandbox, "mateo") as (db, asker, version_id):
        vector = await embed_query(Raising(), SICK)
        result = await search_handbook(
            db, version_id=version_id, asker=asker, query=SICK, query_vector=vector
        )

    assert result.mode == "fulltext"
    assert result.hits
    assert any(hit.section_id == "4.3" for hit in result.hits)
    assert all(hit.vector_rank is None and hit.fulltext_rank for hit in result.hits)
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "RuntimeError" in warnings[0].getMessage()
    assert "sick" not in caplog.text.lower()
    assert "boom" not in caplog.text


async def test_an_unusable_vector_also_falls_back(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    class Short:
        async def embed(self, texts: Sequence[str], *, input_type: InputType) -> list[list[float]]:
            return [[1.0] * (DIMENSIONS - 1)]

    async with as_persona(app_engine, seeded_sandbox, "mateo") as (db, asker, version_id):
        vector = await embed_query(Short(), SICK)
        assert vector is None
        result = await search_handbook(
            db, version_id=version_id, asker=asker, query=SICK, query_vector=vector
        )

    assert result.mode == "fulltext"


async def test_embedding_the_query_touches_the_database_not_at_all(
    app_engine: AsyncEngine,
) -> None:
    events: list[str] = []

    def statement(*args: object) -> None:
        events.append("statement")

    def checkout(*args: object) -> None:
        events.append("checkout")

    sync_engine = app_engine.sync_engine
    event.listen(sync_engine, "before_cursor_execute", statement)
    event.listen(sync_engine, "checkout", checkout)
    try:
        spy = Spy(events)
        vector = await embed_query(spy, SICK)
    finally:
        event.remove(sync_engine, "before_cursor_execute", statement)
        event.remove(sync_engine, "checkout", checkout)

    assert vector is not None
    assert spy.seen_at == [0]
    assert spy.input_types == ["query"]
    assert events == []


async def test_embed_query_cleans_the_query_and_refuses_an_empty_one() -> None:
    spy = Spy([])

    await embed_query(spy, "  sick\x00 leave ")

    assert spy.texts == ["sick leave"]
    with pytest.raises(ValueError, match="empty"):
        await embed_query(spy, "\x00")


async def test_a_missing_vector_means_a_full_text_result(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    async with as_persona(app_engine, seeded_sandbox, "mateo") as (db, asker, version_id):
        result = await search_handbook(
            db, version_id=version_id, asker=asker, query=SICK, query_vector=None
        )

    assert result.mode == "fulltext"


async def test_each_hit_links_to_its_first_passage_and_carries_the_passage_texts(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    async with as_persona(app_engine, seeded_sandbox, "marcus") as (db, asker, version_id):
        result = await search_handbook(
            db,
            version_id=version_id,
            asker=asker,
            query=SICK,
            # Full-text only: the fake embedder's vectors are noise that can crowd out the
            # addendum, and this test is about the shape of a hit, not the ranking.
            query_vector=None,
        )

    assert result.location_used == "oak"
    assert result.hits
    for hit in result.hits:
        assert hit.deep_link == f"/handbook/{hit.section_id}?passage={hit.passage_ids[0]}"
        assert len(hit.passages) == len(hit.passage_ids) >= 1
        assert all(passage.strip() for passage in hit.passages)
        assert hit.title
        assert hit.group_name
        assert hit.audience_label
    ca = next(hit for hit in result.hits if hit.section_id == "CA-4.3")
    assert ca.group_name == "California addendum"
    assert ca.audience_label == "California employees"
    assert any("sick" in passage.lower() for hit in result.hits for passage in hit.passages)
    company = [hit for hit in result.hits if not hit.section_id.startswith("CA-")]
    assert all(hit.group_name == "Time off" for hit in company if hit.section_id.startswith("4."))


async def test_the_pinned_version_comes_from_the_tenant_row_and_needs_a_tenant(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    async with as_persona(app_engine, seeded_sandbox, "mateo") as (db, _, version_id):
        assert await pinned_version_id(db) == version_id
    async with tenant_session(app_engine, TenantContext(None, None)) as nobody:
        assert await pinned_version_id(nobody) is None


async def test_a_question_that_is_only_control_characters_is_refused(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    async with as_persona(app_engine, seeded_sandbox, "mateo") as (db, asker, version_id):
        for empty in ["", "   ", "\x00\x1f\n\t", "​"]:
            with pytest.raises(ValueError, match="empty"):
                await search_handbook(
                    db, version_id=version_id, asker=asker, query=empty, query_vector=None
                )


# clean_query


def test_control_characters_become_spaces_and_whitespace_collapses() -> None:
    assert clean_query("  sick\x00leave⁣\n\n  pay\x1b ") == "sick leave pay"


def test_the_excerpt_markers_cannot_survive() -> None:
    assert clean_query("a\x01b\x02c") == "a b c"


def test_a_long_question_is_cut_to_the_cap() -> None:
    assert len(clean_query("word " * 400)) <= MAX_QUERY_CHARACTERS


@pytest.mark.parametrize(
    "odd",
    [chr(0xD800), chr(0xDFFF), chr(0xE000), chr(0xF0000), chr(0x0378), chr(0x10FFFF)],
    ids=["high-surrogate", "low-surrogate", "private-use", "plane-15", "unassigned", "last"],
)
def test_surrogates_private_use_and_unassigned_characters_are_dropped(odd: str) -> None:
    assert clean_query(f"sick {odd} leave") == "sick leave"
    with pytest.raises(ValueError, match="empty"):
        clean_query(odd)


async def test_a_lone_surrogate_in_a_query_never_reaches_the_database(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    query = "sick \ud800 leave"
    async with as_persona(app_engine, seeded_sandbox, "mateo") as (db, asker, version_id):
        vector = await embed_query(FakeEmbedder(), query)
        result = await search_handbook(
            db, version_id=version_id, asker=asker, query=query, query_vector=vector
        )

    assert result.hits


async def test_the_askers_employment_type_is_kept_when_a_location_is_chosen(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    question = "overtime pay"
    vector = await embed_query(FakeEmbedder(), question)
    async with as_persona(app_engine, seeded_sandbox, "mateo") as (db, asker, version_id):
        hourly = await search_handbook(
            db,
            version_id=version_id,
            asker=asker,
            query=question,
            query_vector=vector,
            location_code="oak",
            limit=60,
        )
        salaried = await search_handbook(
            db,
            version_id=version_id,
            asker=Asker("TX", "salaried", "aus"),
            query=question,
            query_vector=vector,
            location_code="oak",
            limit=60,
        )
        sections = (
            await db.scalars(
                select(HandbookSection).where(HandbookSection.version_id == version_id)
            )
        ).all()

    def expected(kind: str) -> set[str]:
        asker_there = Asker("CA", kind, "oak")
        return {
            s.section_key
            for s in sections
            if applies(
                Audience(
                    tuple(s.audience.get("states", ())),
                    tuple(s.audience.get("employmentTypes", ())),
                    tuple(s.audience.get("locations", ())),
                ),
                asker_there,
            )
        }

    hourly_only = expected("hourly") - expected("salaried")
    assert hourly_only, "the handbook has hourly-only sections that apply in California"
    assert {h.section_id for h in hourly.hits} <= expected("hourly")
    assert {h.section_id for h in salaried.hits} <= expected("salaried")
    assert {h.section_id for h in hourly.hits} & hourly_only
    assert not {h.section_id for h in salaried.hits} & hourly_only
