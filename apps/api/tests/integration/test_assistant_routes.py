"""The assistant's conversation routes: the current conversation, a new one, and feedback.

The turns these routes show are written straight into the database as the person, with the store's
own functions, so these tests do not depend on the stream.
"""

import json
from collections.abc import Sequence
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.ai.conversations import (
    CURRENT_PINS,
    TurnOutcome,
    section_names,
)
from app.ai.fixed_texts import (
    BUDGET_DAILY_TEXT,
    BUDGET_SANDBOX_TEXT,
    CRISIS_TEXT,
    ERROR_TEXTS,
    PERSONAL_DATA_TEXT,
    STILL_ANSWERING_TEXT,
    UNAVAILABLE_TEXT,
)
from app.db.models import AiConversation, AiSpend
from app.db.tenancy import TenantContext, set_is_hr, tenant_session
from app.modules.cases.queries import cases_by_turn
from tests.integration.conftest import (
    Browser,
    OpenBrowser,
    OpenBrowserWith,
    begin_turn,
    end_turn,
    message_row,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.usefixtures("daily_ledger_untouched"),
]

BASE = "/api/v1/assistant"
CITATION = {
    "marker": 1,
    "offsetUtf16": 17,
    "sectionId": "CA-4.3",
    "passageId": "p2",
    "title": "Sick leave",
    "groupName": "California addendum",
    "audienceLabel": "California",
    "lastUpdated": "2026-09-12",
    "deepLink": "/handbook/CA-4.3?passage=p2",
    "citedText": "40 hours",
}


def sign_in(browser: Browser, persona: str = "priya") -> tuple[UUID, UUID]:
    """Start a sandbox as `persona`. Returns (tenant ID, person ID)."""
    sandbox = browser.start_sandbox(persona)
    return UUID(sandbox["tenant"]["id"]), UUID(sandbox["me"]["id"])


def new_conversation(browser: Browser) -> dict[str, Any]:
    response = browser.client.post(f"{BASE}/conversations", headers=browser.csrf)
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


async def seed_turn(
    engine: AsyncEngine,
    tenant_id: UUID,
    person_id: UUID,
    conversation_id: UUID,
    *,
    question: str = "How much sick leave do I get?",
    outcome: TurnOutcome | None = None,
) -> UUID:
    """Add a turn as the person and, unless `outcome` is None, finish it."""
    async with tenant_session(engine, TenantContext(tenant_id, person_id)) as db:
        conversation = await db.get(AiConversation, conversation_id)
        assert conversation is not None
        turn = await begin_turn(db, conversation, question)
        if outcome is not None:
            await end_turn(db, conversation, turn.id, outcome)
        return turn.id


def completed(**changes: Any) -> TurnOutcome:
    fields: dict[str, Any] = {
        "status": "completed",
        "answer_text": "You get 40 hours of paid sick leave.",
        "citations": [CITATION],
        "guard_verdict": {"category": "ordinary", "kind": None, "injectionSuspected": True},
        "tool_calls": [
            {"name": "search_handbook", "inputSummary": "sick leave", "ok": True, "durationMs": 12}
        ],
        "sections_retrieved": [{"sectionId": "CA-4.3", "passageIds": ["p1", "p2"]}],
        "served_by_models": ["claude-opus-5-5"],
        "cost_usd": Decimal("0.05"),
    }
    fields.update(changes)
    return TurnOutcome(**fields)


async def add_spend(
    engine: AsyncEngine, tenant_id: UUID, person_id: UUID, turn_id: UUID, amount_usd: str
) -> None:
    async with tenant_session(engine, TenantContext(tenant_id, person_id)) as db:
        db.add(
            AiSpend(
                tenant_id=tenant_id, turn_id=turn_id, kind="reserve", amount_usd=Decimal(amount_usd)
            )
        )


# --- Who may call ---------------------------------------------------------------------------


def test_every_route_needs_a_session(browser: Browser) -> None:
    turn_id = uuid4()
    responses = [
        browser.client.get(f"{BASE}/conversations/current"),
        browser.client.post(f"{BASE}/conversations"),
        browser.client.post(f"{BASE}/turns/{turn_id}/feedback", json={"helpful": True}),
        browser.client.post(f"{BASE}/conversations/{uuid4()}/turns", json={"question": "hi"}),
        browser.client.get(f"{BASE}/texts"),
        browser.client.get(f"{BASE}/budget"),
    ]

    assert [r.status_code for r in responses] == [401] * 6
    assert all(r.headers["content-type"] == "application/problem+json" for r in responses)


def test_the_routes_that_change_state_need_the_csrf_token(browser: Browser) -> None:
    sign_in(browser)

    create = browser.client.post(f"{BASE}/conversations")
    feedback = browser.client.post(f"{BASE}/turns/{uuid4()}/feedback", json={"helpful": True})

    assert (create.status_code, feedback.status_code) == (403, 403)
    assert browser.client.get(f"{BASE}/conversations/current").json() is None


def test_creating_a_conversation_needs_the_same_origin_check(browser: Browser) -> None:
    sign_in(browser)

    response = browser.client.post(
        f"{BASE}/conversations", headers={**browser.csrf, "Sec-Fetch-Site": "cross-site"}
    )

    assert response.status_code == 403


# --- The current conversation ---------------------------------------------------------------


def test_there_is_no_current_conversation_before_the_first(browser: Browser) -> None:
    sign_in(browser)

    response = browser.client.get(f"{BASE}/conversations/current")

    assert response.status_code == 200
    assert response.json() is None
    assert response.headers["cache-control"] == "no-store"


def test_a_new_conversation_is_pinned_to_the_current_versions_and_is_the_current_one(
    browser: Browser,
) -> None:
    sign_in(browser)

    created = new_conversation(browser)
    current = browser.client.get(f"{BASE}/conversations/current").json()

    assert current == created
    assert created["turns"] == []
    assert created["budget"] == {
        "sandboxReached": False,
        "dailyReached": False,
        "sandboxRemainingCents": 100,
        "banner": None,
    }
    assert created["hrContacts"] == []
    assert created["longHistory"] is False
    assert created["historyTooLong"] is False
    assert set(created) == {
        "id",
        "createdAt",
        "turns",
        "hrContacts",
        "budget",
        "longHistory",
        "historyTooLong",
        "outdated",
    }
    assert created["outdated"] is False


async def test_the_new_conversation_row_carries_the_current_pins(
    browser: Browser, app_engine: AsyncEngine
) -> None:
    tenant_id, person_id = sign_in(browser)

    created = new_conversation(browser)

    async with tenant_session(app_engine, TenantContext(tenant_id, person_id)) as db:
        row = await db.get(AiConversation, UUID(created["id"]))
    assert row is not None
    assert (
        row.model,
        row.guard_model,
        row.effort,
        row.prompt_version,
        row.toolset_version,
    ) == (
        CURRENT_PINS.model,
        CURRENT_PINS.guard_model,
        CURRENT_PINS.effort,
        CURRENT_PINS.prompt_version,
        CURRENT_PINS.toolset_version,
    )


