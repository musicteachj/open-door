"""The turn's two new timings (Phase 7): `guard_ms` and `first_text_ms`, on the console row only.

The turn reads time in one place (`turn._clock`), so a fake clock that the fake model moves makes
every figure exact. The steps below are binary fractions of a second, so the milliseconds are exact
too. `ai_turns` keeps its own `first_event_ms`, which counts the first status line.
"""

from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.ai import budget as budget_module
from app.ai import turn as turn_module
from app.ai.budget import Caps
from app.ai.transport import (
    GuardRequest,
    GuardResult,
    ModelEvent,
    ModelRequest,
    StatusNote,
    TextBlockEnd,
)
from app.ai.transport import TextDelta as ModelText
from app.modules.sandbox.seed import SeedCompany
from tests.integration.test_console_rows_written import console_rows, only_row
from tests.integration.test_turn import (
    Item,
    PlanTransport,
    _leave_the_daily_ledger_as_found,  # noqa: F401
    finished,
    make_env,
    search_plan,
    text_plan,
)

pytestmark = pytest.mark.integration

GUARD_SECONDS = 0.125
STATUS_SECONDS = 0.25
TEXT_SECONDS = 0.5
TOOL_SECONDS = 0.0625


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class SlowModel:
    """Wraps a model and moves the fake clock the way a slow one would: the guard takes a while,
    a status line comes after a pause, and so does the first word."""

    def __init__(
        self,
        inner: Any,
        clock: FakeClock,
        *,
        guard: float = 0.0,
        status: float = 0.0,
        text: float = 0.0,
    ) -> None:
        self.inner, self.clock = inner, clock
        self.guard, self.status, self.text = guard, status, text

    async def classify(self, request: GuardRequest) -> GuardResult:
        self.clock.advance(self.guard)
        result: GuardResult = await self.inner.classify(request)
        return result

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        async for event in self.inner.stream(request):
            if isinstance(event, StatusNote):
                self.clock.advance(self.status)
            elif isinstance(event, ModelText):
                self.clock.advance(self.text)
            yield event


def noted_plan(request: ModelRequest, number: int) -> list[Item]:
    answer = "You get 40 hours."
    return [
        StatusNote("Looking it up"),
        ModelText(answer),
        TextBlockEnd(()),
        finished([{"type": "text", "text": answer}]),
    ]


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> FakeClock:
    fake = FakeClock()
    monkeypatch.setattr(turn_module, "_clock", fake)
    return fake


async def test_guard_ms_covers_the_one_safety_check_call(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany, clock: FakeClock
) -> None:
    model = SlowModel(PlanTransport(text_plan()), clock, guard=GUARD_SECONDS)
    env = await make_env(app_engine, seeded_sandbox, transport=model)
    await env.ask()

    assert (await only_row(env))["guard_ms"] == 125


