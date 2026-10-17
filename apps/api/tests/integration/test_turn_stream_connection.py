"""The turn stream and its connection: a client that disconnects, a write that stalls, two requests
at once, and a shutdown with a stream open.

httpx's ASGI transport buffers a whole body and cannot disconnect, so these tests call the ASGI app
directly: they build the request, play the client's side of `receive`, and control `send`.
"""

import asyncio
import contextlib
import json
from collections import Counter
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import anyio
import httpx2 as httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.ai.scripted import ScriptedTransport
from app.core.config import Settings
from app.db.models import AiSpend, AiTurn
from app.db.tenancy import TenantContext, tenant_session
from app.main import create_app
from app.modules.assistant import sse
from app.modules.identity.cookies import CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE

pytestmark = [
    pytest.mark.integration,
    pytest.mark.usefixtures("daily_ledger_untouched"),
]

BASE = "/api/v1/assistant"
LONG = "scripted long answer"
SILENT = "scripted silence"
SICK = "How much paid sick leave do I get?"


@dataclass
class Session:
    app: FastAPI
    client: httpx.AsyncClient
    tenant_id: UUID
    person_id: UUID
    conversation_id: str
    session_token: str
    csrf_token: str


@asynccontextmanager
async def running_app(
    settings: Settings, created_tenant_ids: list[UUID], transport: ScriptedTransport
) -> AsyncIterator[Session]:
    """The app with its lifespan running, and a signed-in person with a new conversation."""
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        app.state.transport = transport
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="https://testserver",
            headers={"Sec-Fetch-Site": "same-origin"},
        ) as client:
            created = await client.post("/api/v1/sandboxes", json={"persona": "priya"})
            assert created.status_code == 201, created.text
            sandbox = created.json()
            tenant_id = UUID(sandbox["tenant"]["id"])
            created_tenant_ids.append(tenant_id)
            csrf = client.cookies[CSRF_COOKIE]
            conversation = await client.post(f"{BASE}/conversations", headers={CSRF_HEADER: csrf})
            assert conversation.status_code == 201, conversation.text
            yield Session(
                app,
                client,
                tenant_id,
                UUID(sandbox["me"]["id"]),
                conversation.json()["id"],
                client.cookies[SESSION_COOKIE],
                csrf,
            )


@dataclass
class RawCall:
    """One POST to the turn route made straight to the ASGI app.

    `received` collects the response messages. `disconnect` is the client closing the connection.
    `block_after` makes `send` stall forever once that many messages were accepted.
    """

    session: Session
    question: str
    block_after: int | None = None
    received: list[dict[str, Any]] = field(default_factory=list)
    disconnect: asyncio.Event = field(default_factory=asyncio.Event)
    on_message: Callable[[dict[str, Any]], None] | None = None

    def chunks(self) -> list[str]:
        return [m["body"].decode() for m in self.received if m["type"] == "http.response.body"]

    def text(self) -> str:
        return "".join(self.chunks())

    async def run(self) -> None:
        s = self.session
        raw = json.dumps({"question": self.question}).encode()
        path = f"{BASE}/conversations/{s.conversation_id}/turns"
        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "https",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "root_path": "",
            "headers": [
                (b"host", b"testserver"),
                (b"content-type", b"application/json"),
                (b"content-length", str(len(raw)).encode()),
                (b"sec-fetch-site", b"same-origin"),
                (b"cookie", f"{SESSION_COOKIE}={s.session_token}".encode()),
                (CSRF_HEADER.lower().encode(), s.csrf_token.encode()),
            ],
            "client": ("127.0.0.1", 50000),
            "server": ("testserver", 443),
            "state": {},
        }
        sent_body = False

        async def receive() -> dict[str, Any]:
            nonlocal sent_body
            if not sent_body:
                sent_body = True
                return {"type": "http.request", "body": raw, "more_body": False}
            await self.disconnect.wait()
            return {"type": "http.disconnect"}

        async def send(message: dict[str, Any]) -> None:
            if self.block_after is not None and len(self.received) >= self.block_after:
                await asyncio.Event().wait()
            self.received.append(message)
            if self.on_message is not None:
                self.on_message(message)

        await s.app(scope, receive, send)  # type: ignore[arg-type]


async def wait_for(condition: Callable[[], bool], seconds: float = 5.0) -> None:
    with anyio.fail_after(seconds):
        while not condition():  # noqa: ASYNC110 (polls a plain predicate)
            await asyncio.sleep(0.02)


async def turns(engine: AsyncEngine, session: Session) -> list[AiTurn]:
    ctx = TenantContext(session.tenant_id, session.person_id)
    async with tenant_session(engine, ctx) as db:
        return list((await db.scalars(select(AiTurn).order_by(AiTurn.started_at))).all())


async def spend_kinds(engine: AsyncEngine, session: Session) -> Counter[str]:
    ctx = TenantContext(session.tenant_id, session.person_id)
    async with tenant_session(engine, ctx) as db:
        return Counter((await db.scalars(select(AiSpend.kind))).all())


async def ask_again(session: Session, question: str = SICK) -> httpx.Response:
    return await session.client.post(
        f"{BASE}/conversations/{session.conversation_id}/turns",
        json={"question": question},
        headers={CSRF_HEADER: session.csrf_token},
    )


def paced() -> ScriptedTransport:
    """A long answer written slowly enough to stop in the middle of it."""
    return ScriptedTransport(delta_delay_seconds=0.02)


# --- A second request while a turn runs -----------------------------------------------------


