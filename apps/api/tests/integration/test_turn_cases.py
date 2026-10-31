"""The next turn's context says once that the person opened a case from this conversation.

Like a card's outcome (ADR 0013), the line is made from structured data only (the category and the
reply-by date) and is tracked in `ai_messages.reported_outcomes` as `case:<id>:new`. A case opened
from "My cases" (no conversation) or from another conversation adds nothing. The model is a fake
that follows plans, and Priya Raman is the asker.
"""

from datetime import date
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.ai.proposals import cancel
from app.ai.transport import ModelUnavailable
from app.core.encryption import TEST_KEY_ID
from app.db.models import Case
from app.db.tenancy import tenant_session
from app.modules.sandbox.seed import SeedCompany
from tests.integration.conftest import OPAQUE
from tests.integration.test_timeoff_service import acting
from tests.integration.test_turn import (
    Env,
    PlanTransport,
    _leave_the_daily_ledger_as_found,  # noqa: F401
    guard_result,
    make_env,
    text_plan,
    tool_use_plan,
)
from tests.integration.test_turn_proposals import book, context_of, only_proposal

pytestmark = pytest.mark.integration

# The scripted guard calls every message in these tests sensitive, as a real case has one flagged.
SENSITIVE = guard_result("sensitive", "pay")
REPLY_BY = date(2026, 10, 28)
LINE = (
    "Since the last message: the person opened a confidential case with HR (workplace safety). "
    "HR replies by Wednesday, October 28."
)


async def open_case(
    env: Env,
    *,
    conversation_id: UUID | None,
    turn_id: UUID | None,
    category: str = "safety",
) -> UUID:
    """A case the person opened, as the person: from the given conversation and turn, or from
    neither (the My cases page)."""
    case_id = uuid4()
    async with tenant_session(env.engine, env.ctx) as db:
        db.add(
            Case(
                id=case_id,
                tenant_id=env.ctx.tenant_id,
                person_id=env.ctx.person_id,
                submission_id=uuid4(),
                category=category,
                reply_by=REPLY_BY,
                screening="sensitive",
                conversation_id=conversation_id,
                turn_id=turn_id,
                key_id=TEST_KEY_ID,
                wrapped_key=OPAQUE,
                text_ciphertext=OPAQUE,
            )
        )
    return case_id


async def first_turn_id(env: Env) -> UUID:
    first: UUID = (await env.turns())[0].id
    return first


async def case_entries(env: Env) -> list[str]:
    return [
        entry
        for row in await env.messages()
        if row.role == "system"
        for entry in (row.reported_outcomes or ())
        if entry.startswith("case:")
    ]


