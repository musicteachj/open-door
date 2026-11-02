"""The eval runner's cost report and daily cap against the real database (Phase 7, stage 2).

A billed call that kept its reservation counts as spent now, and another sandbox's spend during a
run does not count against the run. Nothing is paid for: the model is the scripted one."""

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.ai.scripted import ScriptedTransport
from app.ai.transport import ModelUnavailable
from app.core.config import Settings
from tests.integration.test_assistant_eval_runner_db import (
    _leave_the_daily_ledger_as_found,  # noqa: F401 (an autouse fixture)
    args,
    make_env,
    run,
    tiny_sets,
)

pytestmark = pytest.mark.integration


class CutAfterBilling:
    """The scripted model, except that every answer stream is cut by a transient error after it
    started: the call may have been billed, its cost is unknown, and the turn keeps its
    reservation."""

    def __init__(self) -> None:
        self.inner = ScriptedTransport()

    async def stream(self, request: Any) -> Any:
        raise ModelUnavailable("the connection dropped")
        yield  # pragma: no cover (makes this a generator)

    async def classify(self, request: Any) -> Any:
        return await self.inner.classify(request)


async def test_a_billed_call_that_kept_its_reservation_is_spent_now_not_recorded(
    tmp_path: Path,
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    database_settings: Settings,
) -> None:
    env = make_env(
        tmp_path,
        app_engine,
        owner_engine,
        database_settings,
        transport_factory=lambda _settings: CutAfterBilling(),
    )
    out_json = tmp_path / "board.json"

    await run.run_cli(args(tmp_path, "--yes", "--json", str(out_json)), env=env)

    cost = json.loads(out_json.read_text(encoding="utf-8"))["cost_usd"]
    # The reservation stayed in the ledger. The call went to the real transport, so it was paid for
    # now: nothing was reused from a recording.
    assert Decimal(cost["assistant"]) > 0
    assert Decimal(cost["recorded"]["assistant"]) == 0


class SpendsElsewhereOnce(ScriptedTransport):
    """The scripted model, until its first answer call: then another sandbox spends a lot today."""

    def __init__(self, owner_engine: AsyncEngine, amount: str) -> None:
        super().__init__()
        self.owner_engine = owner_engine
        self.amount = amount
        self.done = False

    async def stream(self, request: Any) -> Any:
        if not self.done:
            self.done = True
            async with self.owner_engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO ai_spend_daily (kind, amount_usd) VALUES ('reserve', :amount)"
                    ),
                    {"amount": self.amount},
                )
        async for event in super().stream(request):
            yield event


async def test_another_sandboxes_spend_during_the_run_does_not_stop_it(
    tmp_path: Path,
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    database_settings: Settings,
) -> None:
    # 2.90 is past the run's whole $2 cap, and arrives after the run has started.
    env = make_env(
        tmp_path,
        app_engine,
        owner_engine,
        database_settings,
        transport_factory=lambda _settings: SpendsElsewhereOnce(owner_engine, "2.90"),
    )
    out_json = tmp_path / "board.json"

    await run.run_cli(args(tmp_path, "--yes", "--json", str(out_json)), env=env)

    board = json.loads(out_json.read_text(encoding="utf-8"))
    assert board["partial"] is False
    assert board["items_run"] == 4


async def test_the_runs_own_spend_still_counts_against_the_daily_cap(
    tmp_path: Path,
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    database_settings: Settings,
) -> None:
    # Another sandbox's spend arrives mid-run, and the run's cap is smaller than what it spends.
    env = make_env(
        tmp_path,
        app_engine,
        owner_engine,
        database_settings,
        sets=tiny_sets(cap="0.0001"),
        transport_factory=lambda _settings: SpendsElsewhereOnce(owner_engine, "2.90"),
    )
    out_json = tmp_path / "board.json"

    await run.run_cli(args(tmp_path, "--yes", "--json", str(out_json)), env=env)

    board = json.loads(out_json.read_text(encoding="utf-8"))
    assert board["partial"] is True
    assert board["items_run"] < 4


