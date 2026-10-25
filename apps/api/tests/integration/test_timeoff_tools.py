"""The six time-off tools against the real database, for the seed company's people.

The company is the 145-person seed. Marcus Bell manages Priya Raman, Leo Nakamura, and Zara
Bautista (the apparel lead, whose pending request for October 27 and 28 waits for him); Dana is
HR; Mateo is a warehouse associate in Austin under someone else. "Now" is Monday 2026-10-05, the
seed's anchor day. A tool is run through the registry, as the turn runs it.
"""

import dataclasses
import json
import re
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4, uuid5

import pytest
from sqlalchemy import insert, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.ai.conversations import TurnFinished
from app.ai.tools.base import ToolContext, ToolOutcome
from app.ai.tools.registry import describe_call, run_tool
from app.db.models import TimeOffRequest
from app.db.tenancy import TenantContext, tenant_session
from app.domain.timeoff.labels import label
from app.modules.sandbox.seed import SeedCompany
from app.modules.timeoff.texts import REFUSAL_TEXTS, refusal_text
from tests.integration.conftest import audit_events
from tests.integration.test_proposals import end_turn, make_chat
from tests.integration.test_tools import NOW
from tests.integration.test_tools import context_for as base_context

pytestmark = pytest.mark.integration

CONFIRM_SENTENCE = "A confirm card is shown to the person. Nothing is booked until they confirm."
DENIAL_NOTE = "ZEBRA-NOTE-7731 she was rude to a customer"
UUID_TEXT = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
ZARA_KEY = "oak-apparel-lead"
# A Monday, a Friday, and a Monday after today, with no Oakland holiday near them.
MON_NOV_9 = date(2026, 11, 9)
MON_NOV_16 = date(2026, 11, 16)
MON_OCT_12 = date(2026, 10, 12)
FRI_OCT_16 = date(2026, 10, 16)


# ---------------------------------------------------------------------------------------------
# Setup


def person_id(company: SeedCompany, key: str) -> UUID:
    return uuid5(company.tenant_id, f"person:{key}")


async def tools_as(
    engine: AsyncEngine, company: SeedCompany, key: str, *, with_chat: bool = False
) -> ToolContext:
    """The tools' context for a person: the real actor, the turn's `now`, and (for a proposal) a
    conversation with its one turn running."""
    base = await base_context(engine, company, key)
    if not with_chat:
        return base
    chat = await make_chat(engine, company.tenant_id, person_id(company, key))
    return dataclasses.replace(base, conversation_id=chat.conversation_id, turn_id=chat.turn_id)


async def call(ctx: ToolContext, name: str, raw: dict[str, Any]) -> ToolOutcome:
    return await run_tool(name, raw, ctx)


def body(outcome: ToolOutcome) -> Any:
    """The result's one text block, as JSON. Fails if the tool failed."""
    assert outcome.is_error is False, outcome.content
    assert len(outcome.content) == 1
    assert outcome.content[0]["type"] == "text"
    return json.loads(outcome.content[0]["text"])


def error_text(outcome: ToolOutcome) -> str:
    assert outcome.is_error is True, outcome.content
    assert len(outcome.content) == 1
    assert outcome.content[0]["type"] == "text"
    return str(outcome.content[0]["text"])


def check_input(
    start: date,
    end: date | None = None,
    *,
    type: str = "pto",
    half_day: bool = False,
    hours: int | None = None,
) -> dict[str, Any]:
    return {
        "type": type,
        "start_date": start.isoformat(),
        "end_date": (end or start).isoformat(),
        "half_day": half_day,
        "hours": hours,
    }


async def put_request(
    engine: AsyncEngine,
    company: SeedCompany,
    key: str,
    start: date,
    end: date | None = None,
    *,
    type: str = "pto",
    status: str | None = None,
    amount_minutes: int = 480,
    decided_by: str | None = None,
    note: str | None = None,
) -> UUID:
    """Insert a request directly, as history or as a setup. It is not audited."""
    status = status or ("pending" if type == "pto" else "recorded")
    request_id = uuid4()
    async with tenant_session(engine, TenantContext(company.tenant_id, None)) as session:
        await session.execute(
            insert(TimeOffRequest).values(
                id=request_id,
                tenant_id=company.tenant_id,
                person_id=person_id(company, key),
                type=type,
                start_date=start,
                end_date=end or start,
                amount_minutes=amount_minutes,
                status=status,
                created_via="ui",
                decided_by=person_id(company, decided_by) if decided_by else None,
                decided_at=NOW if status in {"approved", "denied"} else None,
                decision_note=note,
                canceled_at=NOW if status == "canceled" else None,
            )
        )
    return request_id


async def request_ids(engine: AsyncEngine, company: SeedCompany) -> set[UUID]:
    async with tenant_session(engine, TenantContext(company.tenant_id, None)) as session:
        rows = await session.execute(
            text("SELECT id FROM time_off_requests WHERE tenant_id = :t"),
            {"t": company.tenant_id},
        )
        return {row.id for row in rows}


async def counts(owner: AsyncEngine, company: SeedCompany) -> dict[str, int]:
    """Row counts of everything a tool could write, read as the owner (no row-level security)."""
    out: dict[str, int] = {}
    async with owner.connect() as connection:
        for table in ("time_off_requests", "ai_proposals", "audit_events"):
            result = await connection.execute(
                text(f"SELECT count(*) FROM {table} WHERE tenant_id = :t"),  # noqa: S608
                {"t": company.tenant_id},
            )
            out[table] = int(result.scalar_one())
    return out


async def rename_family(
    owner: AsyncEngine, company: SeedCompany, key: str, family_name: str
) -> None:
    async with owner.begin() as connection:
        await connection.execute(
            text("UPDATE people SET family_name = :n WHERE id = :id"),
            {"n": family_name, "id": person_id(company, key)},
        )


