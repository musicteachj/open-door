"""The scripted model's time-off scenarios through the real turn: the real tools, engine, proposals,
and cards run, and only the model's judgment is scripted.

Priya Raman asks the first four (book, sick, balance, cancel), and Marcus Bell the next three
(waiting, approve, deny). "Now" is Thursday 2026-10-15 in Oakland. Zara Bautista has a pending PTO
request for October 27 and 28 that waits for Marcus.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.ai.proposals import confirm
from app.ai.turn import (
    Escalation,
    Proposal,
    TextDelta,
    ToolFinished,
    ToolStarted,
    TurnCompleted,
    TurnEvent,
)
from app.db.models import AiProposal
from app.db.tenancy import tenant_session
from app.modules.sandbox.seed import SeedCompany
from tests.integration.test_timeoff_service import acting
from tests.integration.test_turn import (
    NOW,
    Env,
    _leave_the_daily_ledger_as_found,  # noqa: F401
    make_env,
    of_type,
)

pytestmark = pytest.mark.integration


def said(events: list[TurnEvent]) -> str:
    return "".join(event.text for event in of_type(events, TextDelta))


async def stored(env: Env) -> list[AiProposal]:
    async with tenant_session(env.engine, env.ctx) as db:
        query = select(AiProposal).order_by(AiProposal.created_at, AiProposal.id)
        return list((await db.scalars(query)).all())


async def confirm_latest(env: Env) -> None:
    (*_, row) = await stored(env)
    async with acting(env.engine, env.ctx.tenant_id, env.ctx.person_id) as (db, actor):  # type: ignore[arg-type]
        await confirm(db, actor, row.id, None, NOW)


async def test_book_next_friday_makes_a_pto_card_for_the_friday_of_next_week(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    env = await make_env(app_engine, seeded_sandbox, persona="priya")
    events = await env.ask("Book next Friday off")

    assert isinstance(events[-1], TurnCompleted)
    (event,) = of_type(events, Proposal)
    assert event.proposal.action == "timeoff.request"
    data = event.to_json()
    assert (data["card"]["type"], data["card"]["startDate"]) == ("pto", "2026-10-23")
    assert said(events).startswith("I've prepared a card to book PTO for Friday, October 23: ")
    assert said(events).endswith("Nothing is booked until you confirm.")
    (row,) = await stored(env)
    assert (row.status, row.id) == ("pending", event.proposal.id)
    # The tool saw the same events a person would: started, finished, then the card.
    kinds = [type(e) for e in events]
    at = kinds.index(Proposal)
    assert kinds[at - 2 : at + 1] == [ToolStarted, ToolFinished, Proposal]


async def test_the_booked_card_can_be_confirmed_after_the_turn(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    env = await make_env(app_engine, seeded_sandbox, persona="priya")
    await env.ask("Book next Friday off")
    await confirm_latest(env)

    (row,) = await stored(env)
    assert row.status == "executed"


async def test_im_sick_tomorrow_makes_a_sick_card_for_tomorrow(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    env = await make_env(app_engine, seeded_sandbox, persona="priya")
    events = await env.ask("I'm sick tomorrow")

    (event,) = of_type(events, Proposal)
    data = event.to_json()
    assert (data["card"]["type"], data["card"]["startDate"]) == ("sick", "2026-10-16")
    assert said(events).startswith(
        "I've prepared a card to record sick time for Friday, October 16"
    )
    assert said(events).endswith("Nothing is recorded until you confirm.")


async def test_whats_my_balance_reads_the_balance_and_makes_no_card(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    env = await make_env(app_engine, seeded_sandbox, persona="priya")
    events = await env.ask("What's my balance?")

    assert of_type(events, Proposal) == []
    assert [f.ok for f in of_type(events, ToolFinished)] == [True]
    assert " of PTO available" in said(events)
    assert await stored(env) == []


async def test_cancel_my_request_makes_a_cancel_card_for_a_request_that_can_still_be_canceled(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    env = await make_env(app_engine, seeded_sandbox, persona="priya")
    await env.ask("Book next Friday off")
    await confirm_latest(env)
    events = await env.ask("Cancel my request")

    (event,) = of_type(events, Proposal)
    data = event.to_json()
    assert data["action"] == "timeoff.cancel"
    assert data["card"]["startDate"] == "2026-10-23"
    assert [e.ok for e in of_type(events, ToolFinished)] == [True, True]
    assert said(events) == (
        "I've prepared a card to cancel your request for Friday, October 23. "
        "Nothing is canceled until you confirm."
    )


async def test_cancel_my_request_with_nothing_to_cancel_says_so(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    env = await make_env(app_engine, seeded_sandbox, persona="mateo")
    events = await env.ask("Cancel my request")

    assert of_type(events, Proposal) == []
    assert said(events) == "You have no requests that can be canceled."


async def test_anything_waiting_on_me_names_zaras_request_for_marcus(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    env = await make_env(app_engine, seeded_sandbox, persona="marcus")
    events = await env.ask("Anything waiting on me?")

    assert of_type(events, Proposal) == []
    assert said(events).startswith(
        "The first request waiting for you is from Zara Bautista, for Tuesday, October 27 to "
        "Wednesday, October 28"
    )


@pytest.mark.parametrize(("phrase", "decision"), [("Approve it", "approve"), ("Deny it", "deny")])
async def test_approve_and_deny_make_a_decision_card_for_the_first_waiting_request(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany, phrase: str, decision: str
) -> None:
    env = await make_env(app_engine, seeded_sandbox, persona="marcus")
    events = await env.ask(phrase)

    (event,) = of_type(events, Proposal)
    data = event.to_json()
    assert data["action"] == "timeoff.decide"
    assert data["card"]["decision"] == decision
    assert data["card"]["requester"]["name"] == "Zara Bautista"
    assert [e.ok for e in of_type(events, ToolFinished)] == [True, True]
    assert said(events) == (
        f"I've prepared a card to {decision} Zara Bautista's request for Tuesday, October 27 to "
        "Wednesday, October 28. Nothing is decided until you confirm."
    )
    (row,) = await stored(env)
    assert row.status == "pending"


async def test_an_employee_asking_to_approve_gets_nothing_waiting(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    env = await make_env(app_engine, seeded_sandbox, persona="mateo")
    events = await env.ask("Approve it")

    assert of_type(events, Proposal) == []
    assert said(events) == "Nothing is waiting for your decision, so there is nothing to approve."


async def test_a_sensitive_message_can_still_get_a_card_and_the_hr_panel_follows(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    env = await make_env(app_engine, seeded_sandbox, persona="priya")
    events = await env.ask("A coworker harassed me, so book next Friday off")

    kinds = [type(e) for e in events]
    assert kinds.index(Proposal) < kinds.index(TextDelta) < kinds.index(Escalation)
    assert kinds.index(Escalation) < kinds.index(TurnCompleted)
    (row,) = await stored(env)
    assert row.status == "pending"


async def test_a_following_turn_still_works_while_a_card_is_pending(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    env = await make_env(app_engine, seeded_sandbox, persona="priya")
    await env.ask("Book next Friday off")
    events = await env.ask("What's my balance?")

    assert isinstance(events[-1], TurnCompleted)
    assert " of PTO available" in said(events)
