"""A conversation whose stored text does not open is shown as unreadable, never as a 500.

Phase 8, stage 3. The damage is done as the database owner, in a test sandbox: one turn's
ciphertext, or the conversation's wrapped key. The read returns the conversation with
`unreadable`, no turns, and `historyTooLong` (so the page offers a new one); the budget route
answers; a question is a 409 `conversation-unreadable` that writes nothing; a new conversation
works. The log names the conversation (and the turn), never any text.
"""

import logging
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.models import AiConversation, AiTurn
from app.db.tenancy import TenantContext, tenant_session
from tests.integration.conftest import Browser, begin_turn, message_row
from tests.integration.test_assistant_routes import (
    BASE,
    completed,
    new_conversation,
    seed_turn,
    sign_in,
)
from tests.integration.test_turn_stream import ask

pytestmark = [
    pytest.mark.integration,
    pytest.mark.usefixtures("daily_ledger_untouched"),
]

QUESTION = "ZEBRA-Q-9921 how much sick leave do I get?"
LINE = "This conversation can't be shown. Start a new conversation to keep asking."


async def damage(owner: AsyncEngine, table: str, column: str, key: str, row_id: UUID) -> int:
    """Change the first byte of one stored value, as the owner with the triggers off (the tables
    refuse such edits). A sealed value with a changed byte no longer opens."""
    statement = (
        f"UPDATE {table} SET {column} = set_byte({column}, 0, get_byte({column}, 0) # 255)"  # noqa: S608
        f" WHERE {key} = :id"
    )
    async with owner.begin() as connection:
        await connection.execute(text("SET LOCAL session_replication_role = replica"))
        changed = (await connection.execute(text(statement), {"id": row_id})).rowcount
    assert changed >= 1, "the damage changed no row"
    return changed