class OnlyTheDaysTotal:
    """The owner engine, except that a connection refuses any query but the day's total: the
    sandbox's own spend must be read as the sandbox (row-level security), not as the owner."""

    def __init__(self, inner: AsyncEngine) -> None:
        self.inner = inner

    def connect(self) -> Any:
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def guarded() -> Any:
            from app.ai.budget import DAY_SUM

            async with self.inner.connect() as connection:

                class Guarded:
                    async def scalar(self, statement: Any, *rest: Any, **kw: Any) -> Any:
                        assert statement is DAY_SUM, "the owner read more than the day's total"
                        return await connection.scalar(statement, *rest, **kw)

                yield Guarded()

        return guarded()


async def test_the_other_spend_is_todays_total_less_what_the_sandbox_holds_dated_today(
    owner_engine: AsyncEngine, app_engine: AsyncEngine
) -> None:
    from functools import partial
    from types import SimpleNamespace

    from app.ai.budget import DAY_SUM

    cap = run.SpendCap(Decimal("2.00"))
    stub = SimpleNamespace(
        owner_engine=OnlyTheDaysTotal(owner_engine), app_engine=app_engine, cap=cap
    )
    stub._other_spend_today_usd = partial(run.EvalRun._other_spend_today_usd, stub)
    async with run.fixed_sandbox(app_engine, owner_engine, None):
        async with owner_engine.begin() as connection:
            insert = text(
                "INSERT INTO ai_spend (tenant_id, purpose, kind, amount_usd, created_at)"
                " VALUES (:tenant, 'case_screen', 'reserve', :amount,"
                " now() - make_interval(days => :ago))"
            )
            # Spent before midnight (yesterday), so not in today's total; and 0.05 today, which is.
            await connection.execute(insert, {"tenant": run.TENANT_ID, "amount": 5, "ago": 1})
            await connection.execute(insert, {"tenant": run.TENANT_ID, "amount": "0.05", "ago": 0})
            for amount in ("0.20", "0.05"):  # another sandbox's 0.20, and this run's 0.05
                await connection.execute(
                    text("INSERT INTO ai_spend_daily (kind, amount_usd) VALUES ('reserve', :a)"),
                    {"a": amount},
                )
            day_total = Decimal((await connection.execute(DAY_SUM)).scalar_one())
        # The sandbox's whole ledger (5.05) is more than the day's total, as after midnight.
        cap.start_segment()
        cap.observe(Decimal("5.05"))

        other = await run.EvalRun._other_spend_today_usd(stub)
        caps = await run.EvalRun._caps(stub)

    assert other == day_total - Decimal("0.05")
    assert other >= Decimal("0.20")
    assert caps.daily_usd >= caps.sandbox_usd


async def test_the_board_is_written_before_the_comparison_is_built(
    tmp_path: Path,
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    database_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    low = tmp_path / "low"
    low.mkdir()
    low_json = low / "board.json"
    await run.run_cli(
        args(low, "--yes", "--json", str(low_json)),
        env=make_env(low, app_engine, owner_engine, database_settings),
    )

    def broken(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("the comparison broke")

    monkeypatch.setattr(run.scoreboard, "compare", broken)
    medium = tmp_path / "medium"
    medium.mkdir()
    boards = tmp_path / "scoreboards"

    code = await run.run_cli(
        args(
            medium, "--yes", "--json", str(medium / "20261101T120000Z-full.json"),
            "--compare", str(low_json), "--boards-dir", str(boards), name="full",
        ),
        env=make_env(
            medium, app_engine, owner_engine, database_settings,
            committed_fixtures_dir=medium / "fixtures",
        ),
    )  # fmt: skip

    assert code == 2
    assert [p.name for p in boards.iterdir()] == ["20261101T120000Z-full.json"]
