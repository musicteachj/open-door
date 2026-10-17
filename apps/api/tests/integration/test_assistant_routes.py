"""The assistant's conversation routes: the current conversation, a new one, and feedback.

The turns these routes show are written straight into the database as the person, with the store's
own functions, so these tests do not depend on the stream.
"""

import json
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.ai.conversations import (
    CURRENT_PINS,
    TurnOutcome,
    finish_turn,
    start_turn,
)
from app.ai.fixed_texts import BUDGET_DAILY_TEXT, CRISIS_TEXT, ERROR_TEXTS, UNAVAILABLE_TEXT
from app.db.models import AiConversation, AiMessage, AiSpend
from app.db.tenancy import TenantContext, tenant_session
from tests.integration.conftest import Browser, OpenBrowser, OpenBrowserWith

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
        turn = await start_turn(db, conversation, question)
        if outcome is not None:
            await finish_turn(db, turn.id, outcome)
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
    ]

    assert [r.status_code for r in responses] == [401] * 4
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
    }
    assert created["longHistory"] is False
    assert created["historyTooLong"] is False
    assert set(created) == {
        "id",
        "createdAt",
        "turns",
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
    assert one["sections"] == [{"sectionId": "CA-4.3", "passageIds": ["p1", "p2"]}]
    assert one["feedback"] == {"helpful": False, "reason": "Not what I asked"}
    assert two["feedback"] is None
    assert two["incomplete"] is True
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
    assert set(contacts[0]) == {"name", "workEmail"}
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
        db.add(
            AiMessage(
                tenant_id=tenant_id,
                person_id=person_id,
                conversation_id=conversation_id,
                turn_id=turn_id,
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