async def damaged_turn(
    browser: Browser, app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> tuple[UUID, UUID, UUID, UUID]:
    """A finished turn whose question no longer opens: (tenant, person, conversation, turn)."""
    tenant_id, person_id = sign_in(browser)
    conversation_id = UUID(new_conversation(browser)["id"])
    turn_id = await seed_turn(
        app_engine, tenant_id, person_id, conversation_id, question=QUESTION, outcome=completed()
    )
    await damage(owner_engine, "ai_turns", "question_ciphertext", "id", turn_id)
    return tenant_id, person_id, conversation_id, turn_id


async def damaged_key(
    browser: Browser, app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> tuple[UUID, UUID, UUID, None]:
    """A conversation whose wrapped key no longer opens."""
    tenant_id, person_id = sign_in(browser)
    conversation_id = UUID(new_conversation(browser)["id"])
    await seed_turn(
        app_engine, tenant_id, person_id, conversation_id, question=QUESTION, outcome=completed()
    )
    await damage(owner_engine, "ai_conversations", "wrapped_key", "id", conversation_id)
    return tenant_id, person_id, conversation_id, None


async def count_turns(engine: AsyncEngine, tenant_id: UUID, person_id: UUID) -> int:
    async with tenant_session(engine, TenantContext(tenant_id, person_id)) as db:
        return (await db.execute(select(func.count(AiTurn.id)))).scalar_one()


@pytest.fixture(params=[damaged_turn, damaged_key], ids=["a turn", "the wrapped key"])
def damage_kind(request: pytest.FixtureRequest) -> Any:
    return request.param


async def test_the_current_conversation_is_unreadable_not_a_500(
    browser: Browser,
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    damage_kind: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _, _, conversation_id, turn_id = await damage_kind(browser, app_engine, owner_engine)

    with caplog.at_level(logging.WARNING):
        response = browser.client.get(f"{BASE}/conversations/current")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == str(conversation_id)
    assert body["unreadable"] is True
    assert body["turns"] == []
    assert body["historyTooLong"] is True
    assert body["longHistory"] is True
    assert body["outdated"] is False
    assert body["hrContacts"] == []
    assert body["budget"]["banner"] is None
    # One line, with the IDs and no text.
    lines = [r.getMessage() for r in caplog.records if "could not be opened" in r.getMessage()]
    assert len(lines) == 1
    assert str(conversation_id) in lines[0]
    if turn_id is not None:
        assert str(turn_id) in lines[0]
    assert "ZEBRA" not in caplog.text
    assert "sick leave" not in caplog.text


async def test_the_budget_route_still_answers(
    browser: Browser, app_engine: AsyncEngine, owner_engine: AsyncEngine, damage_kind: Any
) -> None:
    await damage_kind(browser, app_engine, owner_engine)

    response = browser.client.get(f"{BASE}/budget")

    assert response.status_code == 200, response.text
    assert response.json()["banner"] is None


async def test_a_question_to_an_unreadable_conversation_is_a_409_and_writes_nothing(
    browser: Browser, app_engine: AsyncEngine, owner_engine: AsyncEngine, damage_kind: Any
) -> None:
    tenant_id, person_id, conversation_id, _ = await damage_kind(browser, app_engine, owner_engine)
    before = await count_turns(app_engine, tenant_id, person_id)

    response = ask(browser, str(conversation_id))

    assert response.status_code == 409, response.text
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["type"] == "conversation-unreadable"
    assert body["detail"] == LINE
    assert await count_turns(app_engine, tenant_id, person_id) == before


async def test_a_new_conversation_starts_and_is_readable(
    browser: Browser, app_engine: AsyncEngine, owner_engine: AsyncEngine, damage_kind: Any
) -> None:
    _, _, old_id, _ = await damage_kind(browser, app_engine, owner_engine)

    created = browser.client.post(f"{BASE}/conversations", headers=browser.csrf)

    assert created.status_code == 201, created.text
    assert created.json()["id"] != str(old_id)
    assert created.json()["unreadable"] is False
    current = browser.client.get(f"{BASE}/conversations/current")
    assert current.status_code == 200
    assert current.json()["id"] == created.json()["id"]
    assert current.json()["unreadable"] is False


async def test_a_feedback_reason_that_does_not_open_is_left_out_and_the_rest_shows(
    browser: Browser,
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    caplog: pytest.LogCaptureFixture,
) -> None:
    tenant_id, person_id = sign_in(browser)
    conversation_id = UUID(new_conversation(browser)["id"])
    turn_id = await seed_turn(
        app_engine, tenant_id, person_id, conversation_id, outcome=completed()
    )
    given = browser.client.post(
        f"{BASE}/turns/{turn_id}/feedback",
        json={"helpful": False, "reason": "ZEBRA-R-1 too vague"},
        headers=browser.csrf,
    )
    assert given.status_code == 201, given.text
    await damage(owner_engine, "ai_feedback", "reason_ciphertext", "turn_id", turn_id)

    with caplog.at_level(logging.WARNING):
        response = browser.client.get(f"{BASE}/conversations/current")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["unreadable"] is False
    [turn] = body["turns"]
    assert turn["feedback"] == {"helpful": False, "reason": None}
    assert "ZEBRA" not in response.text + caplog.text
    assert "A feedback reason could not be opened" in caplog.text


async def test_a_readable_conversation_is_not_marked_unreadable(
    browser: Browser, app_engine: AsyncEngine
) -> None:
    tenant_id, person_id = sign_in(browser)
    conversation_id = UUID(new_conversation(browser)["id"])
    await seed_turn(app_engine, tenant_id, person_id, conversation_id, outcome=completed())

    body = browser.client.get(f"{BASE}/conversations/current").json()

    assert body["unreadable"] is False
    assert len(body["turns"]) == 1


async def test_a_question_is_taken_when_only_a_feedback_reason_does_not_open(
    browser: Browser, app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    tenant_id, person_id = sign_in(browser)
    conversation_id = UUID(new_conversation(browser)["id"])
    turn_id = await seed_turn(
        app_engine, tenant_id, person_id, conversation_id, outcome=completed()
    )
    given = browser.client.post(
        f"{BASE}/turns/{turn_id}/feedback",
        json={"helpful": False, "reason": "too vague"},
        headers=browser.csrf,
    )
    assert given.status_code == 201, given.text
    await damage(owner_engine, "ai_feedback", "reason_ciphertext", "turn_id", turn_id)
    before = await count_turns(app_engine, tenant_id, person_id)

    response = ask(browser, str(conversation_id))

    assert response.status_code == 200, response.text
    assert await count_turns(app_engine, tenant_id, person_id) == before + 1


async def test_a_question_is_a_409_when_only_the_stored_history_does_not_open(
    browser: Browser, app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    tenant_id, person_id = sign_in(browser)
    conversation_id = UUID(new_conversation(browser)["id"])
    async with tenant_session(app_engine, TenantContext(tenant_id, person_id)) as db:
        conversation = await db.get(AiConversation, conversation_id)
        assert conversation is not None
        earlier = await begin_turn(db, conversation, "earlier")
        db.add(
            message_row(
                conversation,
                earlier.id,
                position=0,
                role="user",
                content=[{"type": "text", "text": "message 0"}],
            )
        )
        await db.flush()
        await db.execute(
            update(AiTurn)
            .where(AiTurn.id == earlier.id)
            .values(status="stopped", ended_at=text("now()"))
        )
    await damage(
        owner_engine, "ai_messages", "content_ciphertext", "conversation_id", conversation_id
    )
    before = await count_turns(app_engine, tenant_id, person_id)

    response = ask(browser, str(conversation_id))

    assert response.status_code == 409, response.text
    assert response.json()["type"] == "conversation-unreadable"
    assert await count_turns(app_engine, tenant_id, person_id) == before
