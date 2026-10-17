"""The three tools against the real database, for the seed company's people."""

import dataclasses
import json
from collections.abc import Sequence
from typing import Any
from uuid import UUID, uuid5

import pytest
from sqlalchemy import delete, event, select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.ai.embeddings import FakeEmbedder, InputType
from app.ai.tools.registry import ToolContext, ToolOutcome, describe_call, run_tool
from app.db.models import AuditEvent, Person, PersonPrivate
from app.db.tenancy import TenantContext, tenant_session
from app.modules.handbook.asker import load_asker
from app.modules.handbook.search import pinned_version_id
from app.modules.identity.actor import load_actor
from app.modules.people.queries import get_card, get_private_details
from app.modules.sandbox.seed import SeedCompany
from app.policy import Action, Actor, PersonResource, can

pytestmark = pytest.mark.integration

SICK = "How much sick leave do I get?"
PRIVATE_NAMES = ("personalEmail", "personal_email", "phone", "homeAddress", "home_address")


class Spy:
    """Records how many statements the engine had run when it was asked to embed."""

    def __init__(self, statements: list[str]) -> None:
        self.statements = statements
        self.seen_at: list[int] = []

    async def embed(self, texts: Sequence[str], *, input_type: InputType) -> list[list[float]]:
        self.seen_at.append(len(self.statements))
        return await FakeEmbedder().embed(texts, input_type=input_type)


async def context_for(
    engine: AsyncEngine, company: SeedCompany, persona: str, embedder: Any = None
) -> ToolContext:
    tenant_id = company.tenant_id
    person_id = uuid5(tenant_id, f"person:{persona}")
    tenant_ctx = TenantContext(tenant_id, person_id)
    async with tenant_session(engine, tenant_ctx) as session:
        actor = await load_actor(session, tenant_id, person_id)
        assert actor is not None
        version_id = await pinned_version_id(session)
        assert version_id is not None
        asker = await load_asker(session, actor)
    return ToolContext(
        engine=engine,
        tenant_ctx=tenant_ctx,
        actor=actor,
        asker=asker,
        version_id=version_id,
        embedder=embedder or FakeEmbedder(),
    )


def payload(outcome: ToolOutcome) -> Any:
    assert outcome.is_error is False, outcome.content
    assert len(outcome.content) == 1
    assert outcome.content[0]["type"] == "text"
    return json.loads(outcome.content[0]["text"])


# --- search_handbook --------------------------------------------------------------------------


