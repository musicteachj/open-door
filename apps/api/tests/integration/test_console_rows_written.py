"""The console row, written by the turn's own ending (Phase 7, ADR 0016).

Every ending writes exactly one row, in the transaction that finishes the turn. A flagged turn's row
holds only its date and its counts. A console row that cannot be written never fails the turn. The
rows are read back as Dana (HR), the only reader the database allows.
"""

import asyncio
import contextlib
import json
import logging
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid5

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.ai import turn as turn_module
from app.ai.budget import settle as budget_settle
from app.ai.console_rows import build_console_row
from app.ai.conversations import ABANDONED_AFTER
from app.ai.pricing import HAIKU, IterationUsage, Usage, cost_usd
from app.ai.scripted import GUARD_USAGE, MODEL_USAGE, ScriptedTransport
from app.ai.transport import GuardResult, ModelRequest, TextBlockEnd
from app.ai.transport import TextDelta as ModelText
from app.ai.turn import TurnEvent, run_turn, start_turn_run
from app.db.models import AiConsoleTurn
from app.db.tenancy import TenantContext, set_is_hr, tenant_session
from app.modules.sandbox.seed import SeedCompany
from tests.integration.conftest import audit_events
from tests.integration.test_turn import (
    NOW,
    OPUS,
    SICK,
    Env,
    Item,
    PlanTransport,
    _leave_the_daily_ledger_as_found,  # noqa: F401
    finished,
    make_env,
    raw_plan,
    search_plan,
    text_plan,
    tool_use_plan,
    wait_for_text,
)
from tests.integration.test_turn_proposals import _age, book

pytestmark = pytest.mark.integration

# Every column of a row, so a test can compare whole rows.
COLUMNS = [column.key for column in AiConsoleTurn.__table__.columns]


async def console_rows(env: Env) -> list[dict[str, Any]]:
    """Every console row of the sandbox, read as Dana in a session of her own."""
    tenant_id = env.deps.actor.tenant_id
    dana = uuid5(tenant_id, "person:dana")
    async with tenant_session(env.engine, TenantContext(tenant_id, dana)) as db:
        await set_is_hr(db, True)
        rows = (
            await db.scalars(
                select(AiConsoleTurn).order_by(
                    AiConsoleTurn.occurred_at.asc().nulls_last(), AiConsoleTurn.id
                )
            )
        ).all()
    return [{name: getattr(row, name) for name in COLUMNS} for row in rows]


async def only_row(env: Env) -> dict[str, Any]:
    (row,) = await console_rows(env)
    return row


def as_json(row: dict[str, Any]) -> str:
    return json.dumps(row, default=str)


# --- Every ending writes one row --------------------------------------------------------------


