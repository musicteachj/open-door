"""The retrieval eval against the real dataset and the loaded handbook (needs `make db`)."""

from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.ai.embeddings import FakeEmbedder
from app.db.models import Location, Tenant
from app.db.tenancy import TenantContext, tenant_session
from tests.retrieval_eval import load_runner

pytestmark = pytest.mark.integration

run = load_runner()


async def test_the_real_dataset_is_valid_and_its_sections_exist_in_the_loaded_handbook(
    app_engine: AsyncEngine,
) -> None:
    questions = run.parse_dataset(run.DATASET_PATH)
    vectors = [None] * len(questions)

    result = await run.run_searches_on(app_engine, questions, vectors)

    run.check_sections(questions, result.section_ids)
    assert len(result.outcomes) == len(questions)
    assert result.version_label
    # No vectors, so every search is full-text only, and the report says so.
    assert {o.mode for o in result.outcomes} == {"fulltext"}


async def test_the_real_dataset_covers_every_section_and_has_the_planned_shape(
    app_engine: AsyncEngine,
) -> None:
    questions = run.parse_dataset(run.DATASET_PATH)
    assert 55 <= len(questions) <= 80
    assert 12 <= sum(q.is_negative for q in questions) <= 20
    assert sum(q.location_code is not None for q in questions) >= 3
    assert {q.asker_label for q in questions} >= {"priya", "marcus", "dana", "mateo"}

    result = await run.run_searches_on(app_engine, questions[:1], [None])
    named = {s for q in questions for s in (*q.expect, *q.must_not)}
    assert result.section_ids - named == set()

    # Sections that are only ever an alternate in a multi-section `expect` are allowed (the lead
    # decides on new questions), but are printed with -s for review.
    sole = {q.expect[0] for q in questions if len(q.expect) == 1}
    only_alternates = (
        (result.section_ids & named) - sole - {s for q in questions for s in q.must_not}
    )
    print("Only ever an alternate:", sorted(only_alternates))


async def test_the_run_searches_with_vectors_and_rolls_its_scratch_tenant_back(
    app_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant_id = uuid4()
    first = iter([tenant_id])
    monkeypatch.setattr(run, "uuid4", lambda: next(first, None) or uuid4())
    questions = run.parse_dataset(run.DATASET_PATH)[:3]
    vectors = [FakeEmbedder._vector(q.text) for q in questions]

    result = await run.run_searches_on(app_engine, questions, vectors)

    assert {o.mode for o in result.outcomes} == {"hybrid"}
    assert all(len(o.sections) <= 5 for o in result.outcomes)
    async with tenant_session(app_engine, TenantContext(tenant_id, None)) as session:
        assert await session.scalar(select(func.count()).select_from(Tenant)) == 0
        assert await session.scalar(select(func.count()).select_from(Location)) == 0


async def test_a_location_code_question_is_answered_for_that_location(
    app_engine: AsyncEngine,
) -> None:
    questions = [q for q in run.parse_dataset(run.DATASET_PATH) if q.id == "loc-mateo-ca-sick"]
    result = await run.run_searches_on(app_engine, questions, [None])
    assert "CA-4.3" in result.outcomes[0].sections