def test_the_newest_conversation_is_the_current_one(browser: Browser) -> None:
    sign_in(browser)
    new_conversation(browser)

    second = new_conversation(browser)

    assert browser.client.get(f"{BASE}/conversations/current").json()["id"] == second["id"]


async def test_the_turns_come_oldest_first_with_everything_the_page_shows(
    browser: Browser, app_engine: AsyncEngine
) -> None:
    tenant_id, person_id = sign_in(browser)
    conversation = new_conversation(browser)
    cid = UUID(conversation["id"])
    first = await seed_turn(
        app_engine, tenant_id, person_id, cid, question="First?", outcome=completed()
    )
    second = await seed_turn(
        app_engine,
        tenant_id,
        person_id,
        cid,
        question="Second?",
        outcome=completed(answer_text="Cut o", citations=[], error_code="max-tokens"),
    )
    browser.client.post(
        f"{BASE}/turns/{first}/feedback",
        json={"helpful": False, "reason": "Not what I asked"},
        headers=browser.csrf,
    )

    turns = browser.client.get(f"{BASE}/conversations/current").json()["turns"]

    assert [t["id"] for t in turns] == [str(first), str(second)]
    assert [t["question"] for t in turns] == ["First?", "Second?"]
    one, two = turns
    assert one["status"] == "completed"
    assert one["answerText"] == "You get 40 hours of paid sick leave."
    assert one["citations"] == [CITATION]
    assert one["incomplete"] is False
    assert one["error"] is None
    assert one["escalation"] is None
    assert one["toolCalls"] == [
        {"name": "search_handbook", "inputSummary": "sick leave", "ok": True, "durationMs": 12}
    ]
    assert one["sections"] == [
        {"sectionId": "CA-4.3", "passageIds": ["p1", "p2"], "title": None, "groupName": None}
    ]
    assert one["notFound"] is False
    assert one["feedback"] == {"helpful": False, "reason": "Not what I asked"}
    assert two["feedback"] is None
    assert two["incomplete"] is True
    # Cut off, so not a miss, though it searched and cited nothing.
    assert two["notFound"] is False
    assert two["error"] is None
    assert two["answerText"] == "Cut o"


async def test_the_browser_sees_the_guards_category_and_kind_but_not_the_injection_flag(
    browser: Browser, app_engine: AsyncEngine
) -> None:
    tenant_id, person_id = sign_in(browser)
    cid = UUID(new_conversation(browser)["id"])
    verdict = {"category": "sensitive", "kind": "pay", "injectionSuspected": True}
    await seed_turn(app_engine, tenant_id, person_id, cid, outcome=completed(guard_verdict=verdict))

    [turn] = browser.client.get(f"{BASE}/conversations/current").json()["turns"]

    assert turn["guard"] == {"category": "sensitive", "kind": "pay"}
    assert "injectionSuspected" not in str(turn)


async def test_a_failed_turn_shows_its_fixed_error_text_on_reload(
    browser: Browser, app_engine: AsyncEngine
) -> None:
    tenant_id, person_id = sign_in(browser)
    cid = UUID(new_conversation(browser)["id"])
    for code in ("budget-daily", "spend-limit", "refusal", "prompt-leak", "abandoned"):
        await seed_turn(
            app_engine,
            tenant_id,
            person_id,
            cid,
            outcome=TurnOutcome(status="failed", error_code=code),
        )

    turns = browser.client.get(f"{BASE}/conversations/current").json()["turns"]

    errors = [t["error"] for t in turns]
    assert errors == [
        {"code": "budget-daily", "message": BUDGET_DAILY_TEXT},
        {"code": "spend-limit", "message": BUDGET_DAILY_TEXT},
        {"code": "refusal", "message": ERROR_TEXTS["refusal"]},
        # Codes the person never sees by name are shown as the plain internal error.
        {"code": "internal", "message": ERROR_TEXTS["internal"]},
        {"code": "internal", "message": ERROR_TEXTS["internal"]},
    ]


async def test_a_crisis_turn_and_an_unavailable_guard_show_their_fixed_texts_and_the_hr_contact(
    browser: Browser, app_engine: AsyncEngine
) -> None:
    tenant_id, person_id = sign_in(browser)
    cid = UUID(new_conversation(browser)["id"])
    await seed_turn(app_engine, tenant_id, person_id, cid, outcome=TurnOutcome(status="crisis"))
    await seed_turn(
        app_engine, tenant_id, person_id, cid, outcome=TurnOutcome(status="guard_unavailable")
    )

    crisis, unavailable = browser.client.get(f"{BASE}/conversations/current").json()["turns"]

    assert crisis["escalation"]["kind"] == "crisis"
    assert crisis["escalation"]["message"] == CRISIS_TEXT
    assert unavailable["escalation"]["kind"] == "unavailable"
    assert unavailable["escalation"]["message"] == UNAVAILABLE_TEXT
    contacts = crisis["escalation"]["hrContact"]
    assert contacts
    assert set(contacts[0]) == {"name", "workEmail", "jobTitle", "locationName"}
    assert (contacts[0]["jobTitle"], contacts[0]["locationName"]) == (
        "HR Business Partner",
        "Denver HQ",
    )
    assert crisis["answerText"] == ""


async def test_a_sensitive_answer_shows_the_hr_stub_after_it(
    browser: Browser, app_engine: AsyncEngine
) -> None:
    tenant_id, person_id = sign_in(browser)
    cid = UUID(new_conversation(browser)["id"])
    verdict = {"category": "sensitive", "kind": "harassment_discrimination"}
    await seed_turn(app_engine, tenant_id, person_id, cid, outcome=completed(guard_verdict=verdict))

    [turn] = browser.client.get(f"{BASE}/conversations/current").json()["turns"]

    assert turn["escalation"]["kind"] == "sensitive"
    assert turn["status"] == "completed"


async def test_a_budget_stop_after_a_sensitive_verdict_still_shows_the_hr_escalation(
    browser: Browser, app_engine: AsyncEngine
) -> None:
    """The stream sent it (sensitive topics go to a person); a stop before the guard ran has no
    verdict and shows none."""
    tenant_id, person_id = sign_in(browser)
    cid = UUID(new_conversation(browser)["id"])
    stop = TurnOutcome(
        status="failed",
        error_code="budget-daily",
        guard_verdict={"category": "sensitive", "kind": "pay", "injectionSuspected": False},
    )
    await seed_turn(app_engine, tenant_id, person_id, cid, outcome=stop)
    await seed_turn(
        app_engine,
        tenant_id,
        person_id,
        cid,
        outcome=TurnOutcome(status="failed", error_code="budget-daily"),
    )

    late, early = browser.client.get(f"{BASE}/conversations/current").json()["turns"]

    assert late["escalation"]["kind"] == "sensitive"
    assert early["escalation"] is None


def verdict_of(category: str, kind: str | None = None) -> dict[str, Any]:
    return {"category": category, "kind": kind, "injectionSuspected": False}


