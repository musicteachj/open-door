"""The stream route never holds the request's database connection while it takes another, and a
turn is never left behind when the response cannot be sent."""

import asyncio
import contextlib
import time
from typing import Any
from uuid import UUID

import httpx2 as httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.ai.scripted import ScriptedTransport
from app.ai.turn import TurnRun
from app.core.config import Settings
from app.modules.assistant.sse import TurnResponse
from tests.integration.test_turn_stream_connection import (
    SICK,
    SILENT,
    RawCall,
    ask_again,
    running_app,
    turns,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.usefixtures("daily_ledger_untouched"),
]


async def test_more_concurrent_questions_than_the_pool_holds_do_not_stall_the_api(
    database_settings: Settings, created_tenant_ids: list[UUID], app_engine: AsyncEngine
) -> None:
    transport = ScriptedTransport(silence_seconds=3)
    async with running_app(database_settings, created_tenant_ids, transport) as session:
        pool = session.app.state.engine.pool
        count = pool.size() + pool._max_overflow + 1
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=session.app),
            base_url="https://testserver",
            headers={"Sec-Fetch-Site": "same-origin"},
        ) as other:
            created = await other.post("/api/v1/sandboxes", json={"persona": "mateo"})
            assert created.status_code == 201
            created_tenant_ids.append(UUID(created.json()["tenant"]["id"]))

            started = time.monotonic()
            flood = asyncio.gather(
                *(ask_again(session, SILENT) for _ in range(count)), return_exceptions=True
            )
            await asyncio.sleep(0.3)
            other_started = time.monotonic()
            visitor = await other.get("/api/v1/me")
            other_seconds = time.monotonic() - other_started
            results = await flood
            seconds = time.monotonic() - started

        codes = sorted(str(getattr(r, "status_code", type(r).__name__)) for r in results)
        rows = await turns(app_engine, session)
        open_streams = session.app.state.streams.open_count

    assert open_streams == 0  # The refused starts gave their count back.
    assert visitor.status_code == 200
    assert other_seconds < 3
    assert codes == ["200"] + ["409"] * (count - 1)
    assert seconds < 10
    assert [r.status for r in rows] == ["completed"]


async def test_a_response_that_cannot_be_sent_does_not_strand_the_turn(
    database_settings: Settings,
    created_tenant_ids: list[UUID],
    app_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with running_app(database_settings, created_tenant_ids, ScriptedTransport()) as session:

        async def broken(self: TurnResponse, scope: object, receive: object, send: object) -> None:
            raise ConnectionResetError("the response could not start")

        monkeypatch.setattr(TurnResponse, "__call__", broken)
        with pytest.raises(ConnectionResetError):
            await ask_again(session)
        monkeypatch.undo()

        rows = await turns(app_engine, session)
        open_streams = session.app.state.streams.open_count
        next_turn = await ask_again(session)

    assert [r.status for r in rows] == ["stopped"]
    assert open_streams == 0
    assert next_turn.status_code == 200


async def test_a_cancel_after_the_turn_is_added_but_before_the_response_does_not_strand_it(
    database_settings: Settings,
    created_tenant_ids: list[UUID],
    app_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """uvicorn's graceful-shutdown cancel is a plain `task.cancel()`, which no anyio shield
    blocks."""
    real_begin: Any = TurnRun.begin.__func__  # type: ignore[attr-defined]

    async def slow_begin(cls: type[TurnRun], *args: Any, **kwargs: Any) -> TurnRun:
        run: TurnRun = await real_begin(cls, *args, **kwargs)
        await asyncio.sleep(1.5)  # The row is added; a cancel lands here.
        return run

    monkeypatch.setattr(TurnRun, "begin", classmethod(slow_begin))
    async with running_app(database_settings, created_tenant_ids, ScriptedTransport()) as session:
        call = RawCall(session, SICK)
        task = asyncio.create_task(call.run())
        await asyncio.sleep(0.6)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        monkeypatch.undo()

        rows = await turns(app_engine, session)
        open_streams = session.app.state.streams.open_count
        next_turn = await ask_again(session)

    assert [r.status for r in rows] == ["stopped"]
    assert open_streams == 0
    assert next_turn.status_code == 200


async def test_the_shutdown_waits_for_a_turn_that_is_still_starting(
    database_settings: Settings,
    created_tenant_ids: list[UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A request canceled during a slow start, then shutdown at once (as uvicorn does): the drain
    must count the start, or the engine is closed under it and `asyncio.run` ends it half done."""
    real_begin: Any = TurnRun.begin.__func__  # type: ignore[attr-defined]
    start_finished = asyncio.Event()

    async def slow_begin(cls: type[TurnRun], *args: Any, **kwargs: Any) -> TurnRun:
        await asyncio.sleep(0.8)
        run: TurnRun = await real_begin(cls, *args, **kwargs)
        await asyncio.sleep(0.8)
        start_finished.set()
        return run

    finished_when_engine_closed: list[bool] = []
    holder: list[Any] = []
    real_dispose = AsyncEngine.dispose

    async def dispose(self: AsyncEngine, close: bool = True) -> None:
        if holder and self is holder[0].app.state.engine:
            finished_when_engine_closed.append(start_finished.is_set())
        await real_dispose(self, close)

    monkeypatch.setattr(TurnRun, "begin", classmethod(slow_begin))
    monkeypatch.setattr(AsyncEngine, "dispose", dispose)
    async with running_app(database_settings, created_tenant_ids, ScriptedTransport()) as session:
        holder.append(session)
        call = RawCall(session, SICK)
        task = asyncio.create_task(call.run())
        await asyncio.sleep(0.3)
        task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    assert finished_when_engine_closed == [True]