async def test_a_completed_turn_writes_one_complete_row(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    env = await make_env(app_engine, seeded_sandbox, persona="priya")
    await env.ask()

    row = await only_row(env)
    turn = await env.last_turn()
    assert row["flagged"] is False
    assert row["turn_id"] == turn.id
    assert row["occurred_on"] == date(2026, 10, 15)  # 17:00 UTC is 11:00 in Denver
    assert row["occurred_at"] == NOW
    assert (row["asker_role"], row["asker_location"]) == ("employee", "Oakland, CA")
    assert row["outcome"] == "answered"
    assert (row["guard_category"], row["injection_suspected"]) == ("ordinary", False)
    assert [tool["name"] for tool in row["tools"]] == ["search_handbook"]
    assert all(set(tool) == {"name", "ok", "durationMs"} for tool in row["tools"])
    assert "CA-4.3" in row["sections_retrieved"]
    assert "CA-4.3" in row["sections_cited"]
    assert row["card_action"] is None
    assert row["served_by"] == list(turn.served_by_models)
    assert (row["effort"], row["prompt_version"]) == (turn.effort, turn.prompt_version)
    assert row["cost_usd"] == turn.cost_usd
    assert row["total_ms"] == turn.total_ms
    assert row["guard_ms"] is not None
    assert row["first_text_ms"] is not None


def priced_text_plan(request: Any, number: int) -> list[Item]:
    return [
        ModelText("You get 40 hours."),
        TextBlockEnd(()),
        finished(
            [{"type": "text", "text": "You get 40 hours."}],
            iterations=(IterationUsage(OPUS, MODEL_USAGE),),
        ),
    ]


def priced_guard() -> GuardResult:
    return GuardResult(
        category="ordinary",
        kind=None,
        injection_suspected=False,
        usage=PRICED_GUARD_USAGE,
        served_by=HAIKU,
    )


PRICED_GUARD_USAGE = Usage(1000, 100, 0, 0)


async def test_the_rows_tokens_include_the_safety_checks_and_its_cost_is_not_counted_twice(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    transport = PlanTransport(priced_text_plan, guard_result=priced_guard)
    env = await make_env(app_engine, seeded_sandbox, transport=transport)
    await env.ask()

    row = await only_row(env)
    turn = await env.last_turn()
    # `ai_turns` holds the main model's tokens; the console row adds the safety check's.
    assert turn.input_tokens == MODEL_USAGE.input_tokens
    assert row["input_tokens"] == MODEL_USAGE.input_tokens + PRICED_GUARD_USAGE.input_tokens
    assert row["output_tokens"] == MODEL_USAGE.output_tokens + PRICED_GUARD_USAGE.output_tokens
    # The cost on `ai_turns` already has the safety check's in it: the row copies it, once.
    expected = cost_usd(OPUS, MODEL_USAGE) + cost_usd(HAIKU, PRICED_GUARD_USAGE)
    assert row["cost_usd"] == turn.cost_usd == await env.spend_total(turn.id) == expected > 0


async def test_a_manager_and_hr_are_labeled_by_their_role(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    marcus = await make_env(app_engine, seeded_sandbox, persona="marcus")
    await marcus.ask()
    dana = await make_env(app_engine, seeded_sandbox, persona="dana")
    await dana.ask()

    assert sorted(row["asker_role"] for row in await console_rows(marcus)) == ["hr", "manager"]


async def test_a_turn_that_says_it_could_not_find_the_answer_is_not_found(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    transport = PlanTransport(
        text_plan("I couldn't find that in the handbook. I can put you in touch with HR.")
    )
    env = await make_env(app_engine, seeded_sandbox, transport=transport)
    await env.ask("What is the pet insurance policy?")

    assert (await only_row(env))["outcome"] == "not_found"


async def test_a_max_tokens_completion_is_answered(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    transport = PlanTransport(search_plan(), text_plan("You get 40 ho", "max_tokens"))
    env = await make_env(app_engine, seeded_sandbox, transport=transport)
    await env.ask()

    assert (await only_row(env))["outcome"] == "answered"


async def test_a_refused_turn_keeps_the_refusals_category_and_never_its_explanation(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    env = await make_env(app_engine, seeded_sandbox)
    await env.ask("scripted safety refusal")

    row = await only_row(env)
    assert (row["outcome"], row["refusal_category"]) == ("refused", "general_harms")
    assert "Scripted safety refusal" not in as_json(row)


async def test_a_budget_stop_before_the_guard_is_a_budget_row_with_no_guard_time(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    from app.ai.budget import Caps

    env = await make_env(app_engine, seeded_sandbox, caps=Caps(Decimal("0.0001"), Decimal(1000)))
    await env.ask()

    row = await only_row(env)
    assert row["outcome"] == "budget"
    assert row["guard_ms"] is None
    assert row["guard_category"] is None


async def test_a_failed_turn_is_failed(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    env = await make_env(app_engine, seeded_sandbox)
    await env.ask("scripted mid-stream error")

    row = await only_row(env)
    assert row["outcome"] == "failed"


async def test_a_guard_unavailable_turn_is_its_own_outcome_and_not_redacted(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    env = await make_env(app_engine, seeded_sandbox)
    await env.ask("scripted guard failure")

    row = await only_row(env)
    assert (row["flagged"], row["outcome"]) == (False, "guard_unavailable")


async def test_a_stopped_turn_writes_a_stopped_row(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    env = await make_env(
        app_engine, seeded_sandbox, transport=ScriptedTransport(delta_delay_seconds=0.05)
    )
    seen: list[TurnEvent] = []

    async def consume() -> None:
        async for event in run_turn(
            env.deps, conversation=env.conversation, question="What is Leo's home address?", now=NOW
        ):
            seen.append(event)

    task = asyncio.create_task(consume())
    await wait_for_text(seen)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    row = await only_row(env)
    assert (row["flagged"], row["outcome"]) == (False, "stopped")
    assert row["first_text_ms"] is not None


async def test_two_turns_write_two_rows(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    env = await make_env(app_engine, seeded_sandbox)
    await env.ask()
    await env.ask("And how does sick leave accrue?")

    rows = await console_rows(env)
    assert len(rows) == 2
    assert len({row["id"] for row in rows}) == 2
    assert {row["turn_id"] for row in rows} == {turn.id for turn in await env.turns()}


async def test_a_card_is_named_by_its_action(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    env = await make_env(
        app_engine, seeded_sandbox, transport=PlanTransport(tool_use_plan(book()), text_plan("Ok."))
    )
    await env.ask("Please book Friday off.")

    row = await only_row(env)
    assert row["card_action"] == "timeoff.request"
    assert row["tools"][0]["name"] == "propose_time_off_request"


async def test_the_date_is_denvers_even_when_oakland_is_a_day_behind(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    env = await make_env(app_engine, seeded_sandbox, persona="priya")
    # 06:30 UTC on Oct 16 is 11:30 PM on Oct 15 in Oakland and 12:30 AM on Oct 16 in Denver.
    await env.ask(now=datetime(2026, 10, 16, 6, 30, tzinfo=UTC))

    assert (await only_row(env))["occurred_on"] == date(2026, 10, 16)


# --- Flagged turns ----------------------------------------------------------------------------


def assert_only_the_date_and_the_counts(row: dict[str, Any]) -> None:
    assert row["flagged"] is True
    for column in (
        "turn_id",
        "occurred_at",
        "asker_role",
        "asker_location",
        "outcome",
        "refusal_category",
        "guard_category",
        "injection_suspected",
        "tools",
        "sections_retrieved",
        "sections_cited",
        "card_action",
    ):
        assert row[column] is None, column


async def test_a_crisis_turn_writes_a_redacted_row(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    env = await make_env(app_engine, seeded_sandbox, persona="priya")
    await env.ask("I want to hurt myself")

    row = await only_row(env)
    assert_only_the_date_and_the_counts(row)
    assert row["occurred_on"] == date(2026, 10, 15)
    assert row["input_tokens"] == GUARD_USAGE.input_tokens  # the safety check read it
    assert row["guard_ms"] is not None
    assert row["first_text_ms"] is None
    turn = await env.last_turn()
    assert str(turn.id) not in as_json(row)
    assert "Oakland" not in as_json(row)


async def test_a_sensitive_turn_writes_a_redacted_row_whatever_else_it_did(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    transport = PlanTransport(search_plan(), text_plan("You get 40 hours.", cite=True))
    env = await make_env(app_engine, seeded_sandbox, persona="priya", transport=transport)
    await env.ask("My coworker is harassing me. What does the handbook say?")

    row = await only_row(env)
    assert_only_the_date_and_the_counts(row)
    assert row["total_ms"] is not None
    assert row["served_by"]


async def test_a_sensitive_turn_that_made_a_card_redacts_the_card_too(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    env = await make_env(
        app_engine, seeded_sandbox, transport=PlanTransport(tool_use_plan(book()), text_plan("Ok."))
    )
    await env.ask("My coworker harassed me, so please book Friday off.")

    row = await only_row(env)
    assert_only_the_date_and_the_counts(row)
    assert "timeoff" not in as_json(row)
    # The card itself was made: only the console row hides it.
    async with tenant_session(env.engine, env.ctx) as db:
        count: int = (await db.execute(text("SELECT count(*) FROM ai_proposals"))).scalar_one()
    assert count == 1


async def test_a_flagged_row_is_not_readable_by_the_person_who_asked(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    env = await make_env(app_engine, seeded_sandbox, persona="priya")
    await env.ask("I want to hurt myself")
    await env.ask()

    async with tenant_session(env.engine, env.ctx) as db:
        own: int = (await db.execute(text("SELECT count(*) FROM ai_console_turns"))).scalar_one()
    assert own == 0
    assert len(await console_rows(env)) == 2


# --- Abandoned turns --------------------------------------------------------------------------


async def test_an_abandoned_turn_gets_a_redacted_row_when_it_is_recovered(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    env = await make_env(app_engine, seeded_sandbox)
    run = await start_turn_run(
        env.deps, conversation=env.conversation, question="Book Friday.", now=NOW
    )
    await _age(owner_engine, run.turn_id, ABANDONED_AFTER + timedelta(minutes=1))
    assert await console_rows(env) == []

    # The next question recovers it, in its own start-up transaction.
    await env.ask()

    abandoned, answered = sorted(await console_rows(env), key=lambda row: not row["flagged"])
    assert_only_the_date_and_the_counts(abandoned)
    assert abandoned["served_by"] == []
    assert (abandoned["input_tokens"], abandoned["cost_usd"]) == (0, 0)
    assert (abandoned["guard_ms"], abandoned["first_text_ms"], abandoned["total_ms"]) == (
        None,
        None,
        None,
    )
    assert (abandoned["effort"], abandoned["prompt_version"]) == (None, None)
    assert answered["flagged"] is False
    assert str(run.turn_id) not in as_json(abandoned)


async def test_an_abandoned_turn_is_dated_by_when_it_was_asked_not_when_it_was_recovered(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    env = await make_env(app_engine, seeded_sandbox)
    run = await start_turn_run(env.deps, conversation=env.conversation, question="x", now=NOW)
    # 11:30 PM on Jan 15 in Denver (MST, UTC-7) is already Jan 16 in UTC.
    async with owner_engine.begin() as connection:
        await connection.execute(
            text("UPDATE ai_turns SET started_at = :moment WHERE id = :id"),
            {"moment": datetime(2026, 1, 16, 6, 30, tzinfo=UTC), "id": run.turn_id},
        )

    await env.ask()

    abandoned = next(row for row in await console_rows(env) if row["flagged"])
    assert abandoned["occurred_on"] == date(2026, 1, 15)


async def test_a_recovered_turn_is_recovered_once_and_so_has_one_row(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    env = await make_env(app_engine, seeded_sandbox)
    run = await start_turn_run(env.deps, conversation=env.conversation, question="x", now=NOW)
    await _age(owner_engine, run.turn_id, ABANDONED_AFTER + timedelta(minutes=1))
    await env.ask()
    await env.ask()

    assert sum(row["flagged"] for row in await console_rows(env)) == 1


async def test_an_abandoned_row_that_cannot_be_written_never_fails_the_new_question(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    seeded_sandbox: SeedCompany,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from app.ai import conversations

    monkeypatch.setattr(
        conversations,
        "build_abandoned_row",
        lambda **_: {"flagged": True, "occurred_on": date(2026, 10, 15), "outcome": "answered"},
    )
    env = await make_env(app_engine, seeded_sandbox)
    run = await start_turn_run(env.deps, conversation=env.conversation, question="x", now=NOW)
    await _age(owner_engine, run.turn_id, ABANDONED_AFTER + timedelta(minutes=1))

    with caplog.at_level(logging.ERROR):
        events = await env.ask()

    assert type(events[-1]).__name__ == "TurnCompleted"
    turns = await env.turns()
    assert [turn.error_code for turn in turns] == ["abandoned", None]
    assert [row["flagged"] for row in await console_rows(env)] == [False]
    assert "Writing the console row failed (IntegrityError)" in caplog.text


# --- The console never hurts the person -------------------------------------------------------


def leaky_builder(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """A bug that writes details onto a flagged row: the check constraint must refuse it."""
    row = build_console_row(*args, **kwargs)
    return {**row, "flagged": True, "outcome": "answered", "asker_role": "employee"}


async def test_a_console_insert_the_database_refuses_leaves_the_turn_finished(
    app_engine: AsyncEngine,
    seeded_sandbox: SeedCompany,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(turn_module, "build_console_row", leaky_builder)
    env = await make_env(app_engine, seeded_sandbox)

    with caplog.at_level(logging.DEBUG):
        events = await env.ask("How much PLANTED-QUESTION-9921 sick leave do I get?")

    assert type(events[-1]).__name__ == "TurnCompleted"
    turn = await env.last_turn()
    assert turn.status == "completed"
    assert turn.ended_at is not None
    assert turn.answer_text
    assert await console_rows(env) == []
    # The log names the error's type and nothing else of it: not the constraint, not the values.
    lines = [r.getMessage() for r in caplog.records if "console row" in r.getMessage()]
    assert lines == ["Writing the console row failed (IntegrityError)"]
    assert "PLANTED-QUESTION-9921" not in caplog.text
    assert "ck_ai_console_turns" not in caplog.text
    # The turn's other end-of-turn writes still happened (the history).
    assert len(await env.messages()) == 5


async def test_a_builder_that_raises_leaves_the_turn_finished(
    app_engine: AsyncEngine,
    seeded_sandbox: SeedCompany,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def broken(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("PLANTED-MESSAGE-5512")

    monkeypatch.setattr(turn_module, "build_console_row", broken)
    env = await make_env(app_engine, seeded_sandbox)

    with caplog.at_level(logging.DEBUG):
        events = await env.ask()

    assert type(events[-1]).__name__ == "TurnCompleted"
    assert (await env.last_turn()).status == "completed"
    assert await console_rows(env) == []
    assert "Building the console row failed (RuntimeError)" in caplog.text
    assert "PLANTED-MESSAGE-5512" not in caplog.text


async def test_a_failed_console_insert_does_not_undo_the_cards_cancellation(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A stopped turn cancels its card in the same transaction as the console row. The row's failure
    # rolls back its savepoint only.
    monkeypatch.setattr(turn_module, "build_console_row", leaky_builder)
    transport = PlanTransport(tool_use_plan(book()), lambda request, number: [30.0])
    env = await make_env(app_engine, seeded_sandbox, transport=transport)
    seen: list[TurnEvent] = []

    async def consume() -> None:
        async for event in run_turn(
            env.deps, conversation=env.conversation, question="Book Friday.", now=NOW
        ):
            seen.append(event)

    task = asyncio.create_task(consume())
    async with asyncio.timeout(10):
        while not any(type(event).__name__ == "Proposal" for event in seen):  # noqa: ASYNC110
            await asyncio.sleep(0.01)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    assert (await env.last_turn()).status == "stopped"
    async with tenant_session(env.engine, env.ctx) as db:
        result = await db.execute(text("SELECT status FROM ai_proposals"))
        statuses: list[str] = list(result.scalars().all())
    assert statuses == ["canceled"]
    assert await console_rows(env) == []


# --- No text reaches the row ------------------------------------------------------------------

PLANTED = "PLANTED-TEXT-4408"


async def test_no_planted_string_reaches_a_console_row(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    answer_env = await make_env(
        app_engine,
        seeded_sandbox,
        persona="priya",
        transport=PlanTransport(
            tool_use_plan(("search_handbook", {"query": f"sick leave {PLANTED}"})),
            text_plan(f"You get 40 hours. {PLANTED}", cite=True),
        ),
    )
    await answer_env.ask(f"How much sick leave do I get {PLANTED}?")

    refusal_env = await make_env(
        app_engine,
        seeded_sandbox,
        persona="mateo",
        transport=PlanTransport(
            raw_plan(
                [],
                "refusal",
            )
        ),
    )
    await refusal_env.ask("scripted safety refusal")

    planted_refusal = await make_env(
        app_engine,
        seeded_sandbox,
        persona="marcus",
        transport=PlanTransport(refusal_with_details),
    )
    await planted_refusal.ask(SICK)

    rows = await console_rows(answer_env)
    assert len(rows) == 3
    assert PLANTED not in as_json({"rows": rows})
    # The tool's input summary (which holds the planted query) is in the turn, not the row.
    assert PLANTED in (await answer_env.last_turn()).tool_calls[0]["inputSummary"]
    refused = next(row for row in rows if row["outcome"] == "refused")
    assert refused["refusal_category"] in {"general_harms", None}


def refusal_with_details(request: ModelRequest, number: int) -> list[Item]:
    return [
        ModelText(""),
        finished(
            [],
            "refusal",
            stop_details={
                "type": "refusal",
                "category": "general_harms",
                "explanation": f"Explained: {PLANTED}",
            },
        ),
    ]


def fallback_plan(request: ModelRequest, number: int) -> list[Item]:
    return [
        ModelText("You get 40 hours."),
        TextBlockEnd(()),
        finished([{"type": "text", "text": "You get 40 hours."}], fell_back=True),
    ]


async def test_a_turn_another_model_served_says_so_on_its_row_and_an_ordinary_one_does_not(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    fell = await make_env(app_engine, seeded_sandbox, transport=PlanTransport(fallback_plan))
    await fell.ask()
    ordinary = await make_env(app_engine, seeded_sandbox, persona="marcus")
    await ordinary.ask()

    rows = await console_rows(fell)
    assert sorted(row["fallback"] for row in rows) == [False, True]


async def test_a_flagged_turn_keeps_the_fallback_flag_like_its_model_labels(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    env = await make_env(app_engine, seeded_sandbox, transport=PlanTransport(fallback_plan))
    await env.ask("My coworker harassed me.")

    assert (await only_row(env))["fallback"] is True


@pytest.mark.parametrize(
    ("question", "kind"),
    [
        ("My coworker is harassing me. What does the handbook say?", "sensitive"),
        ("I want to hurt myself", "crisis"),
    ],
)
async def test_a_stop_while_the_guards_charge_is_settled_keeps_a_flagged_verdict_redacted(
    app_engine: AsyncEngine,
    seeded_sandbox: SeedCompany,
    monkeypatch: pytest.MonkeyPatch,
    question: str,
    kind: str,
) -> None:
    # The person presses Stop just after the safety check flagged the message, while
    # its charge is still being written to the ledger. The verdict is known, so the row must be
    # redacted, not written as an ordinary stopped turn with its time, role, and location.
    real_settle = budget_settle
    calls = 0

    async def stopped_during_the_first_settle(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise asyncio.CancelledError
        return await real_settle(*args, **kwargs)

    monkeypatch.setattr(turn_module, "settle", stopped_during_the_first_settle)
    env = await make_env(app_engine, seeded_sandbox, persona="priya")
    with contextlib.suppress(asyncio.CancelledError):
        await env.ask(question)

    assert calls == 1, "the stop came during the safety check's own settle"
    row = await only_row(env)
    assert_only_the_date_and_the_counts(row)
    # The stored verdict and the turn agree: the turn audits its escalation, as any stopped flagged
    # turn does, so the reload's panel is never one the audit didn't record.
    audit = [
        e
        for e in await audit_events(app_engine, seeded_sandbox.tenant_id)
        if e.action == "escalation.offered"
    ]
    assert len(audit) == 1
    assert audit[0].target_id == (await env.last_turn()).id
    assert audit[0].after is not None
    assert audit[0].after["kind"] == kind