async def test_the_reloads_escalation_offers_a_case_only_for_a_flagged_verdict(
    browser: Browser, app_engine: AsyncEngine
) -> None:
    """The same rule as the stream's `offerCase` and the case service's flagged-turn check."""
    tenant_id, person_id = sign_in(browser)
    cid = UUID(new_conversation(browser)["id"])
    outcomes = {
        "sensitive completed": completed(guard_verdict=verdict_of("sensitive", "pay")),
        "sensitive failed": TurnOutcome(
            status="failed", error_code="model-unavailable", guard_verdict=verdict_of("sensitive")
        ),
        "sensitive stopped": TurnOutcome(
            status="stopped", guard_verdict=verdict_of("sensitive", "pay")
        ),
        "crisis": TurnOutcome(status="crisis", guard_verdict=verdict_of("crisis", "self_harm")),
        "crisis kind under ordinary": TurnOutcome(
            status="crisis", guard_verdict=verdict_of("ordinary", "self_harm")
        ),
        "crisis with no verdict": TurnOutcome(status="crisis"),
        "unavailable": TurnOutcome(status="guard_unavailable"),
        "sensitive kind under ordinary": completed(guard_verdict=verdict_of("ordinary", "pay")),
    }
    for outcome in outcomes.values():
        await seed_turn(app_engine, tenant_id, person_id, cid, outcome=outcome)

    turns = browser.client.get(f"{BASE}/conversations/current").json()["turns"]

    shown = {
        label: None if turn["escalation"] is None else turn["escalation"]["offerCase"]
        for label, turn in zip(outcomes, turns, strict=True)
    }
    assert shown == {
        "sensitive completed": True,
        "sensitive failed": True,
        "sensitive stopped": True,
        "crisis": True,
        "crisis kind under ordinary": False,
        "crisis with no verdict": False,
        "unavailable": False,
        # The panel follows the category (Phase 6, stage 4): an ordinary verdict with a topic shows
        # no panel on reload, as its stream sent none.
        "sensitive kind under ordinary": None,
    }


async def test_a_turn_with_a_case_shows_it_opened_and_only_to_its_owner(
    open_browser: OpenBrowser, app_engine: AsyncEngine
) -> None:
    priya, mateo = open_browser(), open_browser()
    cases: dict[str, str] = {}
    for name, browser in (("priya", priya), ("mateo", mateo)):
        tenant_id, person_id = sign_in(browser, name)
        cid = UUID(new_conversation(browser)["id"])
        flagged = await seed_turn(
            app_engine,
            tenant_id,
            person_id,
            cid,
            outcome=completed(guard_verdict=verdict_of("sensitive")),
        )
        await seed_turn(app_engine, tenant_id, person_id, cid, outcome=completed())
        if name == "priya":
            sent = browser.client.post(
                "/api/v1/cases",
                json={
                    "submissionId": str(uuid4()),
                    "category": "pay",
                    "text": "My pay was short.",
                    "turnId": str(flagged),
                },
                headers=browser.csrf,
            )
            assert sent.status_code == 201, sent.text
            cases[name] = sent.json()["case"]["replyBy"]

    [opened, other] = priya.client.get(f"{BASE}/conversations/current").json()["turns"]
    [theirs, _] = mateo.client.get(f"{BASE}/conversations/current").json()["turns"]

    assert opened["caseOpened"] == {"status": "new", "replyBy": cases["priya"]}
    # The other turn of the conversation has no case, and neither does Mateo's own flagged turn.
    assert other["caseOpened"] is None
    assert theirs["caseOpened"] is None


async def test_the_cases_by_turn_query_filters_by_person_even_for_a_session_that_reads_all(
    browser: Browser, app_engine: AsyncEngine
) -> None:
    # The keys tie a case to its opener's own turn, so no row can share another person's
    # conversation. HR's session reads every case, so only the query's own filter keeps it out.
    tenant_id, person_id = sign_in(browser)
    cid = UUID(new_conversation(browser)["id"])
    turn_id = await seed_turn(
        app_engine,
        tenant_id,
        person_id,
        cid,
        outcome=completed(guard_verdict=verdict_of("sensitive")),
    )
    sent = browser.client.post(
        "/api/v1/cases",
        json={
            "submissionId": str(uuid4()),
            "category": "pay",
            "text": "My pay was short.",
            "turnId": str(turn_id),
        },
        headers=browser.csrf,
    )
    assert sent.status_code == 201, sent.text

    async with tenant_session(app_engine, TenantContext(tenant_id, uuid4())) as db:
        await set_is_hr(db, True)
        theirs = await cases_by_turn(db, tenant_id, uuid4(), cid)
        owners = await cases_by_turn(db, tenant_id, person_id, cid)

    assert theirs == {}
    assert list(owners) == [turn_id]
    assert owners[turn_id]._fields == ("turn_id", "status", "reply_by")


async def test_the_reload_reads_the_conversations_cases_in_one_query(
    browser: Browser, app_engine: AsyncEngine
) -> None:
    tenant_id, person_id = sign_in(browser)
    cid = UUID(new_conversation(browser)["id"])
    for _ in range(4):
        await seed_turn(app_engine, tenant_id, person_id, cid, outcome=completed())
    statements: list[str] = []

    def count(conn: Any, cursor: Any, statement: str, *rest: Any) -> None:
        statements.append(statement)

    engine = browser.client.app.state.engine.sync_engine  # type: ignore[attr-defined]
    event.listen(engine, "before_cursor_execute", count)
    try:
        browser.client.get(f"{BASE}/conversations/current")
    finally:
        event.remove(engine, "before_cursor_execute", count)

    # No turn was flagged, so no case can exist and none is looked up.
    assert sum("FROM cases" in statement for statement in statements) == 0


async def test_the_reload_reads_the_conversations_cases_in_one_query_when_a_turn_is_flagged(
    browser: Browser, app_engine: AsyncEngine
) -> None:
    tenant_id, person_id = sign_in(browser)
    cid = UUID(new_conversation(browser)["id"])
    for _ in range(3):
        await seed_turn(app_engine, tenant_id, person_id, cid, outcome=completed())
    await seed_turn(
        app_engine,
        tenant_id,
        person_id,
        cid,
        outcome=completed(guard_verdict=verdict_of("sensitive")),
    )
    statements: list[str] = []

    def count(conn: Any, cursor: Any, statement: str, *rest: Any) -> None:
        statements.append(statement)

    engine = browser.client.app.state.engine.sync_engine  # type: ignore[attr-defined]
    event.listen(engine, "before_cursor_execute", count)
    try:
        browser.client.get(f"{BASE}/conversations/current")
    finally:
        event.remove(engine, "before_cursor_execute", count)

    assert sum("FROM cases" in statement for statement in statements) == 1


async def test_a_running_turn_is_shown_as_running(
    browser: Browser, app_engine: AsyncEngine
) -> None:
    tenant_id, person_id = sign_in(browser)
    cid = UUID(new_conversation(browser)["id"])
    await seed_turn(app_engine, tenant_id, person_id, cid)

    [turn] = browser.client.get(f"{BASE}/conversations/current").json()["turns"]

    assert turn["status"] == "running"
    assert turn["answerText"] == ""