async def test_a_second_question_while_the_first_streams_is_409_turn_running(
    database_settings: Settings, created_tenant_ids: list[UUID], app_engine: AsyncEngine
) -> None:
    async with running_app(
        database_settings, created_tenant_ids, ScriptedTransport(silence_seconds=1.5)
    ) as session:
        first = RawCall(session, SILENT)
        task = asyncio.create_task(first.run())
        await wait_for(lambda: "event: turn.started" in first.text())

        second = await ask_again(session)
        await task

    assert second.status_code == 409
    assert second.headers["content-type"] == "application/problem+json"
    assert second.json()["type"] == "turn-running"
    rows = await turns(app_engine, session)
    assert [r.status for r in rows] == [
        "completed"
    ]  # The second wrote nothing, and the first lived.
    assert "event: turn.completed" in first.text()


# --- Stop is a disconnect -------------------------------------------------------------------


async def test_a_disconnect_mid_answer_saves_the_partial_answer_as_stopped_and_frees_the_next_turn(
    database_settings: Settings, created_tenant_ids: list[UUID], app_engine: AsyncEngine
) -> None:
    async with running_app(database_settings, created_tenant_ids, ScriptedTransport()) as session:
        full = await ask_again(session, LONG)
        full_answer = "".join(
            json.loads(line.removeprefix("data: "))["text"]
            for block in full.text.split("\n\n")
            for line in block.split("\n")
            if line.startswith("data: ") and "event: text.delta" in block
        )
        before = await spend_kinds(app_engine, session)
        session.app.state.transport = paced()  # Now slow, so there is a middle to stop in.

        call = RawCall(session, LONG)
        task = asyncio.create_task(call.run())
        await wait_for(lambda: call.text().count("event: text.delta") >= 3)
        call.disconnect.set()
        with anyio.fail_after(10):
            await task

        rows = await turns(app_engine, session)
        stopped = rows[-1]
        after = await spend_kinds(app_engine, session)
        # The conversation is free: the next question starts at once.
        next_turn = await ask_again(session)

    assert [r.status for r in rows] == ["completed", "stopped"]
    assert stopped.answer_text
    assert full_answer.startswith(stopped.answer_text)
    assert len(stopped.answer_text) < len(full_answer)
    assert stopped.ended_at is not None
    # The guard call and the search call finished and were settled. The stopped answer call keeps
    # its reservation: its output tokens are known only at the stream's end.
    assert after["reserve"] - before["reserve"] == 3
    assert after["settle"] - before["settle"] == 2
    assert next_turn.status_code == 200
    assert "event: turn.completed" in next_turn.text


async def test_a_disconnect_before_anything_is_read_still_stops_the_turn(
    database_settings: Settings, created_tenant_ids: list[UUID], app_engine: AsyncEngine
) -> None:
    async with running_app(database_settings, created_tenant_ids, paced()) as session:
        call = RawCall(session, LONG)
        call.disconnect.set()  # Gone before the response starts.
        with anyio.fail_after(10):
            await call.run()

        rows = await turns(app_engine, session)
        next_turn = await ask_again(session)

    assert [r.status for r in rows] == ["stopped"]
    assert next_turn.status_code == 200


# --- Bounded writes -------------------------------------------------------------------------


async def test_a_write_that_stalls_ends_the_stream_and_the_turn_is_saved_stopped(
    database_settings: Settings,
    created_tenant_ids: list[UUID],
    app_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sse, "WRITE_TIMEOUT_SECONDS", 0.3)
    async with running_app(database_settings, created_tenant_ids, paced()) as session:
        # The response start and three events go through; the next write never completes.
        call = RawCall(session, LONG, block_after=4)
        with anyio.fail_after(10):
            await call.run()

        rows = await turns(app_engine, session)
        next_turn = await ask_again(session)

    assert len(call.received) == 4
    assert [r.status for r in rows] == ["stopped"]
    assert rows[0].ended_at is not None
    assert next_turn.status_code == 200


# --- Shutdown -------------------------------------------------------------------------------


async def test_a_stream_canceled_at_shutdown_saves_its_turn_before_the_engine_is_closed(
    database_settings: Settings,
    created_tenant_ids: list[UUID],
    owner_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """uvicorn cancels the open requests when its graceful-shutdown timeout passes, and then runs
    the lifespan's shutdown without waiting for them. The lifespan waits for the streams."""
    streams_open_when_engine_closed: list[int] = []
    session_holder: list[Session] = []
    real_dispose = AsyncEngine.dispose

    async def dispose(self: AsyncEngine, close: bool = True) -> None:
        if session_holder and self is session_holder[0].app.state.engine:
            streams_open_when_engine_closed.append(session_holder[0].app.state.streams.open_count)
        await real_dispose(self, close)

    monkeypatch.setattr(AsyncEngine, "dispose", dispose)
    async with running_app(database_settings, created_tenant_ids, paced()) as session:
        session_holder.append(session)
        call = RawCall(session, LONG)
        task = asyncio.create_task(call.run())
        await wait_for(lambda: call.text().count("event: text.delta") >= 3)
        task.cancel()  # What uvicorn does to the request task. Then the app shuts down.
    with contextlib.suppress(asyncio.CancelledError):
        await task
    assert streams_open_when_engine_closed == [0]
    rows = await turns_as_owner(owner_engine, session_holder[0])
    assert [r.status for r in rows] == ["stopped"]
    assert rows[0].answer_text


async def turns_as_owner(engine: AsyncEngine, session: Session) -> list[AiTurn]:
    async with engine.connect() as connection:
        result = await connection.execute(
            select(AiTurn.status, AiTurn.answer_text).where(
                AiTurn.conversation_id == UUID(session.conversation_id)
            )
        )
        return [AiTurn(status=status, answer_text=answer) for status, answer in result]
