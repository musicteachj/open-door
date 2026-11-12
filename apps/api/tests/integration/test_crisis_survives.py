"""The crisis panel survives a failed end-of-turn write (Phase 8, Stage 5).

A crisis turn's verdict used to be written only by `finish_turn`, at the very end. If that write
failed or timed out, the row stayed `running`, then read back as failed (`abandoned`) with no
verdict, and the page lost the 988 and EAP text on reload. The turn now stores the verdict in a
short transaction of its own before the crisis text goes out, and a stored crisis verdict shows the
crisis panel whatever the turn's shown status.
"""

import asyncio
import json
from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.ai import turn as turn_module
from app.ai.conversations import (
    ABANDONED_AFTER,
    conversation_cipher,
    open_turn,
    store_crisis_verdict,
)
from app.ai.fixed_texts import CRISIS_TEXT, ERROR_TEXTS, hr_contact
from app.ai.turn import Error, Escalation, TurnCompleted, TurnStarted, run_turn
from app.db.models import AiTurn
from app.db.tenancy import tenant_session
from app.modules.assistant.display import needs_hr_contact, shown, turn_out
from app.modules.assistant.schemas import TurnOut
from app.modules.sandbox.seed import SeedCompany
from tests.integration.conftest import TEST_KEYS
from tests.integration.test_console_rows_written import (
    assert_only_the_date_and_the_counts,
    console_rows,
)
from tests.integration.test_turn import (
    NOW,
    SICK,
    Env,
    _leave_the_daily_ledger_as_found,  # noqa: F401
    make_env,
    of_type,
)
from tests.integration.test_turn_proposals import _age

pytestmark = pytest.mark.integration

CRISIS = "I want to hurt myself"
CRISIS_VERDICT = {"category": "crisis", "kind": "self_harm", "injectionSuspected": False}


async def stored(owner: AsyncEngine, turn_id: UUID) -> tuple[str, Any, str | None]:
    """The row as the owner login sees it: status, verdict, and error code."""
    async with owner.connect() as connection:
        row = (
            await connection.execute(
                text("SELECT status, guard_verdict, error_code FROM ai_turns WHERE id = :id"),
                {"id": turn_id},
            )
        ).one()
    return row[0], row[1], row[2]


async def reload(env: Env) -> list[TurnOut]:
    """The conversation's turns as the page shows them after a reload (what the route builds), by
    the database's clock."""
    async with tenant_session(env.engine, env.ctx) as db:
        rows = list((await db.scalars(select(AiTurn).order_by(AiTurn.started_at, AiTurn.id))).all())
        now = (await db.execute(select(func.now()))).scalar_one()
        cipher = conversation_cipher(TEST_KEYS, env.conversation)
        shows = [shown(t, now) for t in rows]
        contacts = await hr_contact(db) if needs_hr_contact(shows) else []
        return [
            turn_out(t, open_turn(cipher, t), s, None, None, contacts, {})
            for t, s in zip(rows, shows, strict=True)
        ]


def break_the_finish(monkeypatch: pytest.MonkeyPatch) -> None:
    """The end-of-turn write hangs, and is given up on quickly."""

    async def hang(*args: Any, **kwargs: Any) -> None:
        await asyncio.sleep(3600)

    monkeypatch.setattr(turn_module, "finish_turn", hang)
    monkeypatch.setattr(turn_module, "CLEANUP_TIMEOUT", timedelta(seconds=0.3))


async def crisis_text_and_wait(env: Env) -> tuple[Escalation, float]:
    """Ask the crisis question; the escalation and how long after the start it arrived."""
    loop = asyncio.get_running_loop()
    started = loop.time()
    arrived: list[tuple[Escalation, float]] = []
    async for event in run_turn(env.deps, conversation=env.conversation, question=CRISIS, now=NOW):
        if isinstance(event, Escalation):
            arrived.append((event, loop.time() - started))
    assert len(arrived) == 1
    return arrived[0]


async def drain_detached() -> None:
    """Wait for the steps the turn stopped waiting for, so none outlives the test's loop."""
    await asyncio.gather(*list(turn_module._DETACHED), return_exceptions=True)


def assert_crisis_panel(turn: TurnOut) -> None:
    assert turn.escalation is not None
    assert (turn.escalation.kind, turn.escalation.message) == ("crisis", CRISIS_TEXT)
    assert [c.name for c in turn.escalation.hr_contact] == ["Dana Whitfield"]


