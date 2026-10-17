"""The turn stream: the checks that refuse before it opens, and the events, headers, and heartbeat
of one that does.

The sync test client reads a whole response before returning, which is right for these. The tests
that need a client to disconnect, a write to stall, or two requests to overlap are in
`test_turn_stream_connection.py`, which drives the ASGI app directly.
"""

import json
import logging
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncEngine

from app.ai.admission import HISTORY_REFUSE_TOKENS
from app.ai.conversations import Pins, create_conversation, start_turn
from app.ai.fixed_texts import BUDGET_DAILY_TEXT, BUDGET_SANDBOX_TEXT
from app.ai.prompts.versions import TOOLSET_VERSION
from app.ai.scripted import WORKING_NOTE_TEXT, ScriptedTransport
from app.ai.turn import ConversationNotFound
from app.db.models import AiConversation, AiMessage, AiSpend, AiTurn, HandbookVersion
from app.db.tenancy import TenantContext, tenant_session
from app.modules.handbook.search import pinned_version_id
from app.modules.identity.actor import load_actor
from tests.integration.conftest import Browser, OpenBrowser, OpenBrowserWith
from tests.integration.test_assistant_routes import add_spend, new_conversation, sign_in

pytestmark = [
    pytest.mark.integration,
    pytest.mark.usefixtures("daily_ledger_untouched"),
]

BASE = "/api/v1/assistant"
SICK = "How much paid sick leave do I get?"
SSN = "My number is 078-05-1120, can you check it?"
CARD = "Use my card 4111 1111 1111 1111 for this"


def turns_url(conversation_id: str) -> str:
    return f"{BASE}/conversations/{conversation_id}/turns"


def ask(browser: Browser, conversation_id: str, question: str = SICK, **kwargs: Any) -> Any:
    return browser.client.post(
        turns_url(conversation_id), json={"question": question}, headers=browser.csrf, **kwargs
    )


def parse_sse(body: str) -> tuple[list[tuple[str, dict[str, Any]]], list[str]]:
    """The events as (name, data) and the comment lines, in the order they arrived."""
    events: list[tuple[str, dict[str, Any]]] = []
    comments: list[str] = []
    for block in body.split("\n\n"):
        if not block:
            continue
        lines = block.split("\n")
        if all(line.startswith(":") for line in lines):
            comments.extend(lines)
            continue
        assert lines[0].startswith("event: "), block
        assert lines[1].startswith("data: "), block
        assert len(lines) == 2, block
        events.append(
            (lines[0].removeprefix("event: "), json.loads(lines[1].removeprefix("data: ")))
        )
    return events, comments


async def turn_rows(engine: AsyncEngine, tenant_id: UUID, person_id: UUID) -> list[AiTurn]:
    async with tenant_session(engine, TenantContext(tenant_id, person_id)) as db:
        return list((await db.scalars(select(AiTurn).order_by(AiTurn.started_at))).all())


# --- The checks, before the stream opens ----------------------------------------------------


async def test_another_persons_conversation_and_an_unknown_one_are_404(
    browser: Browser, app_engine: AsyncEngine
) -> None:
    tenant_id, priya = sign_in(browser, "priya")
    conversation_id = new_conversation(browser)["id"]
    browser.client.put("/api/v1/session/persona", json={"persona": "dana"}, headers=browser.csrf)

    theirs = ask(browser, conversation_id)
    unknown = ask(browser, "00000000-0000-0000-0000-000000000000")

    assert (theirs.status_code, unknown.status_code) == (404, 404)
    assert theirs.headers["content-type"] == "application/problem+json"
    assert theirs.json()["detail"] == unknown.json()["detail"]
    assert await turn_rows(app_engine, tenant_id, priya) == []


@pytest.mark.parametrize("question", [SICK, ""])
async def test_a_conversation_pinned_to_an_old_prompt_is_409_conversation_outdated(
    browser: Browser, app_engine: AsyncEngine, question: str
) -> None:
    """Even for a question that would be a 422: the conversation is judged first."""
    tenant_id, person_id = sign_in(browser)
    async with tenant_session(app_engine, TenantContext(tenant_id, person_id)) as db:
        actor = await load_actor(db, tenant_id, person_id)
        assert actor is not None
        old = await create_conversation(
            db,
            actor,
            Pins("claude-opus-5-5", "claude-haiku-5-5", "low", "2020-01.0", TOOLSET_VERSION),
        )

    response = ask(browser, str(old.id), question)

    assert response.status_code == 409
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["type"] == "conversation-outdated"
    assert await turn_rows(app_engine, tenant_id, person_id) == []