async def test_each_hit_becomes_one_search_result_with_citations_on(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    ctx = await context_for(app_engine, seeded_sandbox, "priya")
    outcome = await run_tool("search_handbook", {"query": SICK}, ctx)

    assert outcome.is_error is False
    assert 1 <= len(outcome.content) <= 5
    assert len(outcome.sources) == len(outcome.content)
    for block, source in zip(outcome.content, outcome.sources, strict=True):
        assert block["type"] == "search_result"
        assert block["citations"] == {"enabled": True}
        assert block["source"] == source.deep_link
        assert block["source"].startswith(f"/handbook/{source.section_id}?passage=")
        assert block["source"].endswith(source.passage_ids[0])
        assert block["title"].startswith(f"{source.section_id} {source.title}")
        assert block["title"].endswith(f" · {source.group_name}")
        assert len(block["content"]) == len(source.passage_ids)
        assert all(part["type"] == "text" and part["text"] for part in block["content"])
        assert set(block) == {"type", "source", "title", "content", "citations"}


async def test_a_question_with_no_match_is_one_text_block(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    # The fake embedder always finds neighbors, so the vector search is made to fail and only the
    # full-text search runs.

    class Failing:
        async def embed(self, texts: Sequence[str], *, input_type: InputType) -> list[list[float]]:
            raise RuntimeError("down")

    ctx = await context_for(app_engine, seeded_sandbox, "priya", Failing())
    outcome = await run_tool("search_handbook", {"query": "zzzqqq xylophone"}, ctx)
    assert outcome.is_error is False
    assert outcome.content == [{"type": "text", "text": "No handbook passages matched."}]
    assert outcome.sources == []


async def test_no_embedder_means_full_text_search_only(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany, caplog: pytest.LogCaptureFixture
) -> None:
    class Forbidden:
        async def embed(self, texts: Sequence[str], *, input_type: InputType) -> list[list[float]]:
            raise AssertionError("an embedder was called")

    with_one = await context_for(app_engine, seeded_sandbox, "priya", Forbidden())
    without = dataclasses.replace(with_one, embedder=None)
    outcome = await run_tool("search_handbook", {"query": SICK}, without)

    assert outcome.is_error is False
    assert outcome.sources, "full-text search should still find sick leave"
    # Skipped on purpose, not an embedding failure that was caught and logged.
    assert "Query embedding failed" not in caplog.text


async def test_a_location_searches_that_places_policy_with_the_askers_type(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    ctx = await context_for(app_engine, seeded_sandbox, "mateo")
    own = await run_tool("search_handbook", {"query": SICK}, ctx)
    california = await run_tool("search_handbook", {"query": SICK, "location": "oak"}, ctx)
    assert california.is_error is False
    assert any(s.section_id.startswith("CA") for s in california.sources)
    assert not any(s.section_id.startswith("CA") for s in own.sources)


async def test_a_location_keeps_the_askers_employment_type(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    # Overtime is for hourly people only. Mateo is hourly and Priya is salaried.
    mateo = await context_for(app_engine, seeded_sandbox, "mateo")
    priya = await context_for(app_engine, seeded_sandbox, "priya")
    assert mateo.asker.employment_type == "hourly"
    assert priya.asker.employment_type == "salaried"
    hourly = await run_tool("search_handbook", {"query": "overtime", "location": "den"}, mateo)
    salaried = await run_tool("search_handbook", {"query": "overtime", "location": "den"}, priya)
    assert "CO-3.2" in {s.section_id for s in hourly.sources}
    assert "CO-3.2" not in {s.section_id for s in salaried.sources}


async def test_an_unknown_location_is_a_helpful_error(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    ctx = await context_for(app_engine, seeded_sandbox, "priya")
    outcome = await run_tool("search_handbook", {"query": SICK, "location": "sf"}, ctx)
    assert outcome.is_error is True
    assert outcome.content[0]["text"] == "Unknown location 'sf'. Use one of: den, oak, aus, atl."


async def test_the_query_is_embedded_before_the_transaction_opens(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    events: list[str] = []

    def statement(*args: object) -> None:
        events.append("statement")

    sync_engine = app_engine.sync_engine
    spy = Spy(events)
    ctx = await context_for(app_engine, seeded_sandbox, "priya", spy)
    event.listen(sync_engine, "before_cursor_execute", statement)
    try:
        outcome = await run_tool("search_handbook", {"query": SICK}, ctx)
    finally:
        event.remove(sync_engine, "before_cursor_execute", statement)
    assert outcome.is_error is False
    assert spy.seen_at == [0]
    assert events  # and the search itself did run statements afterward


# --- get_my_profile ---------------------------------------------------------------------------


async def test_get_my_profile_returns_the_askers_own_details_and_audits_the_read(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    ctx = await context_for(app_engine, seeded_sandbox, "priya")
    outcome = await run_tool("get_my_profile", {}, ctx)
    data = payload(outcome)

    assert data["givenName"] == "Priya"
    assert data["familyName"] == "Raman"
    assert data["role"] == "employee"
    assert data["employmentType"] in {"salaried", "hourly"}
    assert {"title", "department", "manager", "location", "workEmail"} <= set(data)
    assert set(data["privateDetails"]) == {
        "personalEmail",
        "phone",
        "homeAddress",
        "dateOfBirth",
    }
    assert outcome.sources == []

    async with tenant_session(app_engine, ctx.tenant_ctx) as db:
        events = (
            await db.scalars(
                select(AuditEvent).where(
                    AuditEvent.action == "person_private.read",
                    AuditEvent.actor_person_id == ctx.actor.person_id,
                )
            )
        ).all()
    assert len(events) == 1
    assert events[0].via == "assistant"
    assert events[0].target_id == ctx.actor.person_id
    assert events[0].after == {"fields": ["dateOfBirth", "homeAddress", "personalEmail", "phone"]}


async def test_get_my_profile_writes_no_audit_event_when_no_details_come_back(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    ctx = await context_for(app_engine, seeded_sandbox, "priya")
    async with owner_engine.begin() as connection:
        await connection.execute(
            delete(PersonPrivate).where(PersonPrivate.person_id == ctx.actor.person_id)
        )
    data = payload(await run_tool("get_my_profile", {}, ctx))
    assert data["privateDetails"] is None
    async with tenant_session(app_engine, ctx.tenant_ctx) as db:
        events = (
            await db.scalars(select(AuditEvent).where(AuditEvent.action == "person_private.read"))
        ).all()
    assert events == []


async def test_get_my_profile_names_a_manager_and_hr_by_role(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    marcus = payload(
        await run_tool(
            "get_my_profile", {}, await context_for(app_engine, seeded_sandbox, "marcus")
        )
    )
    dana = payload(
        await run_tool("get_my_profile", {}, await context_for(app_engine, seeded_sandbox, "dana"))
    )
    assert marcus["role"] == "manager"
    assert dana["role"] == "hr"


# --- find_people ------------------------------------------------------------------------------


async def test_find_people_returns_directory_fields_only(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    ctx = await context_for(app_engine, seeded_sandbox, "priya")
    outcome = await run_tool("find_people", {"scope": "everyone"}, ctx)
    data = payload(outcome)
    text = outcome.content[0]["text"]

    assert len(data["people"]) == 10  # capped
    for card in data["people"]:
        assert set(card) == {
            "name",
            "title",
            "department",
            "manager",
            "location",
            "workEmail",
        }
    for name in PRIVATE_NAMES:
        assert name not in text
    async with tenant_session(app_engine, TenantContext(ctx.actor.tenant_id, None)) as db:
        # Someone's real private values are nowhere in the output either.
        own = await get_private_details(db, ctx.actor.person_id)
    assert own is None or own.phone not in text


async def test_find_people_says_when_the_list_was_cut_off(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    priya = await context_for(app_engine, seeded_sandbox, "priya")
    marcus = await context_for(app_engine, seeded_sandbox, "marcus")
    assert payload(await run_tool("find_people", {"scope": "everyone"}, priya))["truncated"] is True
    assert payload(await run_tool("find_people", {"scope": "my_team"}, priya))["truncated"] is False
    one = payload(await run_tool("find_people", {"scope": "everyone", "query": "Raman"}, marcus))
    assert one["truncated"] is False


async def test_find_people_cleans_its_query_like_the_handbook_search(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    ctx = await context_for(app_engine, seeded_sandbox, "marcus")
    raw = {"scope": "everyone", "query": "\ud800Ram\x00an"}
    data = payload(await run_tool("find_people", raw, ctx))
    # The control character became a space, so this is "Ram an", which matches no one; a lone
    # surrogate alone is dropped without an error from the database.
    assert data["people"] == []
    data = payload(
        await run_tool("find_people", {"scope": "everyone", "query": "\ud800Raman"}, ctx)
    )
    assert [card["name"] for card in data["people"]] == ["Priya Raman"]


async def test_find_people_matches_a_name_query(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    ctx = await context_for(app_engine, seeded_sandbox, "priya")
    data = payload(
        await run_tool("find_people", {"scope": "everyone", "query": "Marcus Bell"}, ctx)
    )
    assert [card["name"] for card in data["people"]] == ["Marcus Bell"]


async def test_my_team_gives_a_manager_his_reports_and_priya_none(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    marcus = await context_for(app_engine, seeded_sandbox, "marcus")
    priya = await context_for(app_engine, seeded_sandbox, "priya")
    team = payload(await run_tool("find_people", {"scope": "my_team"}, marcus))
    names = {card["name"] for card in team["people"]}
    assert "Marcus Bell" not in names
    assert len(team["people"]) == min(10, len(marcus.actor.report_ids))
    only = payload(await run_tool("find_people", {"scope": "my_team", "query": "Raman"}, marcus))
    assert [card["name"] for card in only["people"]] == ["Priya Raman"]
    # Nobody outside his reports comes back, even by name.
    stranger = payload(
        await run_tool("find_people", {"scope": "my_team", "query": "Whitfield"}, marcus)
    )
    assert stranger["people"] == []
    assert payload(await run_tool("find_people", {"scope": "my_team"}, priya))["people"] == []


async def test_a_card_the_policy_refuses_is_left_out(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = await context_for(app_engine, seeded_sandbox, "marcus")
    everyone = payload(await run_tool("find_people", {"scope": "everyone"}, ctx))["people"]
    hidden = everyone[0]["workEmail"]
    async with tenant_session(app_engine, ctx.tenant_ctx) as db:
        hidden_id = await db.scalar(select(Person.id).where(Person.work_email == hidden))

    def refuse_one(actor: Actor, action: Action, target: PersonResource) -> bool:
        return target.person_id != hidden_id

    monkeypatch.setattr("app.ai.tools.people.can", refuse_one)
    shown = payload(await run_tool("find_people", {"scope": "everyone"}, ctx))["people"]
    assert hidden not in {card["workEmail"] for card in shown}
    assert len(shown) == len(everyone) - 1


async def test_each_card_passes_the_directory_policy(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    ctx = await context_for(app_engine, seeded_sandbox, "marcus")
    data = payload(await run_tool("find_people", {"scope": "everyone"}, ctx))
    emails = {card["workEmail"] for card in data["people"]}
    async with tenant_session(app_engine, ctx.tenant_ctx) as db:
        ids: list[UUID] = list(
            (await db.scalars(select(Person.id).where(Person.work_email.in_(emails)))).all()
        )
        assert len(ids) == len(emails)
        for person_id in ids:
            assert can(ctx.actor, Action.DIRECTORY_READ, PersonResource(person_id))
            assert await get_card(db, person_id) is not None


async def test_a_page_with_a_filtered_card_does_not_hint_at_the_hidden_person(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = await context_for(app_engine, seeded_sandbox, "marcus")
    team = payload(await run_tool("find_people", {"scope": "everyone", "query": "Shah"}, ctx))
    assert team["truncated"] is False
    assert len(team["people"]) >= 1
    hidden = team["people"][0]["workEmail"]
    async with tenant_session(app_engine, ctx.tenant_ctx) as db:
        hidden_id = await db.scalar(select(Person.id).where(Person.work_email == hidden))

    def refuse_one(actor: Actor, action: Action, target: PersonResource) -> bool:
        return target.person_id != hidden_id

    monkeypatch.setattr("app.ai.tools.people.can", refuse_one)
    shown = payload(await run_tool("find_people", {"scope": "everyone", "query": "Shah"}, ctx))
    assert len(shown["people"]) == len(team["people"]) - 1
    # `truncated` is the cursor only: it must not hint that the policy hid someone.
    assert shown["truncated"] is False


@pytest.mark.parametrize(
    ("name", "tool_input"),
    [
        ("search_handbook", {"query": "sick leave"}),
        ("search_handbook", {"query": "sick\x07 leave", "location": "oak"}),
        ("search_handbook", {"query": "x" * 600}),
        ("search_handbook", {"query": "sick", "location": "mars"}),
        ("search_handbook", {"query": "sick", "extra": 1}),
        ("find_people", {"scope": "everyone", "query": "Shah"}),
        ("find_people", {"scope": "s" * 2048}),
        ("find_people", {"scope": "everyone", "query": "q" * 600}),
        ("get_my_profile", {}),
    ],
)
async def test_the_started_summary_matches_the_finished_one_even_for_bad_input(
    app_engine: AsyncEngine,
    seeded_sandbox: SeedCompany,
    name: str,
    tool_input: dict[str, Any],
) -> None:
    ctx = await context_for(app_engine, seeded_sandbox, "priya")
    outcome = await run_tool(name, tool_input, ctx)
    described = describe_call(name, tool_input)

    assert described == outcome.summary
    assert len(described) < 200


async def test_the_profile_tools_failures_report_the_same_summary_as_its_start(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    ctx = await context_for(app_engine, seeded_sandbox, "priya")
    outcome = await run_tool("get_my_profile", {"x": 1}, ctx)

    assert outcome.is_error is True
    assert outcome.summary == describe_call("get_my_profile", {"x": 1}) == "own profile"


async def test_padding_that_cleans_away_does_not_make_a_query_too_long(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    ctx = await context_for(app_engine, seeded_sandbox, "priya")
    # 510 raw characters: 200 of them real, the rest control characters that clean to spaces.
    query = ("sick leave " * 19)[:200] + "\x07" * 310
    assert len(query) == 510
    outcome = await run_tool("search_handbook", {"query": query}, ctx)

    assert outcome.is_error is False
    assert describe_call("search_handbook", {"query": query}) == outcome.summary != ""