async def test_a_stopped_turn_keeps_its_partial_answer_and_shows_no_error(
    browser: Browser, app_engine: AsyncEngine
) -> None:
    tenant_id, person_id = sign_in(browser)
    cid = UUID(new_conversation(browser)["id"])
    stopped = TurnOutcome(
        status="stopped", answer_text="You get 40 ho", error_code="stopped-by-test"
    )
    await seed_turn(app_engine, tenant_id, person_id, cid, outcome=stopped)

    [turn] = browser.client.get(f"{BASE}/conversations/current").json()["turns"]

    assert (turn["status"], turn["answerText"]) == ("stopped", "You get 40 ho")
    assert (turn["error"], turn["escalation"], turn["incomplete"]) == (None, None, False)


async def test_a_turn_running_past_the_abandoned_limit_is_shown_as_failed_without_writing(
    browser: Browser, app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    tenant_id, person_id = sign_in(browser)
    cid = UUID(new_conversation(browser)["id"])
    abandoned = await seed_turn(app_engine, tenant_id, person_id, cid, question="Old?")
    async with owner_engine.begin() as connection:
        await connection.execute(
            text("UPDATE ai_turns SET started_at = now() - interval '11 minutes' WHERE id = :id"),
            {"id": abandoned},
        )
    [old] = browser.client.get(f"{BASE}/conversations/current").json()["turns"]

    assert old["status"] == "failed"
    assert old["error"] == {"code": "internal", "message": ERROR_TEXTS["internal"]}
    # The read wrote nothing: the row is as it was until the next turn recovers it.
    async with owner_engine.connect() as connection:
        stored = (
            await connection.execute(
                text("SELECT status, error_code FROM ai_turns WHERE id = :id"), {"id": abandoned}
            )
        ).one()
    assert tuple(stored) == ("running", None)


SENSITIVE_VERDICT = {"category": "sensitive", "kind": "pay", "injectionSuspected": False}


async def test_an_abandoned_turn_shows_no_escalation_the_stream_never_sent(
    browser: Browser, app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    """Its stream died, so no escalation was sent, whether the page remaps it or it was recovered
    and stored as `abandoned`."""
    tenant_id, person_id = sign_in(browser)
    cid = UUID(new_conversation(browser)["id"])
    # Stored as abandoned by recovery, with a sensitive verdict.
    await seed_turn(
        app_engine,
        tenant_id,
        person_id,
        cid,
        outcome=TurnOutcome(
            status="failed", error_code="abandoned", guard_verdict=SENSITIVE_VERDICT
        ),
    )
    # Still `running` past the limit, with a sensitive verdict somehow on the row.
    running = await seed_turn(app_engine, tenant_id, person_id, cid)
    async with owner_engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE ai_turns SET started_at = now() - interval '11 minutes',"
                " guard_verdict = CAST(:verdict AS jsonb) WHERE id = :id"
            ),
            {"id": running, "verdict": json.dumps(SENSITIVE_VERDICT)},
        )

    stored, remapped = browser.client.get(f"{BASE}/conversations/current").json()["turns"]

    assert (stored["status"], stored["escalation"]) == ("failed", None)
    assert (remapped["status"], remapped["escalation"]) == ("failed", None)
    assert remapped["error"]["code"] == "internal"


