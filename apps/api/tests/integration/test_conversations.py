"""The conversation store: what the model is sent, in order and unchanged, and one turn at a time.

A person's conversations are visible to that person alone (row-level security, migration 0008), so
every session here is scoped to the person whose conversation it touches.
"""

import asyncio
import dataclasses
import json
from collections.abc import Sequence
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.ai.conversations import (
    Pins,
    SourceEntry,
    StoredMessage,
    TurnFinished,
    TurnOutcome,
    TurnRunning,
    append_messages,
    create_conversation,
    current_conversation,
    finish_turn,
    model_history,
    recover_abandoned,
    search_sources,
    start_turn,
)
from app.ai.transport import count_search_results
from app.db.tenancy import TenantContext, tenant_session
from app.policy import Actor
from tests.integration.conftest import MakeTenant, SampleTenant

pytestmark = pytest.mark.integration

PINS = Pins(
    model="claude-opus-5-5",
    guard_model="claude-haiku-5-5",
    effort="medium",
    prompt_version="test-1",
    toolset_version="test-1",
)


def actor_of(tenant: SampleTenant, person_id: UUID) -> Actor:
    return Actor(
        person_id=person_id,
        tenant_id=tenant.id,
        is_hr_admin=False,
        report_ids=frozenset(),
        direct_report_ids=frozenset(),
    )


def context_of(tenant: SampleTenant, person_id: UUID | None = None) -> TenantContext:
    return TenantContext(tenant.id, person_id or tenant.employee_id)


def source(section_id: str, *passages: str) -> SourceEntry:
    return SourceEntry(
        section_id=section_id,
        passage_ids=passages,
        title="Sick leave",
        group_name="California addendum",
        audience_label="California",
        last_updated=date(2026, 9, 12),
        deep_link=f"/handbook/{section_id}?passage={passages[0]}",
    )


def search_result_message(entries: tuple[SourceEntry, ...]) -> StoredMessage:
    blocks: list[dict[str, Any]] = [
        {
            "type": "search_result",
            "source": entry.deep_link,
            "title": entry.title,
            "content": [{"type": "text", "text": f"passage {p}"} for p in entry.passage_ids],
            "citations": {"enabled": True},
        }
        for entry in entries
    ]
    return StoredMessage("user", blocks, entries)


async def new_conversation(app_engine: AsyncEngine, tenant: SampleTenant) -> UUID:
    actor = actor_of(tenant, tenant.employee_id)
    async with tenant_session(app_engine, context_of(tenant)) as db:
        return (await create_conversation(db, actor, PINS)).id


async def new_turn(
    app_engine: AsyncEngine, tenant: SampleTenant, conversation_id: UUID, question: str = "Hi"
) -> UUID:
    """A running turn, committed."""
    actor = actor_of(tenant, tenant.employee_id)
    async with tenant_session(app_engine, context_of(tenant)) as db:
        conversation = await current_conversation(db, actor)
        assert conversation is not None
        assert conversation.id == conversation_id
        return (await start_turn(db, conversation, question)).id


# A thinking block is signed over its exact bytes. These have keys out of alphabetical order, text
# that JSON escapes, and nesting, which is what a normalizing store would change.
TRICKY_ASSISTANT_CONTENT: list[dict[str, Any]] = [
    {
        "type": "thinking",
        "thinking": 'Sick leave, then a "quote" and a \\ slash\n',
        "signature": "EuYBCkQYAiJA+/==",
    },
    {
        "type": "text",
        "text": "Café ☕ … 40 hours 🙂",
        "citations": [
            {
                "type": "search_result_location",
                "source": "/handbook/CA-4.3?passage=p2",
                "title": "CA-4.3 Sick leave · California addendum",
                "cited_text": "Employees accrue one hour for every 30 hours worked.",
                "search_result_index": 0,
                "start_block_index": 1,
                "end_block_index": 2,
            }
        ],
    },
    {
        "type": "tool_use",
        "id": "toolu_01A",
        "name": "search_handbook",
        "input": {
            "query": "sick leave",
            "z_last": 1,
            "a_first": [3, 2, 1],
            "nested": {"b": 1, "a": 2},
        },
    },
]
# The answer to the tool call above: a tool call is stored together with its result.
TRICKY_TOOL_RESULT_CONTENT: list[dict[str, Any]] = [
    {
        "type": "tool_result",
        "tool_use_id": "toolu_01A",
        "content": [{"type": "text", "text": "No handbook passages matched. ¿Otra pregunta?"}],
    }
]
TRICKY_USER_CONTENT: list[dict[str, Any]] = [
    {"type": "text", "text": "How much sick leave do I get, señor?"}
]


