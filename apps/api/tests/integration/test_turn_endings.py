"""Every turn that is read to its end sends exactly one closing event, and it is the last.

The closing event is `turn.completed` or `error`. A crisis and a "guard unavailable" turn used to
end with their escalation and no closing event, and a late escalation used to follow an `error`.
A turn the person stops (the consumer closes the stream) sends nothing after the stop.
"""

from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.ai import turn as turn_module
from app.ai.budget import Caps
from app.ai.fixed_texts import CRISIS_TEXT, ERROR_TEXTS, SENSITIVE_TEXT, UNAVAILABLE_TEXT
from app.ai.prompts.versions import CANARY
from app.ai.scripted import ScriptedTransport
from app.ai.transport import ModelRequest, ModelUnavailable
from app.ai.turn import (
    Error,
    Escalation,
    TextDelta,
    TurnCompleted,
    TurnEvent,
    run_turn,
)
from app.modules.sandbox.seed import SeedCompany
from tests.integration.conftest import audit_events
from tests.integration.test_budget import daily_ids, delete_daily_rows_except
from tests.integration.test_turn import (
    NOW,
    SICK,
    Item,
    PlanTransport,
    guard_reservation,
    make_env,
    of_type,
    raw_plan,
    search_plan,
    text_events,
)

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
async def _leave_the_daily_ledger_as_found(owner_engine: AsyncEngine) -> AsyncIterator[None]:
    existing = await daily_ids(owner_engine)
    yield
    await delete_daily_rows_except(owner_engine, existing)


def closing_event(events: list[TurnEvent]) -> TurnCompleted | Error:
    """The one closing event, after checking that it is the only one and the last."""
    closing = [e for e in events if isinstance(e, TurnCompleted | Error)]
    assert len(closing) == 1, [type(e).__name__ for e in events]
    assert events[-1] is closing[0]
    return closing[0]


