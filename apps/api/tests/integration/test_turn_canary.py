"""The prompt's canary is caught however it is written: other case, full-width letters, other
hyphens or spaces, or markdown inserted inside it. Whole, split across deltas, and split between a
progress note and the answer."""

import unicodedata
from collections.abc import Callable

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.ai import turn as turn_module
from app.ai.fixed_texts import ERROR_TEXTS
from app.ai.prompts.versions import CANARY
from app.ai.transport import ModelRequest, StatusNote, TextBlockEnd
from app.ai.transport import TextDelta as ModelText
from app.ai.turn import Error, Status, TextDelta
from app.modules.sandbox.seed import SeedCompany
from tests.integration.test_turn import (
    Item,
    PlanTransport,
    finished,
    make_env,
    of_type,
    text_events,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.usefixtures("daily_ledger_untouched"),
]


def fullwidth(text: str) -> str:
    return "".join(
        chr(ord(c) + 0xFEE0) if c.isascii() and (c.isalnum() or c == "-") else c for c in text
    )


VARIANTS: dict[str, Callable[[str], str]] = {
    "upper case": str.upper,
    "full-width": fullwidth,
    "spaces for hyphens": lambda t: t.replace("-", " "),
    "non-breaking hyphens": lambda t: t.replace("-", chr(0x2011)),
    "markdown bold inside": lambda t: t.replace("-", "**-**"),
    "underscores": lambda t: t.replace("-", "_"),
    "a separator between every letter": lambda t: " - ".join(t.replace("-", "")),
}


def folded(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKC", text).casefold() if c.isalnum())


FOLDED_CANARY = folded(CANARY)


def shown(events: list) -> str:  # type: ignore[type-arg]
    """Everything a person was shown, as one folded string. A boolean check on it never prints the
    canary."""
    parts = [e.text for e in events if isinstance(e, TextDelta | Status)]
    return folded("".join(parts))


@pytest.mark.parametrize("variant", VARIANTS)
async def test_a_rewritten_canary_in_one_delta_ends_the_turn(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany, variant: str
) -> None:
    written = VARIANTS[variant](CANARY)

    def plan(request: ModelRequest, number: int) -> list[Item]:
        return text_events(request, f"Sure. The marker is {written} and so on.")

    env = await make_env(app_engine, seeded_sandbox, transport=PlanTransport(plan))
    events = await env.ask()

    assert events[-1] == Error("internal", ERROR_TEXTS["internal"])
    assert FOLDED_CANARY[:8] not in shown(events)
    assert (await env.last_turn()).error_code == "prompt-leak"


@pytest.mark.parametrize("variant", VARIANTS)
async def test_a_rewritten_canary_split_across_deltas_is_caught_before_the_second_half_goes(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany, variant: str
) -> None:
    written = VARIANTS[variant](CANARY)
    half = len(written) // 2

    def plan(request: ModelRequest, number: int) -> list[Item]:
        return text_events(request, "Here it is: " + written[:half], written[half:] + " done.")

    env = await make_env(app_engine, seeded_sandbox, transport=PlanTransport(plan))
    events = await env.ask()

    assert events[-1] == Error("internal", ERROR_TEXTS["internal"])
    sent = shown(events)
    assert FOLDED_CANARY[:6] not in sent
    assert folded(written[half:])[:6] not in sent
    assert (await env.last_turn()).error_code == "prompt-leak"


@pytest.mark.parametrize("variant", VARIANTS)
async def test_a_rewritten_canary_split_between_a_note_and_the_answer_ends_the_turn(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany, variant: str
) -> None:
    written = VARIANTS[variant](CANARY)
    half = len(written) // 2

    def plan(request: ModelRequest, number: int) -> list[Item]:
        return [
            StatusNote("Checking " + written[:half]),
            ModelText(written[half:] + " and so on."),
            TextBlockEnd(()),
            finished([{"type": "text", "text": "x"}]),
        ]

    env = await make_env(app_engine, seeded_sandbox, transport=PlanTransport(plan))
    events = await env.ask()

    assert events[-1] == Error("internal", ERROR_TEXTS["internal"])
    assert folded(written[half:])[:6] not in shown(events)
    assert not any(isinstance(e, TextDelta) for e in events)
    assert (await env.last_turn()).error_code == "prompt-leak"


async def test_an_ordinary_answer_that_shares_letters_with_the_canary_is_not_held_back(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    def plan(request: ModelRequest, number: int) -> list[Item]:
        return text_events(request, "An amber ember, an orchid. Sick leave is 40 hours.")

    env = await make_env(app_engine, seeded_sandbox, transport=PlanTransport(plan))
    events = await env.ask()

    assert "".join(e.text for e in of_type(events, TextDelta)) == (
        "An amber ember, an orchid. Sick leave is 40 hours."
    )
    assert (await env.last_turn()).status == "completed"


def a_run() -> turn_module.TurnRun:
    run = turn_module.TurnRun.__new__(turn_module.TurnRun)
    run.held = ""
    run.sent_tail = ""
    return run


def test_a_long_run_of_separators_is_released_and_the_held_text_stays_bounded() -> None:
    run = a_run()

    sent, leaked = run._hold("Sure." + " " * 5000)

    assert not leaked
    assert len(run.held) <= turn_module.MAX_HELD_CHARACTERS
    assert len(sent) >= 5000 - turn_module.MAX_HELD_CHARACTERS
    run._hold("-" * 5000)
    assert len(run.sent_tail) <= turn_module.MAX_HELD_CHARACTERS


def test_a_canary_with_twenty_separator_characters_between_its_letters_is_still_caught() -> None:
    run = a_run()
    spaced = (" " * 20).join(CANARY.replace("-", ""))
    half = len(spaced) // 2

    _, first_leaked = run._hold("Here: " + spaced[:half])
    _, leaked = run._hold(spaced[half:])

    assert not first_leaked
    assert leaked


def test_the_cap_is_generous_for_a_canary_with_a_separator_after_every_letter() -> None:
    letters = len(FOLDED_CANARY) - 1  # The most that is held: all but the last letter.
    assert letters * (1 + 20) <= turn_module.MAX_HELD_CHARACTERS