async def test_history_comes_back_exactly_as_it_was_stored(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    conversation_id = await new_conversation(app_engine, tenant)
    turn_id = await new_turn(app_engine, tenant, conversation_id)
    async with tenant_session(app_engine, context_of(tenant)) as db:
        await append_messages(
            db,
            conversation_id,
            turn_id,
            [
                StoredMessage("user", TRICKY_USER_CONTENT),
                StoredMessage("assistant", TRICKY_ASSISTANT_CONTENT),
                StoredMessage("user", TRICKY_TOOL_RESULT_CONTENT),
            ],
        )

    async with tenant_session(app_engine, context_of(tenant)) as db:
        history = await model_history(db, conversation_id)
        stored: Sequence[str] = (
            (
                await db.execute(
                    text(
                        "SELECT content::text FROM ai_messages WHERE conversation_id = :c"
                        " ORDER BY position"
                    ),
                    {"c": conversation_id},
                )
            )
            .scalars()
            .all()
        )

    # What SQLAlchemy serialized is what Postgres kept, byte for byte.
    assert list(stored) == [
        json.dumps(TRICKY_USER_CONTENT),
        json.dumps(TRICKY_ASSISTANT_CONTENT),
        json.dumps(TRICKY_TOOL_RESULT_CONTENT),
    ]
    # And what comes back is equal, with every key in its original place.
    assert [m["role"] for m in history] == ["user", "assistant", "user"]
    assert history[0]["content"] == TRICKY_USER_CONTENT
    assert history[1]["content"] == TRICKY_ASSISTANT_CONTENT
    assert json.dumps(history[0]["content"]) == json.dumps(TRICKY_USER_CONTENT)
    assert json.dumps(history[1]["content"]) == json.dumps(TRICKY_ASSISTANT_CONTENT)
    assert json.dumps(history[2]["content"]) == json.dumps(TRICKY_TOOL_RESULT_CONTENT)


async def test_positions_are_consecutive_across_appends(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    conversation_id = await new_conversation(app_engine, tenant)
    turn_id = await new_turn(app_engine, tenant, conversation_id)
    async with tenant_session(app_engine, context_of(tenant)) as db:
        await append_messages(
            db,
            conversation_id,
            turn_id,
            [
                StoredMessage("user", [{"type": "text", "text": "one"}]),
                StoredMessage("assistant", [{"type": "text", "text": "two"}]),
            ],
        )
    async with tenant_session(app_engine, context_of(tenant)) as db:
        await append_messages(
            db,
            conversation_id,
            turn_id,
            [StoredMessage("user", [{"type": "text", "text": "three"}])],
        )

    async with tenant_session(app_engine, context_of(tenant)) as db:
        positions = (
            await db.execute(
                text(
                    "SELECT position, content->0->>'text' FROM ai_messages"
                    " WHERE conversation_id = :c ORDER BY position"
                ),
                {"c": conversation_id},
            )
        ).all()
        history = await model_history(db, conversation_id)

    assert [tuple(row) for row in positions] == [(0, "one"), (1, "two"), (2, "three")]
    assert [m["content"][0]["text"] for m in history] == ["one", "two", "three"]


async def test_a_second_running_turn_is_refused_and_the_transaction_survives(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    conversation_id = await new_conversation(app_engine, tenant)
    await new_turn(app_engine, tenant, conversation_id)
    actor = actor_of(tenant, tenant.employee_id)

    async with tenant_session(app_engine, context_of(tenant)) as db:
        conversation = await current_conversation(db, actor)
        assert conversation is not None
        with pytest.raises(TurnRunning):
            await start_turn(db, conversation, "Another question")
        # The caller's transaction is still usable: the failed insert rolled back to a savepoint.
        assert (await db.execute(text("SELECT 1"))).scalar_one() == 1
        still_there = await current_conversation(db, actor)
        assert still_there is not None


async def test_a_new_turn_starts_once_the_running_one_has_finished(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    conversation_id = await new_conversation(app_engine, tenant)
    turn_id = await new_turn(app_engine, tenant, conversation_id)
    async with tenant_session(app_engine, context_of(tenant)) as db:
        await finish_turn(db, turn_id, TurnOutcome(status="completed", answer_text="Done."))

    await new_turn(app_engine, tenant, conversation_id, "And another?")


async def test_an_abandoned_turn_is_marked_failed_and_the_next_one_starts(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    conversation_id = await new_conversation(app_engine, tenant)
    old_turn = await new_turn(app_engine, tenant, conversation_id)
    # The API can't change started_at (no grant), so the test ages the turn as the owner.
    async with owner_engine.begin() as connection:
        await connection.execute(
            text("UPDATE ai_turns SET started_at = now() - interval '11 minutes' WHERE id = :id"),
            {"id": old_turn},
        )

    async with tenant_session(app_engine, context_of(tenant)) as db:
        recovered = await recover_abandoned(db, conversation_id)

    assert recovered == 1
    await new_turn(app_engine, tenant, conversation_id, "Are you there?")
    async with owner_engine.connect() as connection:
        row = (
            await connection.execute(
                text(
                    "SELECT status, error_code, ended_at IS NOT NULL FROM ai_turns WHERE id = :id"
                ),
                {"id": old_turn},
            )
        ).one()
    assert tuple(row) == ("failed", "abandoned", True)


async def test_a_recent_running_turn_is_left_alone(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    conversation_id = await new_conversation(app_engine, tenant)
    await new_turn(app_engine, tenant, conversation_id)

    async with tenant_session(app_engine, context_of(tenant)) as db:
        assert await recover_abandoned(db, conversation_id) == 0

    with pytest.raises(TurnRunning):
        await new_turn(app_engine, tenant, conversation_id)


async def test_a_finished_turn_cannot_be_finished_again(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    conversation_id = await new_conversation(app_engine, tenant)
    turn_id = await new_turn(app_engine, tenant, conversation_id)
    outcome = TurnOutcome(
        status="completed",
        answer_text="You get 40 hours.",
        citations=[{"marker": 1, "sectionId": "CA-4.3"}],
        tool_calls=[
            {"name": "search_handbook", "inputSummary": "sick leave", "ok": True, "durationMs": 40}
        ],
        served_by_models=["claude-opus-5-5"],
        input_tokens=1200,
        output_tokens=80,
        cache_read_tokens=900,
        cache_write_tokens=300,
        cost_usd=Decimal("0.0504"),
        total_ms=2100,
    )
    async with tenant_session(app_engine, context_of(tenant)) as db:
        await finish_turn(db, turn_id, outcome)

    async with tenant_session(app_engine, context_of(tenant)) as db:
        with pytest.raises(TurnFinished):
            await finish_turn(db, turn_id, TurnOutcome(status="failed", error_code="again"))
        # The transaction survived the refusal.
        assert (await db.execute(text("SELECT 1"))).scalar_one() == 1

    async with owner_engine.connect() as connection:
        row = (
            await connection.execute(
                text(
                    "SELECT status, answer_text, citations, served_by_models, cost_usd,"
                    " cache_write_tokens, total_ms, ended_at IS NOT NULL"
                    " FROM ai_turns WHERE id = :id"
                ),
                {"id": turn_id},
            )
        ).one()
    assert tuple(row) == (
        "completed",
        "You get 40 hours.",
        [{"marker": 1, "sectionId": "CA-4.3"}],
        ["claude-opus-5-5"],
        Decimal("0.0504"),
        300,
        2100,
        True,
    )


async def test_a_turn_finished_without_a_verdict_has_a_sql_null_guard_verdict(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    conversation_id = await new_conversation(app_engine, tenant)
    turn_id = await new_turn(app_engine, tenant, conversation_id)
    async with tenant_session(app_engine, context_of(tenant)) as db:
        await finish_turn(db, turn_id, TurnOutcome(status="failed", error_code="budget-daily"))

    async with tenant_session(app_engine, context_of(tenant)) as db:
        is_null: bool = (
            await db.execute(
                text("SELECT guard_verdict IS NULL FROM ai_turns WHERE id = :id"), {"id": turn_id}
            )
        ).scalar_one()

    assert is_null is True


def tool_result(tool_use_id: str, content: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": "tool_result", "tool_use_id": tool_use_id, "content": content}


def search_result_block(entry: SourceEntry) -> dict[str, Any]:
    return search_result_message((entry,)).content[0]


def test_search_results_are_counted_inside_tool_results() -> None:
    content = [
        tool_result(
            "toolu_1",
            [
                search_result_block(source("CA-4.3", "p2")),
                search_result_block(source("US-1.1", "p1")),
                search_result_block(source("CO-2.1", "p4")),
            ],
        ),
        tool_result("toolu_2", [{"type": "text", "text": "No handbook passages matched."}]),
    ]

    assert count_search_results(content) == 3
    assert count_search_results([search_result_block(source("CA-4.3", "p2"))]) == 1
    assert count_search_results([{"type": "text", "text": "hello"}]) == 0
    # A tool result's content can also be a plain string.
    assert count_search_results([{"type": "tool_result", "tool_use_id": "t", "content": "ok"}]) == 0


async def test_sources_are_stored_for_search_results_inside_tool_results(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    conversation_id = await new_conversation(app_engine, tenant)
    turn_id = await new_turn(app_engine, tenant, conversation_id)
    entries = (source("CA-4.3", "p2", "p3"), source("US-1.1", "p1"), source("CO-2.1", "p4"))
    content = [
        tool_result("toolu_1", [search_result_block(entry) for entry in entries]),
        tool_result("toolu_2", [{"type": "text", "text": "No handbook passages matched."}]),
    ]

    async with tenant_session(app_engine, context_of(tenant)) as db:
        await append_messages(
            db,
            conversation_id,
            turn_id,
            [tool_call("toolu_1", "toolu_2"), StoredMessage("user", content, entries)],
        )

    async with tenant_session(app_engine, context_of(tenant)) as db:
        assert await search_sources(db, conversation_id) == list(entries)


@pytest.mark.parametrize("claimed", [0, 2, 4])
async def test_sources_that_do_not_match_the_search_results_are_refused(
    app_engine: AsyncEngine, make_tenant: MakeTenant, claimed: int
) -> None:
    tenant = await make_tenant()
    conversation_id = await new_conversation(app_engine, tenant)
    turn_id = await new_turn(app_engine, tenant, conversation_id)
    entries = tuple(source(f"CA-{n}", "p1") for n in range(3))
    content = [tool_result("toolu_1", [search_result_block(entry) for entry in entries])]

    async with tenant_session(app_engine, context_of(tenant)) as db:
        with pytest.raises(ValueError, match="search_result"):
            await append_messages(
                db,
                conversation_id,
                turn_id,
                [
                    StoredMessage("user", [{"type": "text", "text": "fine"}]),
                    StoredMessage(
                        "user", content, tuple(source(f"X-{n}", "p1") for n in range(claimed))
                    ),
                ],
            )

    async with tenant_session(app_engine, context_of(tenant)) as db:
        assert await model_history(db, conversation_id) == []


async def test_sources_on_a_message_with_no_search_results_are_refused(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    conversation_id = await new_conversation(app_engine, tenant)
    turn_id = await new_turn(app_engine, tenant, conversation_id)

    async with tenant_session(app_engine, context_of(tenant)) as db:
        with pytest.raises(ValueError, match="search_result"):
            await append_messages(
                db,
                conversation_id,
                turn_id,
                [
                    StoredMessage(
                        "assistant", [{"type": "text", "text": "hi"}], (source("CA-4.3", "p2"),)
                    )
                ],
            )


async def test_finishing_a_turn_that_does_not_exist_fails(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    async with tenant_session(app_engine, context_of(tenant)) as db:
        with pytest.raises(LookupError):
            await finish_turn(db, UUID(int=1), TurnOutcome(status="completed"))


async def test_search_sources_run_in_order_across_turns_even_a_recovered_one(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    conversation_id = await new_conversation(app_engine, tenant)
    first = await new_turn(app_engine, tenant, conversation_id, "First question")
    async with tenant_session(app_engine, context_of(tenant)) as db:
        await append_messages(
            db,
            conversation_id,
            first,
            [
                StoredMessage("user", [{"type": "text", "text": "First question"}]),
                search_result_message((source("CA-4.3", "p2", "p3"), source("US-1.1", "p1"))),
            ],
        )
    # The first turn's task died with its trace empty: it is recovered as failed.
    async with owner_engine.begin() as connection:
        await connection.execute(
            text("UPDATE ai_turns SET started_at = now() - interval '11 minutes' WHERE id = :id"),
            {"id": first},
        )
    async with tenant_session(app_engine, context_of(tenant)) as db:
        assert await recover_abandoned(db, conversation_id) == 1

    second = await new_turn(app_engine, tenant, conversation_id, "Second question")
    async with tenant_session(app_engine, context_of(tenant)) as db:
        await append_messages(
            db,
            conversation_id,
            second,
            [
                StoredMessage("user", [{"type": "text", "text": "Second question"}]),
                search_result_message((source("CO-2.1", "p4"),)),
            ],
        )

    async with tenant_session(app_engine, context_of(tenant)) as db:
        sources = await search_sources(db, conversation_id)

    assert sources == [source("CA-4.3", "p2", "p3"), source("US-1.1", "p1"), source("CO-2.1", "p4")]


async def test_source_entries_are_stored_with_camel_case_keys(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    conversation_id = await new_conversation(app_engine, tenant)
    turn_id = await new_turn(app_engine, tenant, conversation_id)
    async with tenant_session(app_engine, context_of(tenant)) as db:
        await append_messages(
            db,
            conversation_id,
            turn_id,
            [
                StoredMessage("user", [{"type": "text", "text": "No sources here"}]),
                search_result_message((source("CA-4.3", "p2", "p3"),)),
            ],
        )

    async with tenant_session(app_engine, context_of(tenant)) as db:
        rows: Sequence[list[dict[str, Any]] | None] = (
            (
                await db.execute(
                    text(
                        "SELECT sources FROM ai_messages"
                        " WHERE conversation_id = :c ORDER BY position"
                    ),
                    {"c": conversation_id},
                )
            )
            .scalars()
            .all()
        )

    assert rows[0] is None
    # A message without search results has SQL NULL in `sources`, not the JSON value null.
    async with tenant_session(app_engine, context_of(tenant)) as db:
        nulls: Sequence[bool] = (
            (
                await db.execute(
                    text(
                        "SELECT sources IS NULL FROM ai_messages"
                        " WHERE conversation_id = :c ORDER BY position"
                    ),
                    {"c": conversation_id},
                )
            )
            .scalars()
            .all()
        )
    assert list(nulls) == [True, False]
    assert rows[1] == [
        {
            "sectionId": "CA-4.3",
            "passageIds": ["p2", "p3"],
            "title": "Sick leave",
            "groupName": "California addendum",
            "audienceLabel": "California",
            "lastUpdated": "2026-09-12",
            "deepLink": "/handbook/CA-4.3?passage=p2",
        }
    ]
    assert SourceEntry.from_json(rows[1][0]) == source("CA-4.3", "p2", "p3")


async def test_the_current_conversation_is_the_newest(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    actor = actor_of(tenant, tenant.employee_id)
    # The tenant's sample data already has an older conversation for the employee. Each of these
    # commits in its own transaction, so their creation times differ.
    first = await new_conversation(app_engine, tenant)
    second = await new_conversation(app_engine, tenant)

    async with tenant_session(app_engine, context_of(tenant)) as db:
        current = await current_conversation(db, actor)

    assert current is not None
    assert current.id == second
    assert current.id != first
    assert (current.model, current.guard_model, current.effort) == (
        PINS.model,
        PINS.guard_model,
        PINS.effort,
    )
    assert (current.prompt_version, current.toolset_version) == (
        PINS.prompt_version,
        PINS.toolset_version,
    )


async def test_nobody_gets_another_persons_conversation(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    await new_conversation(app_engine, tenant)
    colleague = actor_of(tenant, tenant.colleague_id)

    async with tenant_session(app_engine, context_of(tenant, tenant.colleague_id)) as db:
        assert await current_conversation(db, colleague) is None

    # Even an actor who claims to be the owner gets nothing from a session scoped to someone
    # else: row-level security, not this function, is what keeps the rows apart.
    impostor = actor_of(tenant, tenant.employee_id)
    async with tenant_session(app_engine, context_of(tenant, tenant.colleague_id)) as db:
        assert await current_conversation(db, impostor) is None


async def test_a_message_cannot_be_stored_with_a_turn_of_another_conversation(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    first = await new_conversation(app_engine, tenant)
    first_turn = await new_turn(app_engine, tenant, first)
    second = await new_conversation(app_engine, tenant)
    message = StoredMessage("user", [{"type": "text", "text": "Which conversation am I in?"}])

    async with tenant_session(app_engine, context_of(tenant)) as db:
        with pytest.raises(ValueError, match="turn"):
            await append_messages(db, second, first_turn, [message])
        with pytest.raises(ValueError, match="turn"):
            await append_messages(db, second, UUID(int=1), [message])
        # Its own turn is fine, and nothing was stored by the refused calls.
        assert await model_history(db, second) == []
        await append_messages(db, first, first_turn, [message])
        assert len(await model_history(db, first)) == 1


async def test_every_field_of_a_turn_outcome_reaches_the_row(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    conversation_id = await new_conversation(app_engine, tenant)
    turn_id = await new_turn(app_engine, tenant, conversation_id)
    expected: dict[str, Any] = {
        "status": "stopped",
        "error_code": "e-code",
        "answer_text": "Partial answer",
        "citations": [{"marker": 1, "sectionId": "CA-4.3"}],
        "guard_verdict": {"verdict": "pass", "reason": "ok"},
        "tool_calls": [{"name": "search_handbook", "ok": False, "durationMs": 7}],
        "sections_retrieved": [{"sectionId": "CA-4.3", "passageIds": ["p2"]}],
        "served_by_models": ["claude-opus-5-5", "claude-opus-5"],
        "effort": "high",
        "prompt_version": "prompt-7",
        "toolset_version": "tools-9",
        "input_tokens": 11,
        "output_tokens": 22,
        "cache_read_tokens": 33,
        "cache_write_tokens": 44,
        "cost_usd": Decimal("0.123457"),
        "first_event_ms": 55,
        "total_ms": 66,
        "refusal": True,
        "fallback": True,
        "injection_suspected": True,
    }
    # A new field on TurnOutcome has to be given a distinctive value here.
    assert set(expected) == {f.name for f in dataclasses.fields(TurnOutcome)}
    outcome = TurnOutcome(**expected)
    async with tenant_session(app_engine, context_of(tenant)) as db:
        await finish_turn(db, turn_id, outcome)

    columns = ", ".join(expected)
    async with owner_engine.connect() as connection:
        row = (
            (
                await connection.execute(
                    text(f"SELECT {columns} FROM ai_turns WHERE id = :id"),  # noqa: S608
                    {"id": turn_id},
                )
            )
            .mappings()
            .one()
        )
    assert dict(row) == expected


async def test_a_message_cannot_be_appended_to_a_turn_that_has_ended(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    # A task whose turn was recovered as failed can wake up late. Its messages must not land in
    # the history the next turn builds on.
    tenant = await make_tenant()
    conversation_id = await new_conversation(app_engine, tenant)
    turn_id = await new_turn(app_engine, tenant, conversation_id)
    async with tenant_session(app_engine, context_of(tenant)) as db:
        await finish_turn(db, turn_id, TurnOutcome(status="failed", error_code="abandoned"))
    late = StoredMessage("assistant", [{"type": "text", "text": "I was slow"}])

    async with tenant_session(app_engine, context_of(tenant)) as db:
        with pytest.raises(TurnFinished):
            await append_messages(db, conversation_id, turn_id, [late])
        # The transaction is still usable, and nothing was stored.
        assert await model_history(db, conversation_id) == []


async def wait_for_a_blocked_update(owner_engine: AsyncEngine) -> None:
    for _ in range(100):
        async with owner_engine.connect() as connection:
            blocked: int = (
                await connection.execute(
                    text(
                        "SELECT count(*) FROM pg_stat_activity"
                        " WHERE wait_event_type = 'Lock' AND query LIKE 'UPDATE ai_turns%'"
                    )
                )
            ).scalar_one()
        if blocked:
            return
        await asyncio.sleep(0.05)
    pytest.fail("no UPDATE of a turn is waiting for a lock")


async def test_appending_locks_the_turn_so_recovery_waits_for_it(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    conversation_id = await new_conversation(app_engine, tenant)
    turn_id = await new_turn(app_engine, tenant, conversation_id)
    async with owner_engine.begin() as connection:
        await connection.execute(
            text("UPDATE ai_turns SET started_at = now() - interval '11 minutes' WHERE id = :id"),
            {"id": turn_id},
        )

    async def recover() -> int:
        async with tenant_session(app_engine, context_of(tenant)) as db:
            return await recover_abandoned(db, conversation_id)

    # The append checks that the turn is running and holds it so until its transaction ends. If it
    # didn't, recovery could fail the turn between that check and the insert.
    async with tenant_session(app_engine, context_of(tenant)) as db:
        await append_messages(
            db, conversation_id, turn_id, [StoredMessage("user", [{"type": "text", "text": "Hi"}])]
        )
        recovery = asyncio.create_task(recover())
        try:
            await wait_for_a_blocked_update(owner_engine)
            assert not recovery.done()
        except BaseException:
            recovery.cancel()
            raise

    assert await recovery == 1


def tool_call(*ids: str) -> StoredMessage:
    return StoredMessage(
        "assistant",
        [
            {"type": "text", "text": "Let me look that up."},
            *({"type": "tool_use", "id": i, "name": "search_handbook", "input": {}} for i in ids),
        ],
    )


def tool_answer(*ids: str) -> StoredMessage:
    return StoredMessage(
        "user",
        [
            {"type": "tool_result", "tool_use_id": i, "content": [{"type": "text", "text": "ok"}]}
            for i in ids
        ],
    )


@pytest.mark.parametrize(
    "batch",
    [
        [tool_call("toolu_1")],
        [StoredMessage("user", [{"type": "text", "text": "Q"}]), tool_call("toolu_1")],
        [tool_call("toolu_1", "toolu_2"), tool_answer("toolu_1")],
        [tool_call("toolu_1"), tool_answer("toolu_other")],
        [tool_call("toolu_1"), StoredMessage("user", [{"type": "text", "text": "No result"}])],
        [tool_call("toolu_1"), tool_call("toolu_2")],
    ],
    ids=["lone", "lone after a question", "missing id", "wrong id", "no tool_result", "no user"],
)
async def test_a_tool_call_is_stored_with_all_of_its_results_or_not_at_all(
    app_engine: AsyncEngine, make_tenant: MakeTenant, batch: list[StoredMessage]
) -> None:
    # A dangling tool_use in the history would make every later call a 400, for good.
    tenant = await make_tenant()
    conversation_id = await new_conversation(app_engine, tenant)
    turn_id = await new_turn(app_engine, tenant, conversation_id)

    async with tenant_session(app_engine, context_of(tenant)) as db:
        with pytest.raises(ValueError, match="tool_use"):
            await append_messages(db, conversation_id, turn_id, batch)
        assert await model_history(db, conversation_id) == []


async def test_a_tool_call_with_every_result_is_stored(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    conversation_id = await new_conversation(app_engine, tenant)
    turn_id = await new_turn(app_engine, tenant, conversation_id)

    async with tenant_session(app_engine, context_of(tenant)) as db:
        await append_messages(
            db,
            conversation_id,
            turn_id,
            [
                StoredMessage("user", [{"type": "text", "text": "Q"}]),
                tool_call("toolu_1", "toolu_2"),
                tool_answer("toolu_2", "toolu_1"),
                StoredMessage("assistant", [{"type": "text", "text": "Done."}]),
            ],
        )

    async with tenant_session(app_engine, context_of(tenant)) as db:
        history = await model_history(db, conversation_id)
    assert [m["role"] for m in history] == ["user", "assistant", "user", "assistant"]


async def test_a_turn_cannot_be_finished_as_running(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    # The trigger allows running to running, so only this check stops a turn that never ends.
    tenant = await make_tenant()
    conversation_id = await new_conversation(app_engine, tenant)
    turn_id = await new_turn(app_engine, tenant, conversation_id)

    async with tenant_session(app_engine, context_of(tenant)) as db:
        with pytest.raises(ValueError, match="running"):
            await finish_turn(db, turn_id, TurnOutcome(status="running"))  # type: ignore[arg-type]


async def test_an_assistant_message_with_no_content_is_refused(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    # The API rejects an empty assistant message anywhere but last, so storing one (a refusal
    # before any output makes exactly that) would wedge the conversation for good.
    tenant = await make_tenant()
    conversation_id = await new_conversation(app_engine, tenant)
    turn_id = await new_turn(app_engine, tenant, conversation_id)

    async with tenant_session(app_engine, context_of(tenant)) as db:
        with pytest.raises(ValueError, match="empty"):
            await append_messages(
                db,
                conversation_id,
                turn_id,
                [
                    StoredMessage("user", [{"type": "text", "text": "Q"}]),
                    StoredMessage("assistant", []),
                ],
            )
        assert await model_history(db, conversation_id) == []


async def started_and_ended(db: AsyncSession, turn_id: UUID) -> tuple[datetime, datetime]:
    row = (
        await db.execute(
            text("SELECT started_at, ended_at FROM ai_turns WHERE id = :id"), {"id": turn_id}
        )
    ).one()
    return row.started_at, row.ended_at


async def test_a_finished_turn_ends_when_it_is_written_not_when_the_transaction_began(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    conversation_id = await new_conversation(app_engine, tenant)
    actor = actor_of(tenant, tenant.employee_id)

    async with tenant_session(app_engine, context_of(tenant)) as db:
        conversation = await current_conversation(db, actor)
        assert conversation is not None
        assert conversation.id == conversation_id
        turn = await start_turn(db, conversation, "Quick question")
        await asyncio.sleep(0.05)
        await finish_turn(db, turn.id, TurnOutcome(status="completed"))
        started, ended = await started_and_ended(db, turn.id)

    assert ended - started >= timedelta(milliseconds=40)


async def test_an_abandoned_turn_ends_when_it_is_marked_not_when_the_transaction_began(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    conversation_id = await new_conversation(app_engine, tenant)
    turn_id = await new_turn(app_engine, tenant, conversation_id)
    async with owner_engine.begin() as connection:
        await connection.execute(
            text("UPDATE ai_turns SET started_at = now() - interval '11 minutes' WHERE id = :id"),
            {"id": turn_id},
        )

    async with tenant_session(app_engine, context_of(tenant)) as db:
        began: datetime = (await db.execute(text("SELECT now()"))).scalar_one()
        await asyncio.sleep(0.05)
        assert await recover_abandoned(db, conversation_id) == 1
        _, ended = await started_and_ended(db, turn_id)

    assert ended - began >= timedelta(milliseconds=40)


async def test_appending_does_not_block_writes_that_point_at_the_turn(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    # Every foreign-key check on a turn takes a key-share lock on it. If the append's lock
    # conflicted with that, a spend row for the turn written on another connection (Stage 2's
    # reservation, while a message is being stored) would wait for the append to end.
    tenant = await make_tenant()
    conversation_id = await new_conversation(app_engine, tenant)
    turn_id = await new_turn(app_engine, tenant, conversation_id)

    async def write_a_spend_row() -> None:
        async with tenant_session(app_engine, context_of(tenant)) as other:
            await other.execute(
                text(
                    "INSERT INTO ai_spend (tenant_id, turn_id, kind, amount_usd)"
                    " VALUES (:tenant, :turn, 'reserve', 0.01)"
                ),
                {"tenant": tenant.id, "turn": turn_id},
            )

    async with tenant_session(app_engine, context_of(tenant)) as db:
        await append_messages(
            db, conversation_id, turn_id, [StoredMessage("user", [{"type": "text", "text": "Hi"}])]
        )
        await asyncio.wait_for(write_a_spend_row(), timeout=3)


@pytest.mark.parametrize(
    "batch",
    [
        [tool_answer("toolu_1")],
        [StoredMessage("user", [{"type": "text", "text": "Q"}]), tool_answer("toolu_1")],
        [tool_call("toolu_1"), tool_answer("toolu_1", "toolu_stray")],
        [tool_call("toolu_1"), tool_answer("toolu_other")],
        [
            tool_call("toolu_1"),
            tool_answer("toolu_1"),
            StoredMessage("assistant", [{"type": "text", "text": "Done."}]),
            tool_answer("toolu_1"),
        ],
    ],
    ids=["starts with a result", "after a plain message", "extra id", "wrong id", "answered twice"],
)
async def test_a_tool_result_must_answer_the_tool_use_just_before_it_in_the_same_call(
    app_engine: AsyncEngine, make_tenant: MakeTenant, batch: list[StoredMessage]
) -> None:
    # An orphan tool_result in the history is refused by the API for good, like a dangling
    # tool_use. A tool call and its results are always stored together, so the pair is in one call.
    tenant = await make_tenant()
    conversation_id = await new_conversation(app_engine, tenant)
    turn_id = await new_turn(app_engine, tenant, conversation_id)

    async with tenant_session(app_engine, context_of(tenant)) as db:
        with pytest.raises(ValueError, match="tool_result"):
            await append_messages(db, conversation_id, turn_id, batch)
        assert await model_history(db, conversation_id) == []


async def test_tool_results_must_come_before_any_other_content_in_their_message(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    # The Messages API refuses a user message that puts text before its tool_result blocks.
    tenant = await make_tenant()
    conversation_id = await new_conversation(app_engine, tenant)
    turn_id = await new_turn(app_engine, tenant, conversation_id)
    answer = tool_answer("toolu_1")
    late = StoredMessage("user", [{"type": "text", "text": "Also, a note."}, *answer.content])

    async with tenant_session(app_engine, context_of(tenant)) as db:
        with pytest.raises(ValueError, match="before"):
            await append_messages(db, conversation_id, turn_id, [tool_call("toolu_1"), late])
        assert await model_history(db, conversation_id) == []
        # Text after the results is fine.
        early = StoredMessage("user", [*answer.content, {"type": "text", "text": "Also, a note."}])
        await append_messages(db, conversation_id, turn_id, [tool_call("toolu_1"), early])
        assert len(await model_history(db, conversation_id)) == 2


@pytest.mark.parametrize("text_value", ["", "   ", "\n\t"])
@pytest.mark.parametrize("role", ["user", "assistant"])
async def test_a_message_with_an_empty_text_block_is_refused(
    app_engine: AsyncEngine, make_tenant: MakeTenant, role: str, text_value: str
) -> None:
    # The API rejects an empty text block anywhere but last, and a refusal or a max_tokens stop
    # can leave one. Stored, it would wedge the conversation.
    tenant = await make_tenant()
    conversation_id = await new_conversation(app_engine, tenant)
    turn_id = await new_turn(app_engine, tenant, conversation_id)
    content = [{"type": "text", "text": "Fine."}, {"type": "text", "text": text_value}]
    message = StoredMessage(role, content)  # type: ignore[arg-type]

    async with tenant_session(app_engine, context_of(tenant)) as db:
        with pytest.raises(ValueError, match="empty"):
            await append_messages(db, conversation_id, turn_id, [message])
        assert await model_history(db, conversation_id) == []


async def test_a_thinking_block_with_no_visible_text_is_accepted(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    # Under `display: "updates"` the thinking text is empty and the signature carries the block.
    tenant = await make_tenant()
    conversation_id = await new_conversation(app_engine, tenant)
    turn_id = await new_turn(app_engine, tenant, conversation_id)
    message = StoredMessage(
        "assistant",
        [
            {"type": "thinking", "thinking": "", "signature": "EuYBCkQYAiJA"},
            {"type": "text", "text": "Done."},
        ],
    )

    async with tenant_session(app_engine, context_of(tenant)) as db:
        await append_messages(db, conversation_id, turn_id, [message])
        assert len(await model_history(db, conversation_id)) == 1