async def test_the_verdict_is_stored_before_the_crisis_text_goes_out(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    env = await make_env(app_engine, seeded_sandbox)
    turn_id: UUID | None = None
    at_the_escalation: tuple[str, Any, str | None] | None = None
    async for event in run_turn(env.deps, conversation=env.conversation, question=CRISIS, now=NOW):
        if isinstance(event, TurnStarted):
            turn_id = event.turn_id
        if isinstance(event, Escalation):
            assert turn_id is not None
            at_the_escalation = await stored(owner_engine, turn_id)

    assert at_the_escalation is not None
    status, verdict, error_code = at_the_escalation
    assert (status, error_code) == ("running", None)
    assert verdict == CRISIS_VERDICT


async def test_a_finish_that_hangs_still_leaves_the_crisis_panel_on_reload(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    seeded_sandbox: SeedCompany,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    break_the_finish(monkeypatch)
    env = await make_env(app_engine, seeded_sandbox)
    events = await env.ask(CRISIS)

    assert [type(e) for e in events[-2:]] == [Escalation, Error]
    assert events[-1] == Error("internal", ERROR_TEXTS["internal"])
    escalation = events[-2]
    assert isinstance(escalation, Escalation)
    assert escalation.message == CRISIS_TEXT
    assert not of_type(events, TurnCompleted)
    turn_id = (await env.last_turn()).id
    assert (await stored(owner_engine, turn_id))[0] == "running"

    # Under the abandoned limit: still "answering", with the panel.
    [turn] = await reload(env)
    assert turn.status == "running"
    assert_crisis_panel(turn)

    # Past it: failed as abandoned, with the panel.
    await _age(owner_engine, turn_id, ABANDONED_AFTER + timedelta(minutes=1))
    [turn] = await reload(env)
    assert turn.status == "failed"
    assert turn.error is not None
    assert turn.error.message == ERROR_TEXTS["internal"]
    assert_crisis_panel(turn)

    # The next question recovers it (the end-of-turn write works again): still the panel, and the
    # recovered row's console row holds only the date and the counts.
    monkeypatch.undo()
    await env.ask(SICK)
    assert (await stored(owner_engine, turn_id))[0::2] == ("failed", "abandoned")
    crisis_turn, _ = await reload(env)
    assert crisis_turn.status == "failed"
    assert_crisis_panel(crisis_turn)
    flagged = [row for row in await console_rows(env) if row["flagged"]]
    assert len(flagged) == 1
    assert_only_the_date_and_the_counts(flagged[0])


async def test_a_verdict_write_that_fails_still_sends_the_crisis_text(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def broken(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("cannot write")

    monkeypatch.setattr(turn_module, "store_crisis_verdict", broken)
    env = await make_env(app_engine, seeded_sandbox)
    events = await env.ask(CRISIS)

    escalation = of_type(events, Escalation)
    assert [(e.kind, e.message) for e in escalation] == [("crisis", CRISIS_TEXT)]
    assert [c.name for c in escalation[0].hr_contact] == ["Dana Whitfield"]
    assert isinstance(events[-1], TurnCompleted)
    # The end-of-turn write still stores the verdict.
    assert (await env.last_turn()).guard_verdict == CRISIS_VERDICT


async def test_a_slow_verdict_write_is_not_waited_for_and_still_lands(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    seeded_sandbox: SeedCompany,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The text stops waiting at the bound, but the write is not canceled: a write that is only
    slow still lands, even when the end-of-turn write then fails."""
    real = store_crisis_verdict

    async def slow(*args: Any, **kwargs: Any) -> bool:
        await asyncio.sleep(0.8)
        return await real(*args, **kwargs)

    monkeypatch.setattr(turn_module, "store_crisis_verdict", slow)
    monkeypatch.setattr(turn_module, "CRISIS_VERDICT_TIMEOUT", timedelta(seconds=0.3))
    break_the_finish(monkeypatch)
    env = await make_env(app_engine, seeded_sandbox)
    escalation, waited = await crisis_text_and_wait(env)
    await drain_detached()

    assert waited < 0.3 + 0.35, "the text waited on the write past its bound"
    assert (escalation.kind, escalation.message) == ("crisis", CRISIS_TEXT)
    assert [c.name for c in escalation.hr_contact] == ["Dana Whitfield"]
    turn_id = (await env.last_turn()).id
    assert (await stored(owner_engine, turn_id))[:2] == ("running", CRISIS_VERDICT)
    assert_crisis_panel((await reload(env))[-1])


async def test_the_verdict_write_does_not_add_to_the_hr_lookups_wait(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both are bounded and run together, so a slow pair costs the longer, not the sum."""

    async def slow(*args: Any, **kwargs: Any) -> None:
        await asyncio.sleep(1.0)

    monkeypatch.setattr(turn_module, "store_crisis_verdict", slow)
    monkeypatch.setattr(turn_module, "hr_contact", slow)
    monkeypatch.setattr(turn_module, "CRISIS_VERDICT_TIMEOUT", timedelta(seconds=0.5))
    monkeypatch.setattr(turn_module, "HR_CONTACT_TIMEOUT", timedelta(seconds=0.5))
    env = await make_env(app_engine, seeded_sandbox)
    escalation, waited = await crisis_text_and_wait(env)
    await drain_detached()

    # One bound plus a margin, well under the two bounds' sum (1.0 s).
    assert waited < 0.5 + 0.35, "the waits added up"
    assert (escalation.kind, escalation.message, escalation.hr_contact) == (
        "crisis",
        CRISIS_TEXT,
        (),
    )


async def test_a_step_whose_cancellation_hangs_does_not_hold_the_crisis_text(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A database that stops answering holds a canceled query's cleanup (asyncpg's cancel, the
    pool's close) for as long as the network lets it. The text stops waiting at the bound and
    leaves the step to end on its own; `asyncio.timeout` would have waited for the cleanup. The HR
    lookup is the step that is canceled; the verdict write is left running (here, never ending
    within the test until it is drained)."""

    async def stubborn(*args: Any, **kwargs: Any) -> None:
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            await asyncio.sleep(1.5)  # The cleanup a silent database holds up.
            raise

    async def silent(*args: Any, **kwargs: Any) -> None:
        await asyncio.sleep(1.5)  # A write held by a silent database.

    monkeypatch.setattr(turn_module, "store_crisis_verdict", silent)
    monkeypatch.setattr(turn_module, "hr_contact", stubborn)
    monkeypatch.setattr(turn_module, "CRISIS_VERDICT_TIMEOUT", timedelta(seconds=0.3))
    monkeypatch.setattr(turn_module, "HR_CONTACT_TIMEOUT", timedelta(seconds=0.3))
    env = await make_env(app_engine, seeded_sandbox)
    escalation, waited = await crisis_text_and_wait(env)

    assert waited < 0.3 + 0.35, "the text waited on a step's cleanup"
    assert (escalation.kind, escalation.message) == ("crisis", CRISIS_TEXT)
    await drain_detached()


async def test_an_hr_lookup_cut_off_mid_statement_leaves_the_pool_healthy(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    seeded_sandbox: SeedCompany,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A real statement still running at the bound, in a step that is canceled: the text goes out
    on time, the query is canceled on the server, and the pool's connections still work."""

    async def sleeping(db: Any) -> list[Any]:
        await db.execute(text("SELECT pg_sleep(5)"))
        return []

    monkeypatch.setattr(turn_module, "hr_contact", sleeping)
    monkeypatch.setattr(turn_module, "HR_CONTACT_TIMEOUT", timedelta(seconds=0.3))
    env = await make_env(app_engine, seeded_sandbox)
    escalation, waited = await crisis_text_and_wait(env)
    await drain_detached()

    assert waited < 0.3 + 0.5
    assert (escalation.kind, escalation.message) == ("crisis", CRISIS_TEXT)
    async with owner_engine.connect() as connection:
        running: int = (
            await connection.execute(
                text(
                    "SELECT count(*) FROM pg_stat_activity"
                    " WHERE query = 'SELECT pg_sleep(5)' AND state = 'active'"
                )
            )
        ).scalar_one()
    assert running == 0
    for _ in range(5):
        async with app_engine.connect() as connection:
            assert (await connection.execute(text("SELECT 1"))).scalar_one() == 1
    # The early write and the finish stored the verdict.
    assert (await stored(owner_engine, (await env.last_turn()).id))[:2] == (
        "crisis",
        CRISIS_VERDICT,
    )


@pytest.mark.parametrize(
    ("verdict", "label"),
    [
        (None, "no verdict"),
        ({"category": "ordinary", "kind": None, "injectionSuspected": False}, "ordinary"),
        ({"category": "ordinary", "kind": "pay", "injectionSuspected": False}, "ordinary topic"),
        ({"category": "sensitive", "kind": "pay", "injectionSuspected": False}, "sensitive"),
    ],
)
async def test_an_abandoned_turn_without_a_crisis_verdict_shows_no_panel(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    seeded_sandbox: SeedCompany,
    verdict: dict[str, Any] | None,
    label: str,
) -> None:
    env = await make_env(app_engine, seeded_sandbox)
    run = await turn_module.start_turn_run(
        env.deps, conversation=env.conversation, question="Book Friday.", now=NOW
    )
    await _age(owner_engine, run.turn_id, ABANDONED_AFTER + timedelta(minutes=1))
    if verdict is not None:
        async with owner_engine.begin() as connection:
            await connection.execute(
                text("UPDATE ai_turns SET guard_verdict = CAST(:v AS jsonb) WHERE id = :id"),
                {"v": json.dumps(verdict), "id": run.turn_id},
            )

    [turn] = await reload(env)
    assert turn.status == "failed", label
    assert turn.escalation is None, label


async def test_the_stored_crisis_verdict_does_not_change_a_normal_crisis_turn(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    env = await make_env(app_engine, seeded_sandbox)
    events = await env.ask(CRISIS)

    assert isinstance(events[-1], TurnCompleted)
    turn = await env.last_turn()
    assert (turn.status, turn.guard_verdict) == ("crisis", CRISIS_VERDICT)
    [shown_turn] = await reload(env)
    assert shown_turn.status == "crisis"
    assert_crisis_panel(shown_turn)