async def test_guard_ms_does_not_count_the_ledger_write_that_reserves_for_the_guard(
    app_engine: AsyncEngine,
    seeded_sandbox: SeedCompany,
    clock: FakeClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_reserve = budget_module.reserve

    async def slow_reserve(*args: Any, **kwargs: Any) -> Any:
        # Each reservation (the guard's, then the model's) takes a second on the fake clock.
        clock.advance(1.0)
        return await real_reserve(*args, **kwargs)

    monkeypatch.setattr("app.ai.turn.reserve", slow_reserve)
    model = SlowModel(PlanTransport(text_plan()), clock, guard=GUARD_SECONDS)
    env = await make_env(app_engine, seeded_sandbox, transport=model)
    await env.ask()

    assert (await only_row(env))["guard_ms"] == 125


async def test_guard_ms_is_measured_on_a_flagged_row_too(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany, clock: FakeClock
) -> None:
    model = SlowModel(PlanTransport(text_plan()), clock, guard=GUARD_SECONDS)
    env = await make_env(app_engine, seeded_sandbox, transport=model)
    await env.ask("I want to hurt myself")

    row = await only_row(env)
    assert row["flagged"] is True
    assert row["guard_ms"] == 125


async def test_guard_ms_is_null_when_the_budget_refuses_before_the_guard(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany, clock: FakeClock
) -> None:
    model = SlowModel(PlanTransport(text_plan()), clock, guard=GUARD_SECONDS)
    env = await make_env(
        app_engine, seeded_sandbox, transport=model, caps=Caps(Decimal("0.0001"), Decimal(1000))
    )
    await env.ask()

    row = await only_row(env)
    assert row["outcome"] == "budget"
    assert row["guard_ms"] is None


async def test_guard_ms_is_measured_when_the_guard_fails(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany, clock: FakeClock
) -> None:
    from app.ai.scripted import ScriptedTransport

    model = SlowModel(ScriptedTransport(), clock, guard=GUARD_SECONDS)
    env = await make_env(app_engine, seeded_sandbox, transport=model)
    await env.ask("scripted guard failure")

    row = await only_row(env)
    assert row["outcome"] == "guard_unavailable"
    assert row["guard_ms"] == 125


async def test_first_text_ms_is_the_first_word_not_the_status_line(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany, clock: FakeClock
) -> None:
    model = SlowModel(
        PlanTransport(noted_plan),
        clock,
        guard=GUARD_SECONDS,
        status=STATUS_SECONDS,
        text=TEXT_SECONDS,
    )
    env = await make_env(app_engine, seeded_sandbox, transport=model)
    await env.ask()

    row = await only_row(env)
    turn = await env.last_turn()
    # The guard (125), then the status line (250), then the first word (500).
    assert turn.first_event_ms == 375, "ai_turns counts the first status line, as before"
    assert row["first_text_ms"] == 875
    assert row["guard_ms"] == 125


def blank_then_text_plan(request: ModelRequest, number: int) -> list[Item]:
    answer = "You get 40 hours."
    return [
        # Blank text past the 512 characters the turn holds back (blanks count as nothing in its
        # canary check), so part of it is shown at once.
        ModelText(" \n" * 300),
        ModelText(answer),
        TextBlockEnd(()),
        finished([{"type": "text", "text": answer}]),
    ]


async def test_first_text_ms_is_the_first_non_blank_text(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany, clock: FakeClock
) -> None:
    model = SlowModel(
        PlanTransport(blank_then_text_plan), clock, guard=GUARD_SECONDS, text=TEXT_SECONDS
    )
    env = await make_env(app_engine, seeded_sandbox, transport=model)
    await env.ask()

    # The guard (125), the blank text (500, shown at once), then the real words (500, held back
    # until the block ends and shown then). An empty delta never reaches the turn's text step: the
    # canary hold sends nothing for it, so a long blank one is the case that can.
    assert (await only_row(env))["first_text_ms"] == 1125


async def test_a_tool_start_is_not_text(
    app_engine: AsyncEngine,
    seeded_sandbox: SeedCompany,
    clock: FakeClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.ai.tools.base import ToolOutcome

    async def slow_tool(name: str, raw: Any, ctx: Any) -> ToolOutcome:
        clock.advance(TOOL_SECONDS)
        return ToolOutcome([{"type": "text", "text": "ok"}], summary="ok")

    monkeypatch.setattr(turn_module, "run_tool", slow_tool)
    model = SlowModel(
        PlanTransport(search_plan(), text_plan()), clock, guard=GUARD_SECONDS, text=TEXT_SECONDS
    )
    env = await make_env(app_engine, seeded_sandbox, transport=model)
    await env.ask()

    row = await only_row(env)
    turn = await env.last_turn()
    # The tool started (visible) right after the guard; the first word came after the tool ran and
    # the text pause: 125 + 62 + 500, truncated.
    assert turn.first_event_ms == 125
    assert row["first_text_ms"] == 687
    assert row["tools"][0]["durationMs"] == 62


async def test_first_text_ms_is_null_for_a_turn_with_no_text(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany, clock: FakeClock
) -> None:
    crisis = await make_env(
        app_engine,
        seeded_sandbox,
        persona="priya",
        transport=SlowModel(PlanTransport(text_plan()), clock),
    )
    await crisis.ask("I want to hurt myself")
    refused = await make_env(app_engine, seeded_sandbox, persona="mateo")
    await refused.ask("scripted safety refusal")

    rows = await console_rows(crisis)
    assert [row["first_text_ms"] for row in rows] == [None, None]


async def test_the_new_timings_are_not_columns_of_the_turn(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany, clock: FakeClock
) -> None:
    from app.db.models import AiTurn

    env = await make_env(app_engine, seeded_sandbox)
    await env.ask()

    columns = {column.key for column in AiTurn.__table__.columns}
    assert not columns & {"guard_ms", "first_text_ms"}
    assert "first_event_ms" in columns
