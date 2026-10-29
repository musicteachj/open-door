"""`get_my_cases` and `list_cases` against the real database.

The seed company has four cases: Keisha and Chloe new, Aaliyah in review, Lucia closed. Dana is HR,
Marcus is Priya's manager, Priya is an employee. A canary is planted in every seeded case's words
and summary, and must never reach a tool result, an audit row, or a log.
"""

import json
import logging
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4, uuid5

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.ai.embeddings import FakeEmbedder
from app.ai.tools.base import ToolContext
from app.ai.tools.cases import ONLY_HR_TEXT
from app.ai.tools.registry import ToolOutcome, run_tool
from app.db.models import Tenant
from app.db.tenancy import TenantContext, tenant_session
from app.modules.handbook.asker import load_asker
from app.modules.handbook.search import pinned_version_id
from app.modules.identity.actor import load_actor
from app.modules.sandbox.seed import SeedCompany, build_company, insert_company
from tests.integration.conftest import TEST_KEYS, audit_events
from tests.integration.test_tools import NOW, context_for

pytestmark = pytest.mark.integration

CANARY = "ZEBRA-CANARY-7741-quartz-lantern"
ANCHOR = date(2026, 10, 5)
NAMES = {"Keisha", "Chloe", "Aaliyah", "Lucia"}


async def seed(engine: AsyncEngine, created: list[UUID], *, canary: bool = True) -> SeedCompany:
    tenant_id = uuid4()
    created.append(tenant_id)
    company = build_company(tenant_id, ANCHOR)
    if canary:
        company = replace(
            company,
            cases=tuple(
                replace(
                    case, text=f"{case.text} {CANARY}", summary_text=f"{case.summary_text} {CANARY}"
                )
                for case in company.cases
            ),
        )
    async with tenant_session(engine, TenantContext(tenant_id, None)) as session:
        session.add(
            Tenant(
                id=tenant_id, expires_at=datetime.now(UTC) + timedelta(hours=24), anchor_date=ANCHOR
            )
        )
        await session.flush()
        await insert_company(session, company, TEST_KEYS)
    return company


@pytest.fixture
async def company(app_engine: AsyncEngine, created_tenant_ids: list[UUID]) -> SeedCompany:
    return await seed(app_engine, created_tenant_ids)


def data_of(outcome: ToolOutcome) -> Any:
    assert outcome.is_error is False, outcome.content
    assert len(outcome.content) == 1
    return json.loads(outcome.content[0]["text"])


def person_id(company: SeedCompany, persona: str) -> UUID:
    return uuid5(company.tenant_id, f"person:{persona}")


async def case_audit(engine: AsyncEngine, company: SeedCompany, action: str) -> list[Any]:
    return [e for e in await audit_events(engine, company.tenant_id) if e.action == action]


async def context_of(engine: AsyncEngine, company: SeedCompany, who: UUID) -> ToolContext:
    """A tool context for any person of the company, as the server builds one for a session."""
    ctx = TenantContext(company.tenant_id, who)
    async with tenant_session(engine, ctx) as session:
        actor = await load_actor(session, company.tenant_id, who)
        assert actor is not None
        version_id = await pinned_version_id(session)
        assert version_id is not None
        asker = await load_asker(session, actor)
    return ToolContext(
        engine=engine,
        tenant_ctx=ctx,
        actor=actor,
        asker=asker,
        version_id=version_id,
        embedder=FakeEmbedder(),
        now=NOW,
        conversation_id=uuid4(),
        turn_id=uuid4(),
    )


def seeded_case_of(company: SeedCompany, given_name: str) -> Any:
    owner = next(p.id for p in company.people if p.given_name == given_name)
    return next(case for case in company.cases if case.person_id == owner), owner


# --- get_my_cases ------------------------------------------------------------------------------


async def test_get_my_cases_says_so_when_there_are_none(
    app_engine: AsyncEngine, company: SeedCompany
) -> None:
    ctx = await context_for(app_engine, company, "priya")

    outcome = await run_tool("get_my_cases", {}, ctx)

    assert outcome.is_error is False
    assert outcome.content == [{"type": "text", "text": "You have no cases."}]


@pytest.mark.parametrize("name", sorted(NAMES))
async def test_get_my_cases_returns_only_the_askers_own_case_with_no_id(
    app_engine: AsyncEngine, company: SeedCompany, name: str
) -> None:
    case, owner = seeded_case_of(company, name)
    ctx = await context_of(app_engine, company, owner)

    outcome = await run_tool("get_my_cases", {}, ctx)

    data = data_of(outcome)
    assert len(data["cases"]) == 1
    (shown,) = data["cases"]
    assert set(shown) == {"category", "sentOn", "status", "replyBy"}
    assert shown["replyBy"] == case.reply_by.isoformat()
    assert (
        shown["status"]
        == {
            "new": "Sent to HR",
            "in_review": "HR is reviewing",
            "closed": "HR has finished its review",
        }[case.status]
    )
    assert data["truncated"] is False
    text = outcome.content[0]["text"]
    assert str(case.id) not in text
    assert CANARY not in text
    assert case.text not in text