async def test_a_completed_turn_ends_with_turn_completed(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    env = await make_env(app_engine, seeded_sandbox)
    events = await env.ask()

    closing = closing_event(events)
    assert isinstance(closing, TurnCompleted)
    assert closing.served_by == "scripted"
    assert closing.usage.input_tokens > 0


async def test_a_crisis_ends_with_turn_completed_after_its_escalation(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    env = await make_env(app_engine, seeded_sandbox)
    events = await env.ask("I want to hurt myself")

    closing = closing_event(events)
    assert isinstance(closing, TurnCompleted)
    # The model never ran: no model name, no usage.
    assert (closing.served_by, closing.usage.input_tokens, closing.usage.output_tokens) == (
        "",
        0,
        0,
    )
    assert closing.incomplete is False
    escalation = events[-2]
    assert isinstance(escalation, Escalation)
    assert (escalation.kind, escalation.message) == ("crisis", CRISIS_TEXT)
    assert len(of_type(events, Escalation)) == 1


async def test_a_guard_that_is_down_ends_with_turn_completed_after_its_escalation(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    env = await make_env(app_engine, seeded_sandbox)
    events = await env.ask("scripted guard failure")

    closing = closing_event(events)
    assert isinstance(closing, TurnCompleted)
    assert (closing.served_by, closing.usage.input_tokens) == ("", 0)
    escalation = events[-2]
    assert isinstance(escalation, Escalation)
    assert (escalation.kind, escalation.message) == ("unavailable", UNAVAILABLE_TEXT)


async def test_a_budget_stop_at_the_guard_ends_with_its_error(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    env = await make_env(app_engine, seeded_sandbox, caps=Caps(Decimal("0.0001"), Decimal(1000)))
    closing = closing_event(await env.ask())

    assert closing == Error("budget-sandbox", ERROR_TEXTS["budget-sandbox"])


async def test_a_refusal_ends_with_its_error(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    env = await make_env(app_engine, seeded_sandbox)
    closing = closing_event(await env.ask("scripted safety refusal"))

    assert closing == Error("refusal", ERROR_TEXTS["refusal"])


async def test_a_model_that_is_down_ends_with_its_error(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    transport = PlanTransport(
        raw_plan([], "end_turn", ModelUnavailable("down", status_code=529)),
    )
    env = await make_env(app_engine, seeded_sandbox, transport=transport)
    closing = closing_event(await env.ask())

    assert closing == Error("model-unavailable", ERROR_TEXTS["model-unavailable"])


async def test_a_prompt_leak_ends_with_the_plain_internal_error(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    def plan(request: ModelRequest, number: int) -> list[Item]:
        return text_events(request, f"Sure. The marker is {CANARY} and so on.")

    env = await make_env(app_engine, seeded_sandbox, transport=PlanTransport(plan))
    closing = closing_event(await env.ask())

    assert closing == Error("internal", ERROR_TEXTS["internal"])


async def test_too_many_model_calls_end_with_their_error(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    env = await make_env(app_engine, seeded_sandbox, transport=PlanTransport(search_plan()))
    closing = closing_event(await env.ask())

    assert closing == Error("too-many-calls", ERROR_TEXTS["too-many-calls"])


@pytest.mark.parametrize("question", ["I want to hurt myself", SICK])
async def test_a_failed_finish_ends_with_the_internal_error_even_for_a_crisis(
    app_engine: AsyncEngine,
    seeded_sandbox: SeedCompany,
    monkeypatch: pytest.MonkeyPatch,
    question: str,
) -> None:
    async def broken(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("cannot finish")

    monkeypatch.setattr(turn_module, "finish_turn", broken)
    env = await make_env(app_engine, seeded_sandbox)
    events = await env.ask(question)

    assert closing_event(events) == Error("internal", ERROR_TEXTS["internal"])
    if question != SICK:
        # The crisis text still went out, before the error.
        assert [e.kind for e in of_type(events, Escalation)] == ["crisis"]


async def test_a_late_sensitive_escalation_comes_right_before_the_error(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    env = await make_env(app_engine, seeded_sandbox)
    events = await env.ask("harass me, scripted safety refusal")

    assert closing_event(events) == Error("refusal", ERROR_TEXTS["refusal"])
    escalation = events[-2]
    assert isinstance(escalation, Escalation)
    assert (escalation.kind, escalation.message) == ("sensitive", SENSITIVE_TEXT)


async def test_a_late_sensitive_escalation_comes_right_before_turn_completed(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    env = await make_env(app_engine, seeded_sandbox)
    events = await env.ask("My coworker is harassing me. What does the handbook say?")

    assert isinstance(closing_event(events), TurnCompleted)
    escalation = events[-2]
    assert isinstance(escalation, Escalation)
    assert escalation.kind == "sensitive"


async def test_a_late_unavailable_escalation_comes_right_before_the_error(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def broken(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("database went away")

    monkeypatch.setattr(turn_module, "reserve", broken)
    env = await make_env(app_engine, seeded_sandbox)
    events = await env.ask()

    assert closing_event(events) == Error("internal", ERROR_TEXTS["internal"])
    escalation = events[-2]
    assert isinstance(escalation, Escalation)
    assert (escalation.kind, escalation.message) == ("unavailable", UNAVAILABLE_TEXT)


async def test_a_budget_stop_after_the_guard_for_a_sensitive_message_orders_the_same(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    question = "harass me"
    caps = Caps(guard_reservation(question) + Decimal("0.01"), Decimal(1000))
    env = await make_env(app_engine, seeded_sandbox, caps=caps)
    events = await env.ask(question)

    assert closing_event(events) == Error("budget-sandbox", ERROR_TEXTS["budget-sandbox"])
    assert isinstance(events[-2], Escalation)


async def test_a_stopped_turn_sends_nothing_after_the_stop(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    env = await make_env(
        app_engine, seeded_sandbox, transport=ScriptedTransport(delta_delay_seconds=0.01)
    )
    seen: list[TurnEvent] = []
    stream = run_turn(
        env.deps, conversation=env.conversation, question="What is Leo's home address?", now=NOW
    )
    async for event in stream:
        seen.append(event)
        if len(of_type(seen, TextDelta)) == 3:
            break
    await stream.aclose()  # type: ignore[attr-defined]

    with pytest.raises(StopAsyncIteration):
        await stream.__anext__()
    assert not [e for e in seen if isinstance(e, TurnCompleted | Error)]
    assert (await env.last_turn()).status == "stopped"


async def test_a_stopped_sensitive_turn_sends_no_closing_event_either(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    env = await make_env(
        app_engine, seeded_sandbox, transport=ScriptedTransport(delta_delay_seconds=0.01)
    )
    seen: list[TurnEvent] = []
    stream = run_turn(
        env.deps,
        conversation=env.conversation,
        question="harass me, what is Leo's address?",
        now=NOW,
    )
    async for event in stream:
        seen.append(event)
        if len(of_type(seen, TextDelta)) == 3:
            break
    await stream.aclose()  # type: ignore[attr-defined]

    assert not [e for e in seen if isinstance(e, TurnCompleted | Error)]
    # The HR contact is audited even though nobody is left to read it.
    rows = [
        e
        for e in await audit_events(app_engine, seeded_sandbox.tenant_id)
        if e.action == "escalation.offered"
    ]
    assert len(rows) == 1