async def test_the_page_decides_a_turn_is_abandoned_by_the_databases_clock(
    browser: Browser,
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Postgres decides it for the POST (`has_running_turn`, `recover_abandoned`), so the page
    must too, whatever this server's clock says."""
    from datetime import UTC, datetime

    class FarFuture(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> "FarFuture":
            return cls.fromtimestamp(datetime.now(UTC).timestamp() + 86_400, tz)

    tenant_id, person_id = sign_in(browser)
    cid = UUID(new_conversation(browser)["id"])
    running = await seed_turn(app_engine, tenant_id, person_id, cid)
    async with owner_engine.begin() as connection:
        await connection.execute(
            text("UPDATE ai_turns SET started_at = now() - interval '2 minutes' WHERE id = :id"),
            {"id": running},
        )
    monkeypatch.setattr("app.modules.assistant.routes.datetime", FarFuture)

    [turn] = browser.client.get(f"{BASE}/conversations/current").json()["turns"]

    assert turn["status"] == "running"


async def test_another_persons_conversation_is_never_returned(
    browser: Browser, app_engine: AsyncEngine
) -> None:
    tenant_id, priya = sign_in(browser, "priya")
    cid = UUID(new_conversation(browser)["id"])
    await seed_turn(app_engine, tenant_id, priya, cid, outcome=completed())
    assert len(browser.client.get(f"{BASE}/conversations/current").json()["turns"]) == 1

    switched = browser.client.put(
        "/api/v1/session/persona", json={"persona": "dana"}, headers=browser.csrf
    )
    assert switched.status_code == 200

    # Dana is HR, and Postgres still shows her none of Priya's conversations.
    assert browser.client.get(f"{BASE}/conversations/current").json() is None


# --- The budget banner and the long-history flags -------------------------------------------


async def test_a_sandbox_with_money_left_but_less_than_a_turn_needs_is_at_its_cap(
    browser: Browser, app_engine: AsyncEngine
) -> None:
    tenant_id, person_id = sign_in(browser)
    cid = UUID(new_conversation(browser)["id"])
    turn_id = await seed_turn(app_engine, tenant_id, person_id, cid, outcome=completed())
    # $0.10 of the $1.00 cap is left: not zero, but under the room a turn needs.
    await add_spend(app_engine, tenant_id, person_id, turn_id, "0.90")

    budget = browser.client.get(f"{BASE}/conversations/current").json()["budget"]

    assert budget["sandboxReached"] is True
    assert budget["sandboxRemainingCents"] == 10


async def test_a_sandbox_with_room_for_a_turn_is_not_at_its_cap(
    browser: Browser, app_engine: AsyncEngine
) -> None:
    tenant_id, person_id = sign_in(browser)
    cid = UUID(new_conversation(browser)["id"])
    turn_id = await seed_turn(app_engine, tenant_id, person_id, cid, outcome=completed())
    await add_spend(app_engine, tenant_id, person_id, turn_id, "0.50")

    budget = browser.client.get(f"{BASE}/conversations/current").json()["budget"]

    assert budget["sandboxReached"] is False
    assert budget["sandboxRemainingCents"] == 50


async def test_an_overspent_sandbox_reports_no_negative_remaining(
    browser: Browser, app_engine: AsyncEngine
) -> None:
    tenant_id, person_id = sign_in(browser)
    cid = UUID(new_conversation(browser)["id"])
    turn_id = await seed_turn(app_engine, tenant_id, person_id, cid, outcome=completed())
    await add_spend(app_engine, tenant_id, person_id, turn_id, "1.20")

    budget = browser.client.get(f"{BASE}/conversations/current").json()["budget"]

    assert budget["sandboxRemainingCents"] == 0


def test_a_day_with_less_than_a_turn_left_is_at_its_cap(
    open_browser_with: OpenBrowserWith,
) -> None:
    browser = open_browser_with(ai_daily_budget_usd=Decimal("0.05"))
    sign_in(browser)
    new_conversation(browser)

    budget = browser.client.get(f"{BASE}/conversations/current").json()["budget"]

    assert budget["dailyReached"] is True
    assert budget["sandboxReached"] is False


async def add_history(
    engine: AsyncEngine,
    tenant_id: UUID,
    person_id: UUID,
    conversation_id: UUID,
    turn_id: UUID,
    characters: int,
) -> None:
    async with tenant_session(engine, TenantContext(tenant_id, person_id)) as db:
        conversation = await db.get(AiConversation, conversation_id)
        assert conversation is not None
        db.add(
            message_row(
                conversation,
                turn_id,
                position=0,
                role="user",
                content=[{"type": "text", "text": "y" * characters}],
            )
        )


@pytest.mark.parametrize(
    ("characters", "long", "too_long"),
    [
        (100_000, False, False),
        (130_000, True, False),
        (170_000, True, True),
    ],
)
async def test_a_long_history_is_offered_a_new_conversation_and_a_longer_one_is_full(
    browser: Browser,
    app_engine: AsyncEngine,
    characters: int,
    long: bool,
    too_long: bool,
) -> None:
    tenant_id, person_id = sign_in(browser)
    cid = UUID(new_conversation(browser)["id"])
    turn_id = await seed_turn(app_engine, tenant_id, person_id, cid, outcome=completed())
    await add_history(app_engine, tenant_id, person_id, cid, turn_id, characters)

    current = browser.client.get(f"{BASE}/conversations/current").json()

    assert (current["longHistory"], current["historyTooLong"]) == (long, too_long)


# --- Feedback -------------------------------------------------------------------------------


async def test_feedback_is_recorded_once_on_a_completed_turn(
    browser: Browser, app_engine: AsyncEngine
) -> None:
    tenant_id, person_id = sign_in(browser)
    cid = UUID(new_conversation(browser)["id"])
    turn_id = await seed_turn(app_engine, tenant_id, person_id, cid, outcome=completed())

    first = browser.client.post(
        f"{BASE}/turns/{turn_id}/feedback", json={"helpful": True}, headers=browser.csrf
    )
    second = browser.client.post(
        f"{BASE}/turns/{turn_id}/feedback", json={"helpful": False}, headers=browser.csrf
    )

    assert first.status_code == 201
    assert first.json() == {"turnId": str(turn_id), "helpful": True, "reason": None}
    assert second.status_code == 409
    assert second.headers["content-type"] == "application/problem+json"
    [turn] = browser.client.get(f"{BASE}/conversations/current").json()["turns"]
    assert turn["feedback"] == {"helpful": True, "reason": None}


async def test_a_reason_is_kept_up_to_500_characters(
    browser: Browser, app_engine: AsyncEngine
) -> None:
    tenant_id, person_id = sign_in(browser)
    cid = UUID(new_conversation(browser)["id"])
    ok = await seed_turn(app_engine, tenant_id, person_id, cid, outcome=completed())
    too_long = await seed_turn(app_engine, tenant_id, person_id, cid, outcome=completed())

    accepted = browser.client.post(
        f"{BASE}/turns/{ok}/feedback",
        json={"helpful": False, "reason": "r" * 500},
        headers=browser.csrf,
    )
    refused = browser.client.post(
        f"{BASE}/turns/{too_long}/feedback",
        json={"helpful": False, "reason": "r" * 501},
        headers=browser.csrf,
    )

    assert accepted.status_code == 201
    assert len(accepted.json()["reason"]) == 500
    assert refused.status_code == 422
    assert refused.headers["content-type"] == "application/problem+json"


async def test_a_reason_with_a_nul_character_is_refused(
    browser: Browser, app_engine: AsyncEngine
) -> None:
    tenant_id, person_id = sign_in(browser)
    cid = UUID(new_conversation(browser)["id"])
    turn_id = await seed_turn(app_engine, tenant_id, person_id, cid, outcome=completed())

    response = browser.client.post(
        f"{BASE}/turns/{turn_id}/feedback",
        json={"helpful": False, "reason": "a\u0000b"},
        headers=browser.csrf,
    )

    assert response.status_code == 422


async def test_a_reason_with_a_lone_surrogate_is_refused_not_a_500(
    open_browser: OpenBrowser, app_engine: AsyncEngine
) -> None:
    browser = open_browser(raise_server_exceptions=False)
    tenant_id, person_id = sign_in(browser)
    cid = UUID(new_conversation(browser)["id"])
    turn_id = await seed_turn(app_engine, tenant_id, person_id, cid, outcome=completed())

    response = browser.client.post(
        f"{BASE}/turns/{turn_id}/feedback",
        content=json.dumps({"helpful": False, "reason": "a\ud800b"}),
        headers={**browser.csrf, "Content-Type": "application/json"},
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "reason", ["My SSN is 078-05-1120", "card 4111\u00a01111\u00a01111\u00a01111"]
)
async def test_a_reason_with_a_social_security_or_card_number_is_refused_and_not_stored(
    browser: Browser, app_engine: AsyncEngine, reason: str
) -> None:
    tenant_id, person_id = sign_in(browser)
    cid = UUID(new_conversation(browser)["id"])
    turn_id = await seed_turn(app_engine, tenant_id, person_id, cid, outcome=completed())

    response = browser.client.post(
        f"{BASE}/turns/{turn_id}/feedback",
        json={"helpful": False, "reason": reason},
        headers=browser.csrf,
    )

    assert response.status_code == 422
    assert response.json()["type"] == "personal-data"
    assert "078-05-1120" not in response.text
    [turn] = browser.client.get(f"{BASE}/conversations/current").json()["turns"]
    assert turn["feedback"] is None


@pytest.mark.parametrize(
    "outcome",
    [
        None,
        TurnOutcome(status="failed", error_code="refusal"),
        TurnOutcome(status="stopped"),
        TurnOutcome(status="crisis"),
        TurnOutcome(status="guard_unavailable"),
    ],
)
async def test_feedback_on_a_turn_that_did_not_complete_is_a_conflict(
    browser: Browser, app_engine: AsyncEngine, outcome: TurnOutcome | None
) -> None:
    tenant_id, person_id = sign_in(browser)
    cid = UUID(new_conversation(browser)["id"])
    turn_id = await seed_turn(app_engine, tenant_id, person_id, cid, outcome=outcome)

    response = browser.client.post(
        f"{BASE}/turns/{turn_id}/feedback", json={"helpful": True}, headers=browser.csrf
    )

    assert response.status_code == 409


async def test_feedback_on_another_persons_turn_is_a_404_not_a_403(
    browser: Browser, app_engine: AsyncEngine
) -> None:
    tenant_id, priya = sign_in(browser, "priya")
    cid = UUID(new_conversation(browser)["id"])
    turn_id = await seed_turn(app_engine, tenant_id, priya, cid, outcome=completed())
    browser.client.put("/api/v1/session/persona", json={"persona": "dana"}, headers=browser.csrf)

    mine_not = browser.client.post(
        f"{BASE}/turns/{turn_id}/feedback", json={"helpful": True}, headers=browser.csrf
    )
    unknown = browser.client.post(
        f"{BASE}/turns/{uuid4()}/feedback", json={"helpful": True}, headers=browser.csrf
    )

    assert mine_not.status_code == 404
    assert unknown.status_code == 404
    # The same answer for both, so an ID can't be probed.
    assert mine_not.json()["detail"] == unknown.json()["detail"]


async def test_a_sandbox_without_a_handbook_version_still_gets_its_conversation(
    browser: Browser, owner_engine: AsyncEngine, app_engine: AsyncEngine
) -> None:
    """The version only sizes the banner's estimate (its label is a few characters), so reading
    the conversation does not fail for want of one."""
    tenant_id, person_id = sign_in(browser)
    created = new_conversation(browser)
    cid = UUID(created["id"])
    await seed_turn(app_engine, tenant_id, person_id, cid, outcome=completed())
    async with owner_engine.begin() as connection:
        await connection.execute(
            text("UPDATE tenants SET handbook_version_id = NULL WHERE id = :id"), {"id": tenant_id}
        )

    response = browser.client.get(f"{BASE}/conversations/current")
    created_again = browser.client.post(f"{BASE}/conversations", headers=browser.csrf)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == created["id"]
    assert len(body["turns"]) == 1
    assert body["budget"]["sandboxReached"] is False
    assert created_again.status_code == 201


# --- The HR team on a "not found" card, section titles, the banner, and the browser's texts ----


def hr_dana() -> dict[str, str]:
    return {
        "name": "Dana Whitfield",
        "jobTitle": "HR Business Partner",
        "locationName": "Denver HQ",
    }


async def test_the_conversations_hr_contacts_are_empty_when_no_turn_needs_them(
    browser: Browser, app_engine: AsyncEngine
) -> None:
    tenant_id, person_id = sign_in(browser)
    cid = UUID(new_conversation(browser)["id"])
    await seed_turn(app_engine, tenant_id, person_id, cid, outcome=completed())

    body = browser.client.get(f"{BASE}/conversations/current").json()

    assert body["hrContacts"] == []
    assert [t["notFound"] for t in body["turns"]] == [False]


async def test_a_turn_that_searched_and_cited_nothing_is_not_found_and_brings_the_contacts(
    browser: Browser, app_engine: AsyncEngine
) -> None:
    tenant_id, person_id = sign_in(browser)
    cid = UUID(new_conversation(browser)["id"])
    await seed_turn(
        app_engine,
        tenant_id,
        person_id,
        cid,
        outcome=completed(citations=[], answer_text="I couldn't find that."),
    )

    body = browser.client.get(f"{BASE}/conversations/current").json()

    [turn] = body["turns"]
    assert turn["notFound"] is True
    assert turn["escalation"] is None
    [contact] = body["hrContacts"]
    assert {k: contact[k] for k in ("name", "jobTitle", "locationName")} == hr_dana()
    assert contact["workEmail"].startswith("dana.whitfield@")


async def test_a_sensitive_turn_keeps_its_own_contacts_and_is_not_also_not_found(
    browser: Browser, app_engine: AsyncEngine
) -> None:
    tenant_id, person_id = sign_in(browser)
    cid = UUID(new_conversation(browser)["id"])
    verdict = {"category": "sensitive", "kind": "harassment_discrimination"}
    await seed_turn(
        app_engine,
        tenant_id,
        person_id,
        cid,
        outcome=completed(guard_verdict=verdict, citations=[]),
    )

    body = browser.client.get(f"{BASE}/conversations/current").json()

    [turn] = body["turns"]
    assert turn["notFound"] is False
    assert turn["escalation"]["hrContact"][0]["jobTitle"] == "HR Business Partner"
    assert turn["escalation"]["hrContact"][0]["locationName"] == "Denver HQ"
    assert len(body["hrContacts"]) == 1


async def test_a_new_conversation_has_no_hr_contacts(browser: Browser) -> None:
    sign_in(browser)

    assert new_conversation(browser)["hrContacts"] == []


async def seed_sources(
    engine: AsyncEngine, tenant_id: UUID, person_id: UUID, conversation_id: UUID, turn_id: UUID
) -> None:
    """The `search_result` blocks the model was sent for a turn, as the store keeps them."""
    async with tenant_session(engine, TenantContext(tenant_id, person_id)) as db:
        conversation = await db.get(AiConversation, conversation_id)
        assert conversation is not None
        db.add(
            message_row(
                conversation,
                turn_id,
                position=0,
                role="user",
                content=[{"type": "text", "text": "results"}],
                sources=[
                    {
                        "sectionId": "CA-4.3",
                        "passageIds": ["p1", "p2"],
                        "title": "Sick leave",
                        "groupName": "California addendum",
                        "audienceLabel": "California",
                        "lastUpdated": "2026-09-12",
                        "deepLink": "/handbook/CA-4.3?passage=p2",
                    }
                ],
            )
        )


async def test_each_retrieved_section_carries_its_title_and_group_from_the_stored_sources(
    browser: Browser, app_engine: AsyncEngine
) -> None:
    tenant_id, person_id = sign_in(browser)
    cid = UUID(new_conversation(browser)["id"])
    sections = [
        {"sectionId": "CA-4.3", "passageIds": ["p1", "p2"]},
        {"sectionId": "GONE-9.9", "passageIds": ["p1"]},
    ]
    first = await seed_turn(
        app_engine, tenant_id, person_id, cid, outcome=completed(sections_retrieved=sections)
    )
    await seed_sources(app_engine, tenant_id, person_id, cid, first)
    await seed_turn(
        app_engine,
        tenant_id,
        person_id,
        cid,
        outcome=completed(sections_retrieved=[sections[0]]),
    )

    one, two = browser.client.get(f"{BASE}/conversations/current").json()["turns"]

    assert one["sections"] == [
        {
            "sectionId": "CA-4.3",
            "passageIds": ["p1", "p2"],
            "title": "Sick leave",
            "groupName": "California addendum",
        },
        # A section the stored sources don't know stays untitled.
        {"sectionId": "GONE-9.9", "passageIds": ["p1"], "title": None, "groupName": None},
    ]
    assert two["sections"][0]["title"] == "Sick leave"


async def test_the_sections_are_looked_up_once_per_request_not_once_per_turn(
    browser: Browser, app_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant_id, person_id = sign_in(browser)
    cid = UUID(new_conversation(browser)["id"])
    for _ in range(3):
        await seed_turn(app_engine, tenant_id, person_id, cid, outcome=completed())
    lookups: list[UUID] = []

    async def counting(db: Any, conversation_id: UUID) -> Any:
        lookups.append(conversation_id)
        return await section_names(db, conversation_id)

    monkeypatch.setattr("app.modules.assistant.routes.section_names", counting)

    turns = browser.client.get(f"{BASE}/conversations/current").json()["turns"]

    assert len(turns) == 3
    assert lookups == [cid]


async def seed_source_messages(
    engine: AsyncEngine,
    tenant_id: UUID,
    person_id: UUID,
    conversation_id: UUID,
    turn_id: UUID,
    messages: list[list[dict[str, Any]] | None],
) -> None:
    """One stored message per entry, each with the given `search_result` sources (or none)."""
    async with tenant_session(engine, TenantContext(tenant_id, person_id)) as db:
        conversation = await db.get(AiConversation, conversation_id)
        assert conversation is not None
        for position, sources in enumerate(messages):
            db.add(
                message_row(
                    conversation,
                    turn_id,
                    position=position,
                    role="user",
                    content=[{"type": "text", "text": "results"}],
                    sources=sources,
                )
            )


def source_entry(section_id: str, title: str, group_name: str, passage: str) -> dict[str, Any]:
    return {
        "sectionId": section_id,
        "passageIds": [passage],
        "title": title,
        "groupName": group_name,
        "audienceLabel": "Everyone",
        "lastUpdated": "2026-09-12",
        "deepLink": f"/handbook/{section_id}?passage={passage}",
    }


async def test_repeated_sections_in_the_stored_sources_give_the_same_titles_and_groups(
    browser: Browser, app_engine: AsyncEngine
) -> None:
    tenant_id, person_id = sign_in(browser)
    cid = UUID(new_conversation(browser)["id"])
    sick = source_entry("CA-4.3", "Sick leave", "California addendum", "p1")
    company = source_entry("4.3", "Sick leave", "Company handbook", "p1")
    turn = await seed_turn(
        app_engine,
        tenant_id,
        person_id,
        cid,
        outcome=completed(
            sections_retrieved=[
                {"sectionId": "CA-4.3", "passageIds": ["p1"]},
                {"sectionId": "4.3", "passageIds": ["p1"]},
                {"sectionId": "4.2", "passageIds": ["p1"]},
            ]
        ),
    )
    await seed_source_messages(
        app_engine,
        tenant_id,
        person_id,
        cid,
        turn,
        [
            # Each section several times, across messages and within one, and a message with none.
            [sick, company, sick],
            None,
            [sick, source_entry("4.2", "Paid time off", "Company handbook", "p1"), company],
            [],
        ],
    )

    (one,) = browser.client.get(f"{BASE}/conversations/current").json()["turns"]

    assert {s["sectionId"]: (s["title"], s["groupName"]) for s in one["sections"]} == {
        "CA-4.3": ("Sick leave", "California addendum"),
        "4.3": ("Sick leave", "Company handbook"),
        "4.2": ("Paid time off", "Company handbook"),
    }


async def test_a_block_without_a_title_does_not_hide_the_real_one(
    browser: Browser, app_engine: AsyncEngine
) -> None:
    tenant_id, person_id = sign_in(browser)
    cid = UUID(new_conversation(browser)["id"])
    turn = await seed_turn(
        app_engine,
        tenant_id,
        person_id,
        cid,
        outcome=completed(sections_retrieved=[{"sectionId": "4.3", "passageIds": ["p1"]}]),
    )
    real = source_entry("4.3", "Sick leave", "Company handbook", "p1")
    no_title = {k: v for k, v in real.items() if k not in ("title", "groupName")}
    null_title = {**real, "title": None, "groupName": None}
    await seed_source_messages(
        app_engine, tenant_id, person_id, cid, turn, [[real], [no_title], [null_title]]
    )

    (one,) = browser.client.get(f"{BASE}/conversations/current").json()["turns"]

    assert (one["sections"][0]["title"], one["sections"][0]["groupName"]) == (
        "Sick leave",
        "Company handbook",
    )


async def test_only_this_conversations_sources_name_its_sections(
    browser: Browser, app_engine: AsyncEngine
) -> None:
    tenant_id, person_id = sign_in(browser)
    other = UUID(new_conversation(browser)["id"])
    other_turn = await seed_turn(app_engine, tenant_id, person_id, other, outcome=completed())
    await seed_source_messages(
        app_engine,
        tenant_id,
        person_id,
        other,
        other_turn,
        [[source_entry("CA-4.3", "Not this one", "Elsewhere", "p1")]],
    )
    cid = UUID(new_conversation(browser)["id"])
    await seed_turn(
        app_engine,
        tenant_id,
        person_id,
        cid,
        outcome=completed(sections_retrieved=[{"sectionId": "CA-4.3", "passageIds": ["p1"]}]),
    )

    (one,) = browser.client.get(f"{BASE}/conversations/current").json()["turns"]

    assert one["sections"][0]["title"] is None


async def test_each_turns_ending_is_worked_out_once_per_read(
    browser: Browser, app_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant_id, person_id = sign_in(browser)
    cid = UUID(new_conversation(browser)["id"])
    for _ in range(3):
        await seed_turn(app_engine, tenant_id, person_id, cid, outcome=completed())
    calls: list[Any] = []

    from app.modules.assistant import display

    original = display.ending

    def counting(turn: Any, now: Any) -> Any:
        calls.append(turn.id)
        return original(turn, now)

    monkeypatch.setattr(display, "ending", counting)

    turns = browser.client.get(f"{BASE}/conversations/current").json()["turns"]

    assert len(turns) == 3
    assert len(calls) == 3
    assert len(set(calls)) == 3


def test_no_banner_while_both_budgets_have_room(browser: Browser) -> None:
    sign_in(browser)
    new_conversation(browser)

    budget = browser.client.get(f"{BASE}/conversations/current").json()["budget"]

    assert budget["banner"] is None


async def test_the_sandbox_banner_carries_the_sandbox_text(
    browser: Browser, app_engine: AsyncEngine
) -> None:
    tenant_id, person_id = sign_in(browser)
    cid = UUID(new_conversation(browser)["id"])
    turn_id = await seed_turn(app_engine, tenant_id, person_id, cid, outcome=completed())
    await add_spend(app_engine, tenant_id, person_id, turn_id, "0.95")

    budget = browser.client.get(f"{BASE}/conversations/current").json()["budget"]

    assert budget["banner"] == {"kind": "sandbox", "message": BUDGET_SANDBOX_TEXT}


def test_the_daily_banner_carries_the_daily_text(open_browser_with: OpenBrowserWith) -> None:
    browser = open_browser_with(ai_daily_budget_usd=Decimal("0.05"))
    sign_in(browser)
    new_conversation(browser)

    budget = browser.client.get(f"{BASE}/conversations/current").json()["budget"]

    assert (budget["dailyReached"], budget["sandboxReached"]) == (True, False)
    assert budget["banner"] == {"kind": "daily", "message": BUDGET_DAILY_TEXT}


async def test_when_both_budgets_are_reached_the_daily_banner_wins(
    open_browser_with: OpenBrowserWith, app_engine: AsyncEngine
) -> None:
    """A new sandbox would not help when the day is spent."""
    browser = open_browser_with(ai_daily_budget_usd=Decimal("0.05"))
    tenant_id, person_id = sign_in(browser)
    cid = UUID(new_conversation(browser)["id"])
    turn_id = await seed_turn(app_engine, tenant_id, person_id, cid, outcome=completed())
    await add_spend(app_engine, tenant_id, person_id, turn_id, "0.95")

    budget = browser.client.get(f"{BASE}/conversations/current").json()["budget"]

    assert (budget["dailyReached"], budget["sandboxReached"]) == (True, True)
    assert budget["banner"] == {"kind": "daily", "message": BUDGET_DAILY_TEXT}


def test_the_budget_route_answers_before_there_is_a_conversation(browser: Browser) -> None:
    sign_in(browser)

    response = browser.client.get(f"{BASE}/budget")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    budget = response.json()
    assert (budget["sandboxReached"], budget["dailyReached"], budget["banner"]) == (
        False,
        False,
        None,
    )
    assert budget["sandboxRemainingCents"] > 0


def test_the_daily_cap_shows_before_the_first_conversation(
    open_browser_with: OpenBrowserWith,
) -> None:
    browser = open_browser_with(ai_daily_budget_usd=Decimal("0.05"))
    sign_in(browser)

    budget = browser.client.get(f"{BASE}/budget").json()

    assert browser.client.get(f"{BASE}/conversations/current").json() is None
    assert (budget["dailyReached"], budget["sandboxReached"]) == (True, False)
    assert budget["banner"] == {"kind": "daily", "message": BUDGET_DAILY_TEXT}


async def test_the_sandbox_cap_shows_with_the_sandbox_text(
    browser: Browser, app_engine: AsyncEngine
) -> None:
    tenant_id, person_id = sign_in(browser)
    cid = UUID(new_conversation(browser)["id"])
    turn_id = await seed_turn(app_engine, tenant_id, person_id, cid, outcome=completed())
    await add_spend(app_engine, tenant_id, person_id, turn_id, "0.95")

    budget = browser.client.get(f"{BASE}/budget").json()

    assert (budget["sandboxReached"], budget["dailyReached"]) == (True, False)
    assert budget["banner"] == {"kind": "sandbox", "message": BUDGET_SANDBOX_TEXT}


async def test_when_both_caps_are_reached_the_budget_route_gives_the_daily_banner(
    open_browser_with: OpenBrowserWith, app_engine: AsyncEngine
) -> None:
    browser = open_browser_with(ai_daily_budget_usd=Decimal("0.05"))
    tenant_id, person_id = sign_in(browser)
    cid = UUID(new_conversation(browser)["id"])
    turn_id = await seed_turn(app_engine, tenant_id, person_id, cid, outcome=completed())
    await add_spend(app_engine, tenant_id, person_id, turn_id, "0.95")

    budget = browser.client.get(f"{BASE}/budget").json()

    assert (budget["dailyReached"], budget["sandboxReached"]) == (True, True)
    assert budget["banner"] == {"kind": "daily", "message": BUDGET_DAILY_TEXT}


async def test_the_budget_route_and_the_conversation_never_disagree(
    open_browser_with: OpenBrowserWith, app_engine: AsyncEngine
) -> None:
    browser = open_browser_with(ai_daily_budget_usd=Decimal("0.05"))
    tenant_id, person_id = sign_in(browser)
    cid = UUID(new_conversation(browser)["id"])
    turn_id = await seed_turn(app_engine, tenant_id, person_id, cid, outcome=completed())
    await add_spend(app_engine, tenant_id, person_id, turn_id, "0.5")

    from_conversation = browser.client.get(f"{BASE}/conversations/current").json()["budget"]

    assert browser.client.get(f"{BASE}/budget").json() == from_conversation


async def test_the_budget_route_sizes_the_estimate_with_the_conversations_history_or_none(
    browser: Browser, app_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.modules.assistant import routes

    seen: list[dict[str, Any]] = []
    original = routes.budget_out

    async def recording(*args: Any, **kwargs: Any) -> Any:
        seen.append(kwargs)
        return await original(*args, **kwargs)

    monkeypatch.setattr(routes, "budget_out", recording)
    tenant_id, person_id = sign_in(browser)

    assert browser.client.get(f"{BASE}/budget").status_code == 200
    assert seen[-1]["history"] == []

    cid = UUID(new_conversation(browser)["id"])
    turn = await seed_turn(app_engine, tenant_id, person_id, cid, outcome=completed())
    await seed_source_messages(
        app_engine,
        tenant_id,
        person_id,
        cid,
        turn,
        [[source_entry("4.3", "Sick", "Handbook", "p1")]],
    )
    assert browser.client.get(f"{BASE}/budget").status_code == 200
    assert seen[-1]["history"] != []


def test_the_texts_route_returns_the_two_fixed_texts_the_composer_needs(browser: Browser) -> None:
    sign_in(browser)

    response = browser.client.get(f"{BASE}/texts")

    assert response.status_code == 200
    assert response.json() == {
        "personalData": PERSONAL_DATA_TEXT,
        "stillAnswering": STILL_ANSWERING_TEXT,
    }
    assert response.headers["cache-control"] == "no-store"


def test_the_texts_are_the_words_the_two_problems_use(browser: Browser) -> None:
    sign_in(browser)
    conversation_id = new_conversation(browser)["id"]

    personal = browser.client.post(
        f"{BASE}/conversations/{conversation_id}/turns",
        json={"question": "My number is 078-05-1120"},
        headers=browser.csrf,
    )

    assert (personal.status_code, personal.json()["type"]) == (422, "personal-data")
    assert personal.json()["detail"] == PERSONAL_DATA_TEXT


# --- Encrypted text (Phase 6, stage 1) --------------------------------------------------------


async def test_the_page_shows_decrypted_turns_and_a_turn_with_no_answer_as_empty(
    browser: Browser, app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    tenant_id, person_id = sign_in(browser)
    cid = UUID(new_conversation(browser)["id"])
    await seed_turn(
        app_engine, tenant_id, person_id, cid, question="Ended turn?", outcome=completed()
    )
    # The second turn is still running, so it has no answer yet.
    await seed_turn(app_engine, tenant_id, person_id, cid, question="Running turn?")

    ended, running = browser.client.get(f"{BASE}/conversations/current").json()["turns"]

    assert (ended["question"], ended["answerText"]) == (
        "Ended turn?",
        "You get 40 hours of paid sick leave.",
    )
    assert ended["toolCalls"][0]["inputSummary"] == "sick leave"
    assert (running["question"], running["answerText"]) == ("Running turn?", "")
    async with owner_engine.connect() as connection:
        raw: Sequence[Any] = (
            (
                await connection.execute(
                    text("SELECT row_to_json(t)::text FROM ai_turns t WHERE conversation_id = :c"),
                    {"c": cid},
                )
            )
            .scalars()
            .all()
        )
    for plaintext in (
        "Ended turn?",
        "Running turn?",
        "You get 40 hours",
        'inputSummary": "sick leave',
    ):
        assert not any(plaintext in row for row in raw)


async def test_a_feedback_reason_is_sealed_at_rest_and_shown_back_to_its_owner(
    browser: Browser, app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    tenant_id, person_id = sign_in(browser)
    cid = UUID(new_conversation(browser)["id"])
    turn_id = await seed_turn(app_engine, tenant_id, person_id, cid, outcome=completed())
    reason = "It missed the part about my state"

    posted = browser.client.post(
        f"{BASE}/turns/{turn_id}/feedback",
        json={"helpful": False, "reason": reason},
        headers=browser.csrf,
    )

    assert posted.status_code == 201
    assert posted.json()["reason"] == reason
    async with owner_engine.connect() as connection:
        [(ciphertext, whole_row)] = (
            await connection.execute(
                text(
                    "SELECT reason_ciphertext, row_to_json(f)::text FROM ai_feedback f"
                    " WHERE turn_id = :t"
                ),
                {"t": turn_id},
            )
        ).all()
    assert reason.encode() not in bytes(ciphertext)
    assert reason not in whole_row
    [turn] = browser.client.get(f"{BASE}/conversations/current").json()["turns"]
    assert turn["feedback"] == {"helpful": False, "reason": reason}