async def test_get_my_cases_is_the_askers_even_for_hr(
    app_engine: AsyncEngine, company: SeedCompany
) -> None:
    # Dana could read every case; the tool still returns only the ones she opened (none).
    ctx = await context_for(app_engine, company, "dana")

    outcome = await run_tool("get_my_cases", {}, ctx)

    assert outcome.content == [{"type": "text", "text": "You have no cases."}]


# --- list_cases --------------------------------------------------------------------------------


async def test_list_cases_returns_the_seeded_four_for_dana_in_the_queues_order(
    app_engine: AsyncEngine, company: SeedCompany
) -> None:
    ctx = await context_for(app_engine, company, "dana")

    outcome = await run_tool("list_cases", {"status": "open"}, ctx)

    data = data_of(outcome)
    open_cases = [c for c in company.cases if c.status != "closed"]
    assert len(open_cases) == 3
    assert {c["id"] for c in data["cases"]} == {str(c.id) for c in open_cases}
    # New cases first, by reply-by date; then the rest.
    assert [c["status"] for c in data["cases"]][-1] == "in_review"
    assert [c["status"] for c in data["cases"]][:2] == ["new", "new"]
    reply_by = [c["replyBy"] for c in data["cases"][:2]]
    assert reply_by == sorted(reply_by)

    everything = {
        status: data_of(await run_tool("list_cases", {"status": status}, ctx))["cases"]
        for status in ("new", "in_review", "closed")
    }
    assert [len(everything[k]) for k in ("new", "in_review", "closed")] == [2, 1, 1]
    assert {c["id"] for rows in everything.values() for c in rows} == {
        str(c.id) for c in company.cases
    }


async def test_list_cases_gives_the_metadata_the_spec_names_and_nothing_else(
    app_engine: AsyncEngine, company: SeedCompany
) -> None:
    ctx = await context_for(app_engine, company, "dana")
    data = data_of(await run_tool("list_cases", {"status": "closed"}, ctx))

    (lucia,) = data["cases"]
    case, _ = seeded_case_of(company, "Lucia")
    assert set(lucia) == {
        "id",
        "category",
        "person",
        "title",
        "location",
        "sentOn",
        "replyBy",
        "status",
        "replyDue",
    }
    assert lucia["id"] == str(case.id)
    assert lucia["person"].startswith("Lucia ")
    assert lucia["status"] == "closed"
    assert lucia["replyDue"] is False
    assert data["truncated"] is False


async def test_a_new_case_is_marked_reply_due_when_its_date_has_come(
    app_engine: AsyncEngine, company: SeedCompany
) -> None:
    # The tool's day is Monday 2026-10-05 in Denver. The seed makes Chloe's reply due that day, and
    # Keisha's is later. A case that is not new is never "due".
    ctx = await context_for(app_engine, company, "dana")
    rows = data_of(await run_tool("list_cases", {"status": "open"}, ctx))["cases"]

    due = {row["person"].split()[0]: row["replyDue"] for row in rows}
    assert due == {"Keisha": False, "Chloe": True, "Aaliyah": False}


async def test_list_cases_writes_one_case_listed_event_with_a_count_and_no_text(
    app_engine: AsyncEngine, company: SeedCompany
) -> None:
    ctx = await context_for(app_engine, company, "dana")
    before = await case_audit(app_engine, company, "case.listed")

    await run_tool("list_cases", {"status": "open"}, ctx)

    events = await case_audit(app_engine, company, "case.listed")
    assert len(events) == len(before) + 1
    event = events[-1]
    assert (event.target_type, event.via) == ("case", "assistant")
    assert event.actor_person_id == person_id(company, "dana")
    assert event.after == {"count": 3, "status": "open"}
    assert CANARY not in json.dumps(event.after)


@pytest.mark.parametrize("persona", ["marcus", "priya", "mateo"])
async def test_anyone_but_hr_gets_the_one_fixed_error_and_no_audit_row(
    app_engine: AsyncEngine, company: SeedCompany, persona: str
) -> None:
    ctx = await context_for(app_engine, company, persona)

    for status in ("open", "new", "in_review", "closed"):
        outcome = await run_tool("list_cases", {"status": status}, ctx)
        assert outcome.is_error is True
        assert outcome.content == [{"type": "text", "text": ONLY_HR_TEXT}]
    assert await case_audit(app_engine, company, "case.listed") == []