async def proposals_of(owner: AsyncEngine, company: SeedCompany) -> list[dict[str, Any]]:
    async with owner.connect() as connection:
        rows = await connection.execute(
            text(
                "SELECT id, action, status, payload, outcome FROM ai_proposals"
                " WHERE tenant_id = :t ORDER BY created_at"
            ),
            {"t": company.tenant_id},
        )
        return [dict(row._mapping) for row in rows]


async def waiting_id_for_marcus(ctx: ToolContext) -> str:
    """Zara's pending request, found the way the model finds it: through the list tool."""
    result = body(await call(ctx, "list_time_off_requests", {"scope": "waiting_for_me"}))
    [only] = [r for r in result["requests"] if r["person"] == "Zara Bautista"]
    return str(only["id"])


# ---------------------------------------------------------------------------------------------
# get_time_off_balance


async def test_the_balance_is_every_figure_as_a_label_with_its_rules(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    ctx = await tools_as(app_engine, seeded_sandbox, "priya")

    outcome = await call(ctx, "get_time_off_balance", {})

    result = body(outcome)
    assert outcome.proposal is None
    assert result["person"] == "Priya Raman"
    assert result["asOf"] == "2026-10-05"
    assert set(result["pto"]) == {
        "earned",
        "taken",
        "booked",
        "pending",
        "available",
        "ceiling",
        "nextEarning",
    }
    assert set(result["pto"]["nextEarning"]) == {"date", "amount"}
    assert all(isinstance(v, str) for k, v in result["pto"].items() if k != "nextEarning")
    # The current year only, until a recorded sick day falls in the next one.
    assert [year["year"] for year in result["sick"]] == [2026]
    assert set(result["sick"][0]) == {"year", "granted", "used", "booked", "available"}
    assert {rule["sectionId"] for rule in result["rules"]} >= {"4.1"}
    assert all(set(rule) == {"sectionId", "title"} and rule["title"] for rule in result["rules"])


async def test_the_balance_matches_the_engine_through_the_page_route(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    from app.modules.identity.actor import load_actor
    from app.modules.timeoff import service
    from app.modules.timeoff.schemas import BalancesOut

    ctx = await tools_as(app_engine, seeded_sandbox, "priya")
    async with tenant_session(app_engine, ctx.tenant_ctx) as db:
        actor = await load_actor(db, ctx.actor.tenant_id, ctx.actor.person_id)
        assert actor is not None
        balances = await service.balances(db, actor, actor.person_id, NOW)
    assert not isinstance(balances, service.Refused)
    expected = BalancesOut.of(balances)

    result = body(await call(ctx, "get_time_off_balance", {}))

    assert result["pto"]["available"] == expected.pto.available_label
    assert result["pto"]["ceiling"] == expected.pto.ceiling_label
    assert result["sick"][0]["available"] == expected.sick[0].available_label


# ---------------------------------------------------------------------------------------------
# person_name: only among the people the actor may read


@pytest.mark.parametrize("tool", ["get_time_off_balance", "list_time_off_requests"])
async def test_an_employee_asking_for_a_colleague_gets_an_error_that_names_no_one(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany, tool: str
) -> None:
    ctx = await tools_as(app_engine, seeded_sandbox, "priya")
    raw = {"person_name": "Leo Nakamura"}
    raw |= {"scope": "team"} if tool == "list_time_off_requests" else {}

    outcome = await call(ctx, tool, raw)

    message = error_text(outcome)
    for word in ("Leo", "Nakamura", "Marcus", "Zara"):
        assert word not in message
    # Not even the name that was asked for comes back: a refusal says nothing about who exists.
    assert "Nakamura" not in message


async def test_an_employee_can_name_themselves(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    ctx = await tools_as(app_engine, seeded_sandbox, "priya")

    for name in ("Priya Raman", "priya", "RAMAN", "  priya   raman "):
        result = body(await call(ctx, "get_time_off_balance", {"person_name": name}))
        assert result["person"] == "Priya Raman", name


async def test_a_manager_reads_a_report_and_only_a_report(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    ctx = await tools_as(app_engine, seeded_sandbox, "marcus")

    for name in ("Leo Nakamura", "leo nakamura", "NAKAMURA", "Leo"):
        result = body(await call(ctx, "get_time_off_balance", {"person_name": name}))
        assert result["person"] == "Leo Nakamura", name
    # Mateo works in Austin, under someone else.
    refused = error_text(await call(ctx, "get_time_off_balance", {"person_name": "Mateo Alvarez"}))
    assert "Mateo" not in refused
    assert "Alvarez" not in refused


async def test_a_skip_level_manager_reads_the_reports_of_their_reports(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    ctx = await tools_as(app_engine, seeded_sandbox, "marcus")
    async with tenant_session(app_engine, ctx.tenant_ctx) as db:
        row = await db.execute(
            text(
                "SELECT given_name || ' ' || family_name AS name FROM people"
                " WHERE manager_id = :zara LIMIT 1"
            ),
            {"zara": person_id(seeded_sandbox, ZARA_KEY)},
        )
        associate: str = row.scalar_one()

    result = body(await call(ctx, "get_time_off_balance", {"person_name": associate}))

    assert result["person"] == associate


async def test_hr_reads_anyone(app_engine: AsyncEngine, seeded_sandbox: SeedCompany) -> None:
    ctx = await tools_as(app_engine, seeded_sandbox, "dana")

    mateo = body(await call(ctx, "get_time_off_balance", {"person_name": "Mateo Alvarez"}))
    listing = body(
        await call(ctx, "list_time_off_requests", {"scope": "mine", "person_name": "Leo Nakamura"})
    )

    assert mateo["person"] == "Mateo Alvarez"
    assert {r["person"] for r in listing["requests"]} == {"Leo Nakamura"}


async def test_no_match_says_so_without_naming_anyone(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    ctx = await tools_as(app_engine, seeded_sandbox, "dana")

    message = error_text(await call(ctx, "get_time_off_balance", {"person_name": "Nobody Atall"}))

    assert "Nobody" not in message
    assert "match" in message.lower()


async def test_an_ambiguous_name_lists_names_and_titles_of_readable_people_only(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    seeded_sandbox: SeedCompany,
) -> None:
    # Three people share a family name: two of Marcus's reports, and Mateo, who isn't his.
    await rename_family(owner_engine, seeded_sandbox, "leo", "Raman")
    await rename_family(owner_engine, seeded_sandbox, "mateo", "Raman")
    marcus = await tools_as(app_engine, seeded_sandbox, "marcus")
    dana = await tools_as(app_engine, seeded_sandbox, "dana")
    priya = await tools_as(app_engine, seeded_sandbox, "priya")
    mateo = await tools_as(app_engine, seeded_sandbox, "mateo")

    for tool in ("get_time_off_balance", "list_time_off_requests"):
        raw: dict[str, Any] = {"person_name": "Raman"}
        if tool == "list_time_off_requests":
            raw["scope"] = "team"
        manager = error_text(await call(marcus, tool, raw))
        assert "Priya Raman (Visual Merchandiser)" in manager
        assert "Leo Raman (Sales Associate)" in manager
        assert "Mateo" not in manager
        assert "Warehouse Associate" not in manager
        hr = error_text(await call(dana, tool, raw))
        assert "Mateo Raman (Warehouse Associate)" in hr
        assert "Leo Raman" in hr
        assert "Priya Raman" in hr
    # An employee sees only themselves among the three, so the name is theirs.
    own = body(await call(priya, "get_time_off_balance", {"person_name": "Raman"}))
    assert own["person"] == "Priya Raman"
    own_too = body(await call(mateo, "get_time_off_balance", {"person_name": "Raman"}))
    assert own_too["person"] == "Mateo Raman"


async def test_a_full_name_beats_a_shared_family_name(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    await rename_family(owner_engine, seeded_sandbox, "leo", "Raman")
    ctx = await tools_as(app_engine, seeded_sandbox, "marcus")

    result = body(await call(ctx, "get_time_off_balance", {"person_name": "leo raman"}))

    assert result["person"] == "Leo Raman"


# ---------------------------------------------------------------------------------------------
# list_time_off_requests


async def test_a_person_lists_their_own_requests_with_names_labels_and_ids(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    ctx = await tools_as(app_engine, seeded_sandbox, "priya")

    outcome = await call(ctx, "list_time_off_requests", {"scope": "mine"})

    result = body(outcome)
    assert outcome.proposal is None
    assert result["window"] == {"from": "2026-09-05", "to": "2027-02-02"}
    assert result["truncated"] is False
    [half_day] = [r for r in result["requests"] if r["startDate"] == "2026-09-22"]
    assert half_day["person"] == "Priya Raman"
    assert half_day["type"] == "pto"
    assert half_day["endDate"] == "2026-09-22"
    assert half_day["amount"] == "4 hours (half a day)"
    assert half_day["status"] == "approved"
    assert half_day["decidedBy"] is None or isinstance(half_day["decidedBy"], str)
    assert UUID(half_day["id"])
    assert set(half_day) == {
        "id",
        "person",
        "type",
        "startDate",
        "endDate",
        "amount",
        "status",
        "decidedBy",
    }
    # Starts before the window (September 4), so it isn't listed.
    assert all(r["startDate"] != "2026-09-04" for r in result["requests"])


async def test_a_manager_lists_the_team_and_what_waits_for_them(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    ctx = await tools_as(app_engine, seeded_sandbox, "marcus")

    team = body(await call(ctx, "list_time_off_requests", {"scope": "team"}))
    waiting = body(await call(ctx, "list_time_off_requests", {"scope": "waiting_for_me"}))

    people = {r["person"] for r in team["requests"]}
    assert {"Leo Nakamura", "Priya Raman"} <= people
    assert "Marcus Bell" not in people
    [only] = waiting["requests"]
    assert (only["person"], only["status"], only["startDate"], only["endDate"]) == (
        "Zara Bautista",
        "pending",
        "2026-10-27",
        "2026-10-28",
    )
    assert only["amount"] == "16 hours (2 days)"


async def test_nothing_waits_for_someone_with_no_reports(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    ctx = await tools_as(app_engine, seeded_sandbox, "priya")

    for scope in ("team", "waiting_for_me"):
        result = body(await call(ctx, "list_time_off_requests", {"scope": scope}))
        assert result["requests"] == []


async def test_the_window_narrows_the_list(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    ctx = await tools_as(app_engine, seeded_sandbox, "marcus")

    result = body(
        await call(
            ctx,
            "list_time_off_requests",
            {"scope": "team", "from": "2026-10-20", "to": "2026-10-31"},
        )
    )

    assert result["window"] == {"from": "2026-10-20", "to": "2026-10-31"}
    assert {r["person"] for r in result["requests"]} == {"Zara Bautista"}


async def test_a_list_stops_at_twenty_and_says_it_was_cut(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    for offset in range(25):
        day = date(2026, 11, 2) + timedelta(days=offset)
        await put_request(app_engine, seeded_sandbox, "priya", day, type="sick", amount_minutes=480)
    ctx = await tools_as(app_engine, seeded_sandbox, "priya")

    result = body(
        await call(
            ctx,
            "list_time_off_requests",
            {"scope": "mine", "from": "2026-11-01", "to": "2026-12-31"},
        )
    )

    assert len(result["requests"]) == 20
    assert result["truncated"] is True
    assert result["requests"][0]["startDate"] == "2026-11-02"


async def test_a_denied_request_is_listed_without_its_note(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    await put_request(
        app_engine,
        seeded_sandbox,
        "priya",
        date(2026, 11, 2),
        status="denied",
        decided_by="marcus",
        note=DENIAL_NOTE,
    )
    priya = await tools_as(app_engine, seeded_sandbox, "priya")
    marcus = await tools_as(app_engine, seeded_sandbox, "marcus")

    for ctx, scope in ((priya, "mine"), (marcus, "team")):
        outcome = await call(ctx, "list_time_off_requests", {"scope": scope})
        result = body(outcome)
        denied = [r for r in result["requests"] if r["status"] == "denied"]
        assert [r["decidedBy"] for r in denied] == ["Marcus Bell"]
        raw = outcome.content[0]["text"]
        assert "ZEBRA" not in raw
        assert "rude" not in raw
        assert "note" not in raw.lower()


async def test_waiting_for_me_with_a_name_lists_only_what_the_asker_decides(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    marcus = await tools_as(app_engine, seeded_sandbox, "marcus")
    dana = await tools_as(app_engine, seeded_sandbox, "dana")

    zara = body(
        await call(
            marcus,
            "list_time_off_requests",
            {"scope": "waiting_for_me", "person_name": "Zara Bautista"},
        )
    )
    leo = body(
        await call(
            marcus, "list_time_off_requests", {"scope": "waiting_for_me", "person_name": "Leo"}
        )
    )
    # HR reads Zara's request but isn't her manager, so nothing waits for HR to decide.
    hr = body(
        await call(
            dana,
            "list_time_off_requests",
            {"scope": "waiting_for_me", "person_name": "Zara Bautista"},
        )
    )

    assert [r["person"] for r in zara["requests"]] == ["Zara Bautista"]
    assert leo["requests"] == []
    assert hr["requests"] == []


async def test_waiting_for_me_ignores_the_window_so_a_lone_far_bound_is_no_error(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    ctx = await tools_as(app_engine, seeded_sandbox, "marcus")

    far_from = body(
        await call(ctx, "list_time_off_requests", {"scope": "waiting_for_me", "from": "2027-06-01"})
    )
    early_to = body(
        await call(ctx, "list_time_off_requests", {"scope": "waiting_for_me", "to": "2026-01-01"})
    )

    assert [r["person"] for r in far_from["requests"]] == ["Zara Bautista"]
    assert [r["person"] for r in early_to["requests"]] == ["Zara Bautista"]


async def test_a_lone_bound_on_the_wrong_side_says_which_to_move_without_echoing_it(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    ctx = await tools_as(app_engine, seeded_sandbox, "marcus")

    late_from = error_text(
        await call(ctx, "list_time_off_requests", {"scope": "team", "from": "2027-06-01"})
    )
    early_to = error_text(
        await call(ctx, "list_time_off_requests", {"scope": "team", "to": "2026-01-01"})
    )

    assert "'to'" in late_from
    assert "'from'" in early_to
    assert "2027" not in late_from
    assert "2026-01" not in early_to


async def test_the_summary_names_the_scope_and_never_a_request_id() -> None:
    summary = describe_call("list_time_off_requests", {"scope": "team", "person_name": "Leo"})
    assert "team" in summary
    assert describe_call("list_time_off_requests", {"nope": 1}) == ""


# ---------------------------------------------------------------------------------------------
# check_time_off


async def test_a_check_gives_the_engines_answer_and_writes_nothing(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    ctx = await tools_as(app_engine, seeded_sandbox, "priya", with_chat=True)
    before = await counts(owner_engine, seeded_sandbox)
    events_before = len(await audit_events(app_engine, seeded_sandbox.tenant_id))

    ok = await call(ctx, "check_time_off", check_input(MON_NOV_16))
    refused = await call(ctx, "check_time_off", check_input(date(2026, 10, 2)))
    half = await call(ctx, "check_time_off", check_input(MON_NOV_16, half_day=True))

    assert await counts(owner_engine, seeded_sandbox) == before
    assert len(await audit_events(app_engine, seeded_sandbox.tenant_id)) == events_before
    assert ok.proposal is None
    answer = body(ok)
    assert answer["ok"] is True
    assert answer["countedDays"] == ["2026-11-16"]
    assert answer["skippedDays"] == []
    assert answer["amount"] == "8 hours (1 day)"
    [draw] = answer["draws"]
    assert draw["year"] is None
    assert draw["amount"] == "8 hours (1 day)"
    assert draw["availableBefore"] != draw["availableAfter"]
    assert answer["warnings"] == []
    assert answer["problems"] == []
    assert answer["rules"]
    assert body(half)["amount"] == "4 hours (half a day)"
    # A refusal is an answer to "would this work", with the engine's sentence.
    no = body(refused)
    assert no["ok"] is False
    assert [p["code"] for p in no["problems"]] == ["out-of-range"]
    assert no["problems"][0]["text"] == refusal_text("out-of-range")


async def test_a_check_flags_short_notice_and_skips_with_reasons(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    ctx = await tools_as(app_engine, seeded_sandbox, "priya")

    week = body(await call(ctx, "check_time_off", check_input(MON_OCT_12, FRI_OCT_16)))
    weekend = body(
        await call(ctx, "check_time_off", check_input(date(2026, 11, 14), date(2026, 11, 16)))
    )

    assert "short-notice" in [w["code"] for w in week["warnings"]]
    assert all(w["text"] for w in week["warnings"])
    assert week["amount"].endswith("days)")
    assert weekend["countedDays"] == ["2026-11-16"]
    assert [s["date"] for s in weekend["skippedDays"]] == ["2026-11-14", "2026-11-15"]
    assert all(s["reason"] for s in weekend["skippedDays"])


async def test_sick_time_across_new_year_shows_one_draw_per_year(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    ctx = await tools_as(app_engine, seeded_sandbox, "priya")

    answer = body(
        await call(
            ctx,
            "check_time_off",
            check_input(date(2026, 12, 31), date(2027, 1, 4), type="sick"),
        )
    )

    assert answer["ok"] is True
    assert [d["year"] for d in answer["draws"]] == [2026, 2027]
    assert [d["amount"] for d in answer["draws"]] == ["8 hours (1 day)", "8 hours (1 day)"]
    assert "2027-01-01" in [s["date"] for s in answer["skippedDays"]]


async def test_sick_hours_become_a_partial_day(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    ctx = await tools_as(app_engine, seeded_sandbox, "priya")

    three = body(
        await call(ctx, "check_time_off", check_input(date(2026, 10, 2), type="sick", hours=3))
    )
    half = body(
        await call(
            ctx, "check_time_off", check_input(date(2026, 10, 2), type="sick", half_day=True)
        )
    )
    on_a_range = body(
        await call(
            ctx,
            "check_time_off",
            check_input(date(2026, 10, 1), date(2026, 10, 2), type="sick", hours=3),
        )
    )

    assert three["amount"] == "3 hours"
    assert half["amount"] == "4 hours (half a day)"
    assert [p["code"] for p in on_a_range["problems"]] == ["bad-partial"]


async def test_a_check_uses_the_turns_time_not_a_clock(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    ctx = await tools_as(app_engine, seeded_sandbox, "priya")
    later = dataclasses.replace(ctx, now=datetime(2026, 11, 17, 18, 0, tzinfo=UTC))

    now_ok = body(await call(ctx, "check_time_off", check_input(MON_NOV_16)))
    then = body(await call(later, "check_time_off", check_input(MON_NOV_16)))

    assert now_ok["ok"] is True
    # By the 17th, the 16th is in the past.
    assert [p["code"] for p in then["problems"]] == ["out-of-range"]


async def test_an_overlap_lists_the_days_that_clash(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    await put_request(app_engine, seeded_sandbox, "priya", MON_NOV_9, date(2026, 11, 10))
    ctx = await tools_as(app_engine, seeded_sandbox, "priya")

    answer = body(
        await call(ctx, "check_time_off", check_input(date(2026, 11, 10), date(2026, 11, 11)))
    )

    assert answer["ok"] is False
    assert [p["code"] for p in answer["problems"]] == ["overlaps"]
    assert answer["overlappingDays"] == ["2026-11-10"]


# ---------------------------------------------------------------------------------------------
# propose_time_off_request


async def test_a_request_proposal_writes_one_proposal_and_one_audit_event_and_nothing_else(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    ctx = await tools_as(app_engine, seeded_sandbox, "priya", with_chat=True)
    before = await counts(owner_engine, seeded_sandbox)
    events_before = len(await audit_events(app_engine, seeded_sandbox.tenant_id))

    outcome = await call(ctx, "propose_time_off_request", check_input(MON_NOV_16))

    after = await counts(owner_engine, seeded_sandbox)
    assert after == {
        "time_off_requests": before["time_off_requests"],
        "ai_proposals": before["ai_proposals"] + 1,
        "audit_events": before["audit_events"] + 1,
    }
    new_events = (await audit_events(app_engine, seeded_sandbox.tenant_id))[events_before:]
    assert [e.action for e in new_events] == ["proposal.created"]
    answer = body(outcome)
    assert answer["note"] == CONFIRM_SENTENCE
    assert answer["ok"] is True
    assert answer["amount"] == "8 hours (1 day)"
    assert answer["countedDays"] == ["2026-11-16"]
    [stored] = await proposals_of(owner_engine, seeded_sandbox)
    assert (stored["action"], stored["status"]) == ("timeoff.request", "pending")
    assert stored["payload"] == {
        "type": "pto",
        "startDate": "2026-11-16",
        "endDate": "2026-11-16",
        "partialMinutes": None,
    }


async def test_the_outcome_carries_the_card_and_the_model_never_sees_it(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    ctx = await tools_as(app_engine, seeded_sandbox, "priya", with_chat=True)

    outcome = await call(ctx, "propose_time_off_request", check_input(MON_NOV_16))

    card = outcome.proposal
    assert card is not None
    [stored] = await proposals_of(owner_engine, seeded_sandbox)
    assert card.id == stored["id"]
    assert (card.action, card.status, card.turn_running) == ("timeoff.request", "pending", True)
    assert card.card.kind == "request"
    assert card.card.amount_label == "8 hours (1 day)"
    assert card.card.approver is not None
    assert card.card.approver.name == "Marcus Bell"
    # Nothing but the engine's labels and the sentence reaches the model: no proposal ID, no
    # approver, no expiry.
    raw = outcome.content[0]["text"]
    assert str(card.id) not in raw
    assert "Marcus" not in raw
    assert "expires" not in raw.lower()


async def test_a_sick_request_proposal_stores_the_hours_as_a_partial_day(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    ctx = await tools_as(app_engine, seeded_sandbox, "priya", with_chat=True)

    outcome = await call(
        ctx, "propose_time_off_request", check_input(date(2026, 10, 2), type="sick", hours=3)
    )

    assert body(outcome)["amount"] == "3 hours"
    assert outcome.proposal is not None
    assert outcome.proposal.card.partial_minutes == 180
    [stored] = await proposals_of(owner_engine, seeded_sandbox)
    assert stored["payload"]["partialMinutes"] == 180


async def test_a_refused_request_is_a_tool_error_and_writes_nothing(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    ctx = await tools_as(app_engine, seeded_sandbox, "priya", with_chat=True)
    before = await counts(owner_engine, seeded_sandbox)

    outcome = await call(ctx, "propose_time_off_request", check_input(date(2026, 10, 2)))

    assert error_text(outcome) == refusal_text("out-of-range")
    assert outcome.proposal is None
    assert await counts(owner_engine, seeded_sandbox) == before


async def test_a_manager_less_person_asking_for_pto_gets_the_fixed_sentence(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    async with owner_engine.begin() as connection:
        await connection.execute(
            text("UPDATE people SET manager_id = NULL WHERE id = :id"),
            {"id": person_id(seeded_sandbox, "priya")},
        )
    ctx = await tools_as(app_engine, seeded_sandbox, "priya", with_chat=True)
    before = await counts(owner_engine, seeded_sandbox)

    outcome = await call(ctx, "propose_time_off_request", check_input(MON_NOV_16))

    assert error_text(outcome) == refusal_text("no-approver")
    assert await counts(owner_engine, seeded_sandbox) == before


async def test_a_second_proposal_in_the_conversation_replaces_the_first(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    ctx = await tools_as(app_engine, seeded_sandbox, "priya", with_chat=True)

    first = await call(ctx, "propose_time_off_request", check_input(MON_NOV_16))
    second = await call(ctx, "propose_time_off_request", check_input(MON_NOV_9))

    assert first.proposal is not None
    assert second.proposal is not None
    stored = await proposals_of(owner_engine, seeded_sandbox)
    assert [(row["status"], row["id"]) for row in stored] == [
        ("canceled", first.proposal.id),
        ("pending", second.proposal.id),
    ]
    assert stored[0]["outcome"]["reason"] == "replaced"


async def test_a_proposal_for_a_turn_that_has_ended_is_a_tool_error_that_writes_nothing(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    ctx = await tools_as(app_engine, seeded_sandbox, "priya")
    chat = await make_chat(app_engine, seeded_sandbox.tenant_id, person_id(seeded_sandbox, "priya"))
    ctx = dataclasses.replace(ctx, conversation_id=chat.conversation_id, turn_id=chat.turn_id)
    await end_turn(app_engine, chat, "completed")
    before = await counts(owner_engine, seeded_sandbox)

    outcome = await call(ctx, "propose_time_off_request", check_input(MON_NOV_16))

    assert error_text(outcome) == "This answer has ended, so no card was made."
    assert outcome.proposal is None
    assert await counts(owner_engine, seeded_sandbox) == before


async def test_turn_finished_is_turned_into_the_same_error_for_every_proposal_tool(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    seeded_sandbox: SeedCompany,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.ai.tools import timeoff

    async def finished(*_args: Any, **_kwargs: Any) -> Any:
        raise TurnFinished("t")

    monkeypatch.setattr(timeoff, "create_proposal", finished)
    zara_request = await put_request(app_engine, seeded_sandbox, "priya", MON_NOV_9)
    marcus = await tools_as(app_engine, seeded_sandbox, "marcus", with_chat=True)
    priya = await tools_as(app_engine, seeded_sandbox, "priya", with_chat=True)
    waiting = await waiting_id_for_marcus(marcus)

    outcomes = [
        await call(priya, "propose_time_off_request", check_input(MON_NOV_16)),
        await call(
            marcus, "propose_time_off_decision", {"request_id": waiting, "decision": "approve"}
        ),
        await call(priya, "propose_cancel_time_off", {"request_id": str(zara_request)}),
    ]

    for outcome in outcomes:
        assert error_text(outcome) == "This answer has ended, so no card was made."
        assert outcome.proposal is None


# ---------------------------------------------------------------------------------------------
# propose_time_off_decision


async def test_a_decision_proposal_gives_the_summary_and_never_the_team_coverage(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    # Priya, on Marcus's team, is off on one of Zara's days, so the card's coverage isn't empty.
    await put_request(
        app_engine,
        seeded_sandbox,
        "priya",
        date(2026, 10, 27),
        status="approved",
        decided_by="marcus",
    )
    ctx = await tools_as(app_engine, seeded_sandbox, "marcus", with_chat=True)
    request_id = await waiting_id_for_marcus(ctx)
    before = await counts(owner_engine, seeded_sandbox)
    events_before = len(await audit_events(app_engine, seeded_sandbox.tenant_id))

    outcome = await call(
        ctx, "propose_time_off_decision", {"request_id": request_id, "decision": "approve"}
    )

    answer = body(outcome)
    assert answer["person"] == "Zara Bautista"
    assert answer["title"] == "Department Lead, Apparel"
    assert answer["type"] == "pto"
    assert (answer["startDate"], answer["endDate"]) == ("2026-10-27", "2026-10-28")
    assert answer["amount"] == "16 hours (2 days)"
    assert answer["decision"] == "approve"
    assert answer["note"].startswith("A confirm card is shown to the person.")
    assert answer["rules"]
    # The card has the coverage. The model does not.
    assert outcome.proposal is not None
    card = outcome.proposal.card
    assert card.kind == "decide"
    assert [c.person.name for c in card.coverage] == ["Priya Raman"]
    raw = outcome.content[0]["text"]
    for word in ("Priya", "Raman", "overage", "team"):
        assert word not in raw
    assert str(card.requester.id) not in raw
    assert request_id in raw
    after = await counts(owner_engine, seeded_sandbox)
    assert after == {
        "time_off_requests": before["time_off_requests"],
        "ai_proposals": before["ai_proposals"] + 1,
        "audit_events": before["audit_events"] + 1,
    }
    new_events = (await audit_events(app_engine, seeded_sandbox.tenant_id))[events_before:]
    assert [e.action for e in new_events] == ["proposal.created"]
    [stored] = await proposals_of(owner_engine, seeded_sandbox)
    assert stored["action"] == "timeoff.decide"
    assert stored["payload"] == {"requestId": request_id, "decision": "approve"}


async def test_a_denial_proposal_says_deny(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    ctx = await tools_as(app_engine, seeded_sandbox, "marcus", with_chat=True)
    request_id = await waiting_id_for_marcus(ctx)

    outcome = await call(
        ctx, "propose_time_off_decision", {"request_id": request_id, "decision": "deny"}
    )

    assert body(outcome)["decision"] == "deny"
    assert outcome.proposal is not None
    assert outcome.proposal.card.kind == "decide"
    assert outcome.proposal.card.decision == "deny"


async def test_a_decision_that_isnt_open_to_the_person_is_a_fixed_sentence_and_writes_nothing(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    marcus = await tools_as(app_engine, seeded_sandbox, "marcus", with_chat=True)
    request_id = await waiting_id_for_marcus(marcus)
    priya = await tools_as(app_engine, seeded_sandbox, "priya", with_chat=True)
    dana = await tools_as(app_engine, seeded_sandbox, "dana", with_chat=True)
    already_approved = await put_request(
        app_engine, seeded_sandbox, "leo", MON_NOV_9, status="approved", decided_by="marcus"
    )
    before = await counts(owner_engine, seeded_sandbox)

    unreadable = await call(
        priya, "propose_time_off_decision", {"request_id": request_id, "decision": "approve"}
    )
    not_the_manager = await call(
        dana, "propose_time_off_decision", {"request_id": request_id, "decision": "approve"}
    )
    decided = await call(
        marcus,
        "propose_time_off_decision",
        {"request_id": str(already_approved), "decision": "deny"},
    )
    missing = await call(
        marcus,
        "propose_time_off_decision",
        {"request_id": str(uuid4()), "decision": "approve"},
    )

    assert error_text(unreadable) == refusal_text("not-found")
    assert error_text(not_the_manager) == refusal_text("not-allowed")
    assert error_text(decided) == refusal_text("status-changed")
    assert error_text(missing) == refusal_text("not-found")
    assert await counts(owner_engine, seeded_sandbox) == before


# ---------------------------------------------------------------------------------------------
# propose_cancel_time_off


async def test_a_cancel_proposal_gives_the_request_and_what_returns(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    request_id = await put_request(app_engine, seeded_sandbox, "priya", MON_NOV_9)
    ctx = await tools_as(app_engine, seeded_sandbox, "priya", with_chat=True)
    before = await counts(owner_engine, seeded_sandbox)
    events_before = len(await audit_events(app_engine, seeded_sandbox.tenant_id))

    outcome = await call(ctx, "propose_cancel_time_off", {"request_id": str(request_id)})

    answer = body(outcome)
    assert answer["type"] == "pto"
    assert (answer["startDate"], answer["endDate"]) == ("2026-11-09", "2026-11-09")
    assert answer["status"] == "pending"
    assert answer["amount"] == "8 hours (1 day)"
    assert answer["returns"] == "8 hours (1 day)"
    assert isinstance(answer["availableAfter"], str)
    assert answer["note"].startswith("A confirm card is shown to the person.")
    assert answer["rules"]
    assert outcome.proposal is not None
    assert outcome.proposal.action == "timeoff.cancel"
    assert outcome.proposal.card.kind == "cancel"
    after = await counts(owner_engine, seeded_sandbox)
    assert after == {
        "time_off_requests": before["time_off_requests"],
        "ai_proposals": before["ai_proposals"] + 1,
        "audit_events": before["audit_events"] + 1,
    }
    new_events = (await audit_events(app_engine, seeded_sandbox.tenant_id))[events_before:]
    assert [e.action for e in new_events] == ["proposal.created"]
    [stored] = await proposals_of(owner_engine, seeded_sandbox)
    assert stored["payload"] == {"requestId": str(request_id)}


async def test_a_sick_cancel_has_nothing_that_returns(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    request_id = await put_request(app_engine, seeded_sandbox, "priya", MON_NOV_9, type="sick")
    ctx = await tools_as(app_engine, seeded_sandbox, "priya", with_chat=True)

    answer = body(await call(ctx, "propose_cancel_time_off", {"request_id": str(request_id)}))

    assert answer["type"] == "sick"
    assert answer["status"] == "recorded"
    assert answer["returns"] is None
    assert answer["availableAfter"] is None


async def test_a_cancel_that_isnt_open_is_a_fixed_sentence_and_writes_nothing(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    priya = await tools_as(app_engine, seeded_sandbox, "priya", with_chat=True)
    marcus = await tools_as(app_engine, seeded_sandbox, "marcus", with_chat=True)
    leos = await put_request(app_engine, seeded_sandbox, "leo", MON_NOV_9)
    past = await put_request(
        app_engine,
        seeded_sandbox,
        "priya",
        date(2026, 10, 1),
        status="approved",
        decided_by="marcus",
    )
    denied = await put_request(
        app_engine,
        seeded_sandbox,
        "priya",
        date(2026, 11, 23),
        status="denied",
        decided_by="marcus",
    )
    zara = await waiting_id_for_marcus(marcus)
    before = await counts(owner_engine, seeded_sandbox)

    someone_elses = await call(marcus, "propose_cancel_time_off", {"request_id": str(leos)})
    unreadable = await call(priya, "propose_cancel_time_off", {"request_id": zara})
    started = await call(priya, "propose_cancel_time_off", {"request_id": str(past)})
    closed = await call(priya, "propose_cancel_time_off", {"request_id": str(denied)})

    assert error_text(someone_elses) == refusal_text("not-allowed")
    assert error_text(unreadable) == refusal_text("not-found")
    assert error_text(started) == refusal_text("already-started")
    assert error_text(closed) == refusal_text("status-changed")
    assert await counts(owner_engine, seeded_sandbox) == before


# ---------------------------------------------------------------------------------------------
# What every result may hold


async def every_result(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, company: SeedCompany
) -> list[tuple[str, str, ToolOutcome]]:
    """Every tool's result over the seeded sandbox, for each person it makes sense for. Returns
    (person, tool, outcome). A denied request with a distinctive note and a colleague's approved
    time off on a request's days are seeded first."""
    await put_request(
        app_engine, company, "priya", date(2026, 10, 27), status="approved", decided_by="marcus"
    )
    await put_request(
        app_engine,
        company,
        "priya",
        date(2026, 11, 2),
        status="denied",
        decided_by="marcus",
        note=DENIAL_NOTE,
    )
    cancelable = await put_request(app_engine, company, "priya", MON_NOV_9)
    results: list[tuple[str, str, ToolOutcome]] = []
    for key in ("priya", "leo", "marcus", "dana", "mateo"):
        ctx = await tools_as(app_engine, company, key, with_chat=True)
        for scope in ("mine", "team", "waiting_for_me"):
            results.append(
                (key, "list", await call(ctx, "list_time_off_requests", {"scope": scope}))
            )
        results.append((key, "balance", await call(ctx, "get_time_off_balance", {})))
        results.append((key, "check", await call(ctx, "check_time_off", check_input(MON_NOV_16))))
        if key != "mateo":
            results.append(
                (
                    key,
                    "check sick",
                    await call(
                        ctx,
                        "check_time_off",
                        check_input(date(2026, 12, 31), date(2027, 1, 4), type="sick"),
                    ),
                )
            )
        results.append(
            (
                key,
                "propose",
                await call(ctx, "propose_time_off_request", check_input(date(2026, 11, 30))),
            )
        )
        if key == "marcus":
            waiting = await waiting_id_for_marcus(ctx)
            for decision in ("approve", "deny"):
                results.append(
                    (
                        key,
                        f"decide {decision}",
                        await call(
                            ctx,
                            "propose_time_off_decision",
                            {"request_id": waiting, "decision": decision},
                        ),
                    )
                )
        if key == "priya":
            results.append(
                (
                    key,
                    "cancel",
                    await call(ctx, "propose_cancel_time_off", {"request_id": str(cancelable)}),
                )
            )
        if key == "dana":
            results.append(
                (
                    key,
                    "balance of leo",
                    await call(ctx, "get_time_off_balance", {"person_name": "Leo Nakamura"}),
                )
            )
    return results


async def test_no_result_holds_a_random_id_or_a_note(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    results = await every_result(app_engine, owner_engine, seeded_sandbox)

    allowed = {str(i) for i in await request_ids(app_engine, seeded_sandbox)}
    seen: set[str] = set()
    for person, tool, outcome in results:
        for block in outcome.content:
            assert block["type"] == "text", (person, tool)
            text_found = block["text"]
            assert "ZEBRA" not in text_found, (person, tool)
            assert "rude" not in text_found, (person, tool)
            ids = set(UUID_TEXT.findall(text_found))
            assert ids <= allowed, (person, tool, ids - allowed)
            seen |= ids
    # The scan did see request IDs, so it isn't passing on an empty result.
    assert seen
    # Seeded IDs come from the sandbox's own ID, so they repeat in the eval's sandbox.
    seeded = {str(r.id) for r in seeded_sandbox.time_off_requests}
    assert seen & seeded


def minutes_leaks(node: Any, path: str = "") -> list[str]:
    """Where a result holds a bare number: only a calendar year may be one."""
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            found.extend(minutes_leaks(value, f"{path}.{key}"))
            if "minute" in key.lower():
                found.append(f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found.extend(minutes_leaks(value, f"{path}[{index}]"))
    elif isinstance(node, int) and not isinstance(node, bool) and not path.endswith(".year"):
        found.append(path)
    return found


async def test_results_quote_labels_and_never_a_bare_number_of_minutes(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    results = await every_result(app_engine, owner_engine, seeded_sandbox)

    parsed = 0
    for person, tool, outcome in results:
        if outcome.is_error:
            continue
        parsed += 1
        assert minutes_leaks(json.loads(outcome.content[0]["text"])) == [], (person, tool)
    assert parsed > 20
    # The label is the product's one, not a rewrite of it.
    answer = body(next(o for p, t, o in results if (p, t) == ("priya", "check") and not o.is_error))
    assert answer["amount"] == label(480)


async def test_only_proposal_tools_carry_a_proposal(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    results = await every_result(app_engine, owner_engine, seeded_sandbox)

    for person, tool, outcome in results:
        proposes = tool in {"propose", "decide approve", "decide deny", "cancel"}
        if proposes and not outcome.is_error:
            assert outcome.proposal is not None, (person, tool)
        else:
            assert outcome.proposal is None, (person, tool)


async def test_every_result_is_a_policy_checked_read_of_the_askers_own_people(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    results = await every_result(app_engine, owner_engine, seeded_sandbox)

    people = {f"{p.given_name} {p.family_name}": p.id for p in seeded_sandbox.people}
    for key, tool, outcome in results:
        if tool != "list" or outcome.is_error:
            continue
        ctx = await tools_as(app_engine, seeded_sandbox, key)
        readable = {ctx.actor.person_id, *ctx.actor.report_ids}
        for row in json.loads(outcome.content[0]["text"])["requests"]:
            who = people[row["person"]]
            assert ctx.actor.is_hr_admin or who in readable, (key, row["person"])


async def test_a_refusal_text_is_always_a_fixed_one() -> None:
    # Every sentence a tool can answer with is in the fixed table, so no stored text is repeated.
    assert set(REFUSAL_TEXTS) >= {
        "out-of-range",
        "no-approver",
        "not-found",
        "not-allowed",
        "status-changed",
        "already-started",
    }