async def test_a_case_opened_from_this_conversation_is_told_to_the_next_turn_once(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    transport = PlanTransport(
        text_plan("Ok."), text_plan("Two."), text_plan("Three."), guard_result=SENSITIVE
    )
    env = await make_env(app_engine, seeded_sandbox, transport=transport)
    await env.ask("Someone keeps leaving a wet floor near my station.")
    case_id = await open_case(
        env, conversation_id=env.conversation.id, turn_id=await first_turn_id(env)
    )
    await env.ask("Thanks.")
    await env.ask("And now?")

    requests = env.transport.requests
    assert "Since the last message" not in context_of(requests, 0)
    second = context_of(requests, 1)
    assert second.count("Since the last message:") == 1
    assert LINE in second
    assert "Since the last message" not in context_of(requests, 2)
    assert await case_entries(env) == [f"case:{case_id}:new"]


async def test_the_line_comes_from_structured_data_only(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    env = await make_env(
        app_engine,
        seeded_sandbox,
        transport=PlanTransport(text_plan("Ok."), text_plan("Two."), guard_result=SENSITIVE),
    )
    await env.ask("My manager made an age comment.")
    await open_case(
        env,
        conversation_id=env.conversation.id,
        turn_id=await first_turn_id(env),
        category="harassment_discrimination",
    )
    await env.ask("Thanks.")

    second = context_of(env.transport.requests, 1)
    assert "with HR (harassment or discrimination). HR replies by Wednesday, October 28." in second
    # Not the person's message, not the case's ID.
    assert "age comment" not in second.split("Operator notes")[0]
    assert "case:" not in second


async def test_a_case_from_my_cases_adds_nothing(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    env = await make_env(
        app_engine, seeded_sandbox, transport=PlanTransport(text_plan("Ok."), text_plan("Two."))
    )
    await env.ask("Hello.")
    await open_case(env, conversation_id=None, turn_id=None)
    await env.ask("And now?")

    assert "Since the last message" not in context_of(env.transport.requests, 1)
    assert await case_entries(env) == []


async def test_a_case_from_another_conversation_adds_nothing(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    env = await make_env(
        app_engine, seeded_sandbox, transport=PlanTransport(text_plan("Ok."), text_plan("Two."))
    )
    other = await make_env(app_engine, seeded_sandbox, transport=PlanTransport(text_plan("Other.")))
    await other.ask("Something happened to me.")
    await open_case(
        other, conversation_id=other.conversation.id, turn_id=await first_turn_id(other)
    )
    await env.ask("Hello.")
    await env.ask("And now?")

    assert "Since the last message" not in context_of(env.transport.requests, 1)
    assert await case_entries(env) == []


async def test_a_turn_that_failed_in_between_does_not_swallow_the_line(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    transport = PlanTransport(
        text_plan("Ok."),
        lambda request, number: [ModelUnavailable("down", status_code=529)],
        text_plan("Three."),
        text_plan("Four."),
        guard_result=SENSITIVE,
    )
    env = await make_env(app_engine, seeded_sandbox, transport=transport)
    await env.ask("Hello.")
    await open_case(env, conversation_id=env.conversation.id, turn_id=await first_turn_id(env))
    await env.ask("Never mind.")  # Fails: its context is built but never stored.
    await env.ask("Again?")
    await env.ask("And?")

    requests = env.transport.requests
    assert LINE in context_of(requests, 1)
    assert LINE in context_of(requests, 2)
    assert "Since the last message" not in context_of(requests, 3)
    assert await case_entries(env) == [f"case:{(await case_ids(env))[0]}:new"]


async def case_ids(env: Env) -> list[UUID]:
    from sqlalchemy import select

    async with tenant_session(env.engine, env.ctx) as db:
        return list((await db.scalars(select(Case.id))).all())


async def test_a_card_outcome_and_an_opened_case_share_one_line(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    transport = PlanTransport(
        tool_use_plan(book()), text_plan("Ok."), text_plan("Fine."), guard_result=SENSITIVE
    )
    env = await make_env(app_engine, seeded_sandbox, transport=transport)
    await env.ask("Please book Friday off.")
    row = await only_proposal(env)
    async with acting(app_engine, env.ctx.tenant_id, env.ctx.person_id) as (db, actor):  # type: ignore[arg-type]
        await cancel(db, actor, row.id)
    await open_case(env, conversation_id=env.conversation.id, turn_id=await first_turn_id(env))
    await env.ask("Never mind.")

    context = context_of(env.transport.requests, 2)
    assert context.count("Since the last message:") == 1
    [line] = [x for x in context.splitlines() if x.startswith("Since the last message:")]
    assert line == (
        "Since the last message: the card to book PTO on Friday, October 23 was dismissed, so "
        "nothing was changed. The person opened a confidential case with HR (workplace safety). "
        "HR replies by Wednesday, October 28."
    )


def test_two_cases_and_no_card_outcome_make_one_line() -> None:
    from app.ai.case_outcomes import with_case_sentences

    one = "the person opened a confidential case with HR (pay). HR replies by Friday, October 30."
    two = one.replace("pay", "safety")

    assert with_case_sentences((), (one, two)) == (
        "Since the last message: " + one + " " + two[0].upper() + two[1:],
    )
    assert with_case_sentences(("kept",), ()) == ("kept",)