async def test_the_error_is_the_same_whether_or_not_cases_exist(
    app_engine: AsyncEngine, company: SeedCompany, created_tenant_ids: list[UUID]
) -> None:
    bare_id = uuid4()
    created_tenant_ids.append(bare_id)
    bare = replace(build_company(bare_id, ANCHOR), cases=())
    async with tenant_session(app_engine, TenantContext(bare_id, None)) as session:
        session.add(
            Tenant(
                id=bare_id, expires_at=datetime.now(UTC) + timedelta(hours=24), anchor_date=ANCHOR
            )
        )
        await session.flush()
        await insert_company(session, bare, None)

    with_cases = await run_tool(
        "list_cases", {"status": "open"}, await context_for(app_engine, company, "marcus")
    )
    without_cases = await run_tool(
        "list_cases", {"status": "open"}, await context_for(app_engine, bare, "marcus")
    )

    assert with_cases == without_cases
    assert with_cases.content == [{"type": "text", "text": ONLY_HR_TEXT}]


async def test_a_person_in_another_sandbox_sees_none_of_this_sandboxs_cases(
    app_engine: AsyncEngine, company: SeedCompany, created_tenant_ids: list[UUID]
) -> None:
    other = await seed(app_engine, created_tenant_ids)

    employee = await run_tool(
        "list_cases", {"status": "open"}, await context_for(app_engine, other, "priya")
    )
    hr_elsewhere = data_of(
        await run_tool(
            "list_cases", {"status": "open"}, await context_for(app_engine, other, "dana")
        )
    )

    assert employee.content == [{"type": "text", "text": ONLY_HR_TEXT}]
    # The other sandbox's HR sees the other sandbox's four, never this one's.
    assert {c["id"] for c in hr_elsewhere["cases"]} == {
        str(c.id) for c in other.cases if c.status != "closed"
    }
    assert not {c["id"] for c in hr_elsewhere["cases"]} & {str(c.id) for c in company.cases}


async def test_a_manager_is_refused(app_engine: AsyncEngine, company: SeedCompany) -> None:
    # Nobody outside HR lists cases, whoever the case belongs to.
    outcome = await run_tool(
        "list_cases", {"status": "open"}, await context_for(app_engine, company, "marcus")
    )
    assert outcome.content == [{"type": "text", "text": ONLY_HR_TEXT}]


async def test_a_model_supplied_person_or_flag_is_refused_and_changes_nothing(
    app_engine: AsyncEngine, company: SeedCompany
) -> None:
    ctx = await context_for(app_engine, company, "priya")

    outcome = await run_tool(
        "list_cases",
        {"status": "open", "person_id": str(person_id(company, "dana")), "is_hr": True},
        ctx,
    )

    # Priya is not HR, so she gets the fixed error whatever the input says.
    assert outcome.content == [{"type": "text", "text": ONLY_HR_TEXT}]
    hr = await context_for(app_engine, company, "dana")
    bad = await run_tool("list_cases", {"status": "open", "person_id": "x"}, hr)
    assert bad.is_error is True
    assert "person_id" in bad.content[0]["text"]
    assert await case_audit(app_engine, company, "case.listed") == []


# --- the canary --------------------------------------------------------------------------------


async def test_no_case_words_or_summary_reach_a_result_an_audit_row_or_a_log(
    app_engine: AsyncEngine, company: SeedCompany, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    dana = await context_for(app_engine, company, "dana")
    outcomes = [
        await run_tool("list_cases", {"status": status}, dana)
        for status in ("open", "new", "in_review", "closed")
    ]
    for name in sorted(NAMES):
        _, owner = seeded_case_of(company, name)
        outcomes.append(
            await run_tool("get_my_cases", {}, await context_of(app_engine, company, owner))
        )
    outcomes.append(
        await run_tool(
            "list_cases", {"status": "open"}, await context_for(app_engine, company, "priya")
        )
    )

    for outcome in outcomes:
        assert json.dumps(outcome.content).find(CANARY) == -1
        assert CANARY not in outcome.summary
    for case in company.cases:
        for outcome in outcomes:
            assert case.text not in json.dumps(outcome.content)
            assert case.summary_text not in json.dumps(outcome.content)
    audit = await audit_events(app_engine, company.tenant_id)
    for event in audit:
        assert CANARY not in json.dumps([event.before, event.after])
    assert CANARY not in caplog.text
    # The seeded words were really there to leak.
    assert all(CANARY in case.text for case in company.cases)