async def test_a_history_past_80000_tokens_is_refused_as_history_too_long(
    browser: Browser, app_engine: AsyncEngine
) -> None:
    tenant_id, person_id = sign_in(browser)
    conversation_id = new_conversation(browser)["id"]
    async with tenant_session(app_engine, TenantContext(tenant_id, person_id)) as db:
        conversation = await db.get(AiConversation, UUID(conversation_id))
        assert conversation is not None
        earlier = await start_turn(db, conversation, "earlier")
        db.add(
            AiMessage(
                tenant_id=tenant_id,
                person_id=person_id,
                conversation_id=conversation.id,
                turn_id=earlier.id,
                position=0,
                role="user",
                content=[{"type": "text", "text": "y" * (HISTORY_REFUSE_TOKENS * 2 + 100)}],
            )
        )
        await db.flush()
        await db.execute(
            update(AiTurn)
            .where(AiTurn.id == earlier.id)
            .values(status="stopped", ended_at=text("now()"))
        )

    response = ask(browser, conversation_id)

    assert response.status_code == 409
    assert response.json()["type"] == "history-too-long"
    assert len(await turn_rows(app_engine, tenant_id, person_id)) == 1  # Only the earlier one.


@pytest.mark.parametrize(
    "question",
    ["", "   \n\t ", "x" * 2001, "a\u0000b", "lone \ud800 surrogate"],
)
async def test_a_question_that_is_not_1_to_2000_characters_is_422(
    browser: Browser, app_engine: AsyncEngine, question: str
) -> None:
    tenant_id, person_id = sign_in(browser)
    conversation_id = new_conversation(browser)["id"]

    response = browser.client.post(
        turns_url(conversation_id),
        content=json.dumps({"question": question}),
        headers={**browser.csrf, "Content-Type": "application/json"},
    )

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    assert await turn_rows(app_engine, tenant_id, person_id) == []


async def test_a_question_is_measured_after_trimming(browser: Browser) -> None:
    sign_in(browser)
    conversation_id = new_conversation(browser)["id"]
    padded = "  " + "x" * 2000 + "  "

    response = ask(browser, conversation_id, padded)

    assert response.status_code == 200


@pytest.mark.parametrize("question", [SSN, CARD, "My SSN is 078\u00a005\u00a01120"])
async def test_personal_data_is_refused_as_a_problem_and_never_stored_or_logged(
    browser: Browser,
    app_engine: AsyncEngine,
    caplog: pytest.LogCaptureFixture,
    question: str,
) -> None:
    tenant_id, person_id = sign_in(browser)
    conversation_id = new_conversation(browser)["id"]
    caplog.set_level(logging.DEBUG)

    response = ask(browser, conversation_id, question)

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["type"] == "personal-data"
    for number in ("078-05-1120", "4111 1111 1111 1111"):
        assert number not in response.text
    assert await turn_rows(app_engine, tenant_id, person_id) == []
    logged = " ".join(f"{r.getMessage()} {r.__dict__}" for r in caplog.records)
    assert "078-05-1120" not in logged
    assert "4111" not in logged
    # Nothing of it was stored in any table the person can read.
    async with tenant_session(app_engine, TenantContext(tenant_id, person_id)) as db:
        stored = await db.scalar(select(func.count()).select_from(AiMessage))
    assert stored == 0


async def test_a_turn_already_running_is_409_turn_running(
    browser: Browser, app_engine: AsyncEngine
) -> None:
    tenant_id, person_id = sign_in(browser)
    conversation_id = new_conversation(browser)["id"]
    async with tenant_session(app_engine, TenantContext(tenant_id, person_id)) as db:
        conversation = await db.get(AiConversation, UUID(conversation_id))
        assert conversation is not None
        await start_turn(db, conversation, "still going")

    response = ask(browser, conversation_id)

    assert response.status_code == 409
    assert response.json()["type"] == "turn-running"
    assert len(await turn_rows(app_engine, tenant_id, person_id)) == 1


