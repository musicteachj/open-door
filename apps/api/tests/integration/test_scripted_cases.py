"""The scripted model's case scenarios through the real turn: the real case tools run, so a person
sees only their own cases and only HR sees the queue, and only the model's judgment is scripted.

The seeded company has four cases for people who aren't personas: Keisha (pay) and Chloe
(harassment) are new, Aaliyah's (safety) is in review, and Lucia's (medical) is closed. Priya,
Marcus, and Mateo have none. Dana is HR. Nothing here reads a person's words: no tool returns them.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.ai.turn import Escalation, Proposal, TextDelta, ToolFinished, TurnEvent
from app.modules.sandbox.seed import SeedCompany
from tests.integration.test_turn import (
    _leave_the_daily_ledger_as_found,  # noqa: F401
    make_env,
    of_type,
)

pytestmark = pytest.mark.integration

SEEDED_WORDS = ("paychecks were each about four hours short", "ladder in the stockroom is cracked")


def said(events: list[TurnEvent]) -> str:
    return "".join(event.text for event in of_type(events, TextDelta))


async def test_priya_asks_for_the_status_of_her_case_and_has_none(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    env = await make_env(app_engine, seeded_sandbox, persona="priya")

    events = await env.ask("What's the status of my case?")

    assert [f.ok for f in of_type(events, ToolFinished)] == [True]
    assert said(events) == "You have no cases."
    assert of_type(events, Proposal) == []


async def test_dana_asks_for_the_open_cases_and_gets_the_queue_without_any_words(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    env = await make_env(app_engine, seeded_sandbox, persona="dana")

    events = await env.ask("Show me the open cases")

    assert [f.ok for f in of_type(events, ToolFinished)] == [True]
    words = said(events)
    # Keisha's and Chloe's are new and Aaliyah's is in review; Lucia's is closed.
    assert words.startswith("There are 3 open cases. First in the queue: ")
    assert "Lucia" not in words
    for fragment in SEEDED_WORDS:
        assert fragment not in words


async def test_dana_asks_which_cases_need_a_reply_soon(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    env = await make_env(app_engine, seeded_sandbox, persona="dana")

    events = await env.ask("Which cases need a reply soon?")

    assert [f.ok for f in of_type(events, ToolFinished)] == [True]
    # Whether any is due depends on the sandbox's date; either way it quotes only the tool.
    assert said(events).startswith(("No case needs a reply soon.", "1 case needs", "2 cases need"))


@pytest.mark.parametrize("persona", ["marcus", "priya", "mateo"])
async def test_anyone_else_asking_for_the_queue_gets_the_fixed_error_and_no_hint(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany, persona: str
) -> None:
    env = await make_env(app_engine, seeded_sandbox, persona=persona)

    events = await env.ask("Show me the open cases")

    assert [f.ok for f in of_type(events, ToolFinished)] == [False]
    assert said(events) == "That didn't work: Only the HR team can see cases."
    for name in ("Keisha", "Chloe", "Aaliyah", "Lucia"):
        assert name not in said(events)


async def test_the_demos_age_comment_makes_the_sensitive_panel_offer_a_case(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    env = await make_env(app_engine, seeded_sandbox, persona="priya")

    events = await env.ask("My manager keeps making comments about my age.")

    (panel,) = of_type(events, Escalation)
    assert panel.kind == "sensitive"
    assert panel.offer_case is True