async def test_a_running_turn_older_than_ten_minutes_is_abandoned_and_does_not_block(
    browser: Browser, app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    tenant_id, person_id = sign_in(browser)
    conversation_id = new_conversation(browser)["id"]
    async with tenant_session(app_engine, TenantContext(tenant_id, person_id)) as db:
        conversation = await db.get(AiConversation, UUID(conversation_id))
        assert conversation is not None
        old = await start_turn(db, conversation, "died")
    async with owner_engine.begin() as connection:
        await connection.execute(
            text("UPDATE ai_turns SET started_at = now() - interval '11 minutes' WHERE id = :id"),
            {"id": old.id},
        )

    response = ask(browser, conversation_id)

    assert response.status_code == 200
    rows = await turn_rows(app_engine, tenant_id, person_id)
    assert [(r.status, r.error_code) for r in rows] == [
        ("failed", "abandoned"),
        ("completed", None),
    ]


async def test_a_sandbox_without_room_is_429_budget_sandbox_and_starts_no_turn(
    browser: Browser, app_engine: AsyncEngine
) -> None:
    tenant_id, person_id = sign_in(browser)
    conversation_id = new_conversation(browser)["id"]
    async with tenant_session(app_engine, TenantContext(tenant_id, person_id)) as db:
        conversation = await db.get(AiConversation, UUID(conversation_id))
        assert conversation is not None
        earlier = await start_turn(db, conversation, "earlier")
        await db.execute(
            update(AiTurn)
            .where(AiTurn.id == earlier.id)
            .values(status="stopped", ended_at=text("now()"))
        )
    # $0.10 left: not zero, but under what the guard and a model call could cost.
    await add_spend(app_engine, tenant_id, person_id, earlier.id, "0.90")

    response = ask(browser, conversation_id)

    assert response.status_code == 429
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["type"] == "budget-sandbox"
    assert response.json()["detail"] == BUDGET_SANDBOX_TEXT
    # Checked before the turn's row is added: nothing was left `running`.
    rows = await turn_rows(app_engine, tenant_id, person_id)
    assert [r.status for r in rows] == ["stopped"]
    async with tenant_session(app_engine, TenantContext(tenant_id, person_id)) as db:
        spent = await db.scalars(select(AiSpend.amount_usd))
        assert sum(spent, Decimal(0)) == Decimal("0.90")


async def test_a_day_without_room_is_429_budget_daily(open_browser_with: OpenBrowserWith) -> None:
    browser = open_browser_with(ai_daily_budget_usd=Decimal("0.05"))
    sign_in(browser)
    conversation_id = new_conversation(browser)["id"]

    response = ask(browser, conversation_id)

    assert response.status_code == 429
    assert response.json()["type"] == "budget-daily"
    assert response.json()["detail"] == BUDGET_DAILY_TEXT


async def test_the_checks_run_in_the_specs_order(browser: Browser, app_engine: AsyncEngine) -> None:
    tenant_id, person_id = sign_in(browser)
    conversation_id = new_conversation(browser)["id"]
    async with tenant_session(app_engine, TenantContext(tenant_id, person_id)) as db:
        conversation = await db.get(AiConversation, UUID(conversation_id))
        assert conversation is not None
        running = await start_turn(db, conversation, "running")
    await add_spend(app_engine, tenant_id, person_id, running.id, "0.95")

    # A turn is running AND the budget is short AND the text is a number: the question is judged
    # first, then the running turn, then the budget.
    personal = ask(browser, conversation_id, SSN)
    busy = ask(browser, conversation_id)
    empty = ask(browser, conversation_id, "  ")

    assert (personal.status_code, personal.json()["type"]) == (422, "personal-data")
    assert (busy.status_code, busy.json()["type"]) == (409, "turn-running")
    assert empty.status_code == 422


def test_the_stream_needs_the_csrf_token_and_the_same_origin_check(browser: Browser) -> None:
    sign_in(browser)
    conversation_id = new_conversation(browser)["id"]

    no_csrf = browser.client.post(turns_url(conversation_id), json={"question": SICK})
    cross_site = browser.client.post(
        turns_url(conversation_id),
        json={"question": SICK},
        headers={**browser.csrf, "Sec-Fetch-Site": "cross-site"},
    )

    assert (no_csrf.status_code, cross_site.status_code) == (403, 403)
    assert no_csrf.headers["content-type"] == "application/problem+json"


# --- The stream -----------------------------------------------------------------------------


def names(events: list[tuple[str, dict[str, Any]]]) -> list[str]:
    """The event names with consecutive repeats collapsed."""
    collapsed: list[str] = []
    for name, _ in events:
        if not collapsed or collapsed[-1] != name:
            collapsed.append(name)
    return collapsed


async def test_a_plain_question_streams_the_events_in_order_and_is_saved(
    browser: Browser, app_engine: AsyncEngine
) -> None:
    tenant_id, person_id = sign_in(browser)
    conversation_id = new_conversation(browser)["id"]

    with browser.client.stream(
        "POST", turns_url(conversation_id), json={"question": SICK}, headers=browser.csrf
    ) as response:
        body = "".join(response.iter_text())
        headers = response.headers
        status_code = response.status_code

    assert status_code == 200
    events, comments = parse_sse(body)
    assert comments == []  # Nothing was quiet for 15 seconds.
    assert names(events) == [
        "turn.started",
        "status",
        "tool.started",
        "tool.finished",
        "text.delta",
        "citation",
        "text.delta",
        "citation",
        "turn.completed",
    ]
    assert headers["content-type"] == "text/event-stream; charset=utf-8"
    assert headers["cache-control"] == "no-store, no-transform"
    assert headers["x-accel-buffering"] == "no"
    assert headers["content-encoding"] == "identity"
    assert headers["x-request-id"]
    [turn] = await turn_rows(app_engine, tenant_id, person_id)
    assert events[0] == ("turn.started", {"turnId": str(turn.id)})
    completed = events[-1][1]
    assert set(completed) == {"turnId", "servedBy", "usage"}
    assert set(completed["usage"]) == {"inputTokens", "outputTokens"}
    assert turn.status == "completed"
    assert turn.answer_text == "".join(d["text"] for n, d in events if n == "text.delta")
    # The page, after a reload, shows what the stream showed.
    [shown] = browser.client.get(f"{BASE}/conversations/current").json()["turns"]
    assert shown["answerText"] == turn.answer_text


async def test_an_event_carries_its_name_on_one_line_and_its_data_on_the_next(
    browser: Browser,
) -> None:
    sign_in(browser)
    conversation_id = new_conversation(browser)["id"]

    lines = ask(browser, conversation_id).text.split("\n")

    assert lines[0] == "event: turn.started"
    assert lines[1].startswith('data: {"turnId":"')
    assert lines[2] == ""


async def test_a_working_note_is_taken_back_with_a_retraction_before_its_status_line(
    browser: Browser, app_engine: AsyncEngine
) -> None:
    tenant_id, person_id = sign_in(browser)
    conversation_id = new_conversation(browser)["id"]

    events, _ = parse_sse(ask(browser, conversation_id, "scripted working note").text)

    sequence = [name for name, _ in events]
    first_text = sequence.index("text.delta")
    retracted = sequence.index("text.retracted")
    assert first_text < retracted
    # The note shows as a status line right after it is taken back, and the answer follows.
    assert events[retracted][1] == {}
    assert events[retracted + 1][0] == "status"
    assert events[retracted + 1][1]["text"] == WORKING_NOTE_TEXT
    assert sequence.index("citation") > retracted
    answer = "".join(d["text"] for n, d in events[retracted + 1 :] if n == "text.delta")
    [turn] = await turn_rows(app_engine, tenant_id, person_id)
    assert turn.answer_text == answer
    assert WORKING_NOTE_TEXT not in turn.answer_text


def quiet_app(open_browser_with: OpenBrowserWith, heartbeat_seconds: int) -> Browser:
    browser = open_browser_with(ai_heartbeat_seconds=heartbeat_seconds)
    # The scripted silence scenario is 45 seconds; shorten it. The routes read the transport from
    # the app's state, so replacing it there is what a deployment's own setting would do.
    browser.client.app.state.transport = ScriptedTransport(silence_seconds=2.6)  # type: ignore[attr-defined]
    return browser


async def test_a_quiet_turn_gets_keep_alive_comments(open_browser_with: OpenBrowserWith) -> None:
    browser = quiet_app(open_browser_with, heartbeat_seconds=1)
    sign_in(browser)
    conversation_id = new_conversation(browser)["id"]

    body = ask(browser, conversation_id, "scripted silence").text

    events, comments = parse_sse(body)
    assert comments.count(": keep-alive") >= 2
    assert names(events)[-1] == "turn.completed"
    # The comments came while the model was silent: after the turn started, before it finished.
    assert body.index(": keep-alive") > body.index("event: turn.started")
    assert body.rindex(": keep-alive") < body.index("event: turn.completed")


async def test_with_the_heartbeat_off_no_comment_is_sent(
    open_browser_with: OpenBrowserWith,
) -> None:
    browser = quiet_app(open_browser_with, heartbeat_seconds=0)
    sign_in(browser)
    conversation_id = new_conversation(browser)["id"]

    body = ask(browser, conversation_id, "scripted silence").text

    events, comments = parse_sse(body)
    assert comments == []
    assert names(events)[-1] == "turn.completed"


async def test_the_budget_threshold_agrees_with_what_a_real_turn_reserves(
    browser: Browser, app_engine: AsyncEngine
) -> None:
    """The room check is an upper bound on the guard's and first call's reservations."""
    from datetime import UTC, datetime

    from app.ai.admission import room_needed_usd
    from app.ai.context import actor_view
    from app.modules.people.queries import get_me

    tenant_id, person_id = sign_in(browser)
    conversation_id = new_conversation(browser)["id"]
    async with tenant_session(app_engine, TenantContext(tenant_id, person_id)) as db:
        actor = await load_actor(db, tenant_id, person_id)
        assert actor is not None
        me = await get_me(db, actor, datetime.now(UTC))
        label = (
            await db.scalars(
                select(HandbookVersion.label).where(
                    HandbookVersion.id == await pinned_version_id(db)
                )
            )
        ).one()
    needed = room_needed_usd(
        model="claude-opus-5-5",
        guard_model="claude-haiku-5-5",
        effort="low",
        history=[],
        question=SICK,
        actor_view=actor_view(me),
        handbook_label=label,
        now=datetime.now(UTC),
    )

    assert ask(browser, conversation_id).status_code == 200

    async with tenant_session(app_engine, TenantContext(tenant_id, person_id)) as db:
        reserves = list(
            await db.scalars(
                select(AiSpend.amount_usd)
                .where(AiSpend.kind == "reserve")
                .order_by(AiSpend.created_at)
            )
        )
    guard, first_call = reserves[0], reserves[1]
    # An upper bound, and a tight one: it differs only by the longer notes and previous answer.
    assert needed >= guard + first_call
    assert needed - (guard + first_call) < Decimal("0.01")


@pytest.mark.parametrize("error", [KeyError("bug"), IndexError("bug")])
async def test_a_lookup_bug_in_the_start_is_a_500_not_a_misleading_404(
    open_browser: OpenBrowser, monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    browser = open_browser(raise_server_exceptions=False)
    sign_in(browser)
    conversation_id = new_conversation(browser)["id"]

    async def broken(*args: Any, **kwargs: Any) -> None:
        raise error

    monkeypatch.setattr("app.ai.turn.TurnRun.begin", broken)

    response = ask(browser, conversation_id)

    assert response.status_code == 500
    assert response.headers["content-type"] == "application/problem+json"


async def test_a_conversation_lost_between_the_checks_and_the_start_is_a_404(
    browser: Browser, monkeypatch: pytest.MonkeyPatch
) -> None:
    sign_in(browser)
    conversation_id = new_conversation(browser)["id"]

    async def lost(*args: Any, **kwargs: Any) -> None:
        raise ConversationNotFound

    monkeypatch.setattr("app.modules.assistant.routes.start_turn_run", lost)

    response = ask(browser, conversation_id)

    assert response.status_code == 404
    assert browser.client.app.state.streams.open_count == 0  # type: ignore[attr-defined]


async def test_the_assistants_query_embeddings_are_not_shared_between_sandboxes(
    browser: Browser,
) -> None:
    from app.ai.embeddings import QueryEmbeddingLru
    from tests.test_embeddings import CountingEmbedder

    inner = CountingEmbedder()
    browser.client.app.state.embedder = QueryEmbeddingLru(inner)  # type: ignore[attr-defined]

    sign_in(browser)  # Sandbox one.
    assert ask(browser, new_conversation(browser)["id"]).status_code == 200
    sign_in(browser)  # Sandbox two asks the same question.
    second = new_conversation(browser)["id"]
    assert ask(browser, second).status_code == 200
    reached_voyage = len(inner.calls)
    assert ask(browser, second).status_code == 200  # The same sandbox again.

    assert reached_voyage == 2
    assert len(inner.calls) == 2


async def test_a_question_in_a_sandbox_without_a_handbook_version_is_a_404(
    browser: Browser, owner_engine: AsyncEngine
) -> None:
    tenant_id, _ = sign_in(browser)
    conversation_id = new_conversation(browser)["id"]
    async with owner_engine.begin() as connection:
        await connection.execute(
            text("UPDATE tenants SET handbook_version_id = NULL WHERE id = :id"), {"id": tenant_id}
        )

    response = ask(browser, conversation_id)

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
