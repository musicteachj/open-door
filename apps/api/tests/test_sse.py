"""The turn stream's encoder, body, and response, against fake turns (no database)."""

import asyncio
import contextlib
import gc
from collections.abc import AsyncGenerator, MutableMapping
from typing import Any
from uuid import UUID

import anyio
import pytest

from app.ai.fixed_texts import ERROR_TEXTS
from app.ai.turn import Error, Status, TextDelta, TurnEvent, TurnStarted
from app.modules.assistant import sse
from app.modules.assistant.sse import (
    KEEP_ALIVE,
    StreamTracker,
    TurnResponse,
    TurnStream,
    encode_event,
)

TURN = UUID("11111111-1111-1111-1111-111111111111")


async def quick(run: "FakeRun") -> AsyncGenerator[TurnEvent]:
    yield TurnStarted(TURN)
    yield TextDelta("hi")


class FakeRun:
    """A started turn whose events come from `script`, an async generator function."""

    def __init__(self, script: Any = None) -> None:
        self.script = script or quick
        self.finished = 0
        self.generator_finished = False
        self.generator_started = False
        self.generator_canceled = False
        self.saved = False

    def events(self) -> AsyncGenerator[TurnEvent]:
        return self._wrapped()

    async def _wrapped(self) -> AsyncGenerator[TurnEvent]:
        self.generator_started = True
        try:
            async for event in self.script(self):
                yield event
        except asyncio.CancelledError:
            self.generator_canceled = True
            raise
        finally:
            # The turn's own cleanup: shielded, so a cancel scope can't cut it short.
            with anyio.CancelScope(shield=True):
                await asyncio.sleep(0.05)
                self.saved = True
            self.generator_finished = True

    async def finish(self) -> None:
        self.finished += 1


async def collect(stream: TurnStream) -> list[bytes]:
    return [chunk async for chunk in stream]


# --- The encoder ----------------------------------------------------------------------------


def test_an_event_is_two_lines_and_a_blank_line() -> None:
    assert encode_event(TurnStarted(TURN)) == (
        b'event: turn.started\ndata: {"turnId":"11111111-1111-1111-1111-111111111111"}\n\n'
    )


def test_the_json_is_compact_utf8_and_a_newline_in_text_cannot_end_the_event() -> None:
    encoded = encode_event(TextDelta('café "x"\nnext\r\n' + chr(0x2028)))

    assert encoded.startswith(b"event: text.delta\ndata: ")
    assert encoded.endswith(b"\n\n")
    assert encoded.count(b"\n") == 3  # The two lines and the blank line: nothing inside.
    assert b"\r" not in encoded
    assert "café".encode() in encoded  # UTF-8, not é.
    assert b": " not in encoded.split(b"data: ", 1)[1]  # Compact separators.


# --- The body -------------------------------------------------------------------------------


async def test_the_body_relays_every_event_in_order_and_ends() -> None:
    run = FakeRun()

    chunks = await collect(TurnStream(run, heartbeat_seconds=0))

    assert [c.split(b"\n")[0] for c in chunks] == [b"event: turn.started", b"event: text.delta"]
    assert run.generator_finished


async def slow(run: FakeRun) -> AsyncGenerator[TurnEvent]:
    yield TurnStarted(TURN)
    await asyncio.sleep(0.35)
    yield Status("done")


async def test_a_quiet_turn_gets_keep_alive_comments_and_its_read_is_never_canceled() -> None:
    run = FakeRun(slow)

    chunks = await collect(TurnStream(run, heartbeat_seconds=0.1))

    assert chunks[0].startswith(b"event: turn.started")
    assert chunks[-1].startswith(b"event: status")
    comments = [c for c in chunks if c == KEEP_ALIVE]
    assert len(comments) >= 2
    # The pending read survived every heartbeat: the generator ran to its end untouched.
    assert run.generator_canceled is False
    assert run.generator_finished


async def test_with_the_heartbeat_off_no_comment_is_sent() -> None:
    run = FakeRun(slow)

    chunks = await collect(TurnStream(run, heartbeat_seconds=0))

    assert KEEP_ALIVE not in chunks
    assert len(chunks) == 2


async def forever(run: FakeRun) -> AsyncGenerator[TurnEvent]:
    yield TurnStarted(TURN)
    await asyncio.sleep(60)
    yield Status("never")  # pragma: no cover


async def test_closing_a_stream_waiting_on_the_turn_stops_the_turn_and_lets_it_save() -> None:
    run = FakeRun(forever)
    tracker = StreamTracker()
    stream = TurnStream(run, heartbeat_seconds=0, tracker=tracker)
    assert await stream.__anext__() is not None  # turn.started
    waiting = asyncio.ensure_future(stream.__anext__())
    await asyncio.sleep(0.05)
    assert tracker.open_count == 1

    await stream.aclose()

    # The generator was stopped in the middle of its wait, and its shielded cleanup completed.
    assert run.generator_canceled
    assert run.saved
    assert run.generator_finished
    assert tracker.open_count == 0
    with pytest.raises(StopAsyncIteration):
        await waiting


async def test_closing_while_the_turn_is_saving_itself_does_not_cut_the_save() -> None:
    """The turn ends with a shielded save and then sends its closing events. A close that lands in
    the middle of the save must wait for it, so the cancel has to be a scope's, not a task's."""

    async def saving(run: FakeRun) -> AsyncGenerator[TurnEvent]:
        yield TurnStarted(TURN)
        with anyio.CancelScope(shield=True):
            await asyncio.sleep(0.3)
            run.saved = True
        yield Status("closing")

    run = FakeRun(saving)
    stream = TurnStream(run, heartbeat_seconds=0)
    await stream.__anext__()
    waiting = asyncio.ensure_future(stream.__anext__())
    await asyncio.sleep(0.1)  # Now inside the shielded save.

    await stream.aclose()

    assert run.saved
    with contextlib.suppress(StopAsyncIteration):
        await waiting


async def test_closing_a_stream_suspended_between_events_closes_the_generator() -> None:
    run = FakeRun(forever)
    stream = TurnStream(run, heartbeat_seconds=0)
    await stream.__anext__()  # turn.started; the generator is now suspended at its yield.

    await stream.aclose()

    assert run.saved
    assert run.generator_finished
    assert run.finished == 0  # It was read, so the generator's own cleanup was the save.


async def test_closing_a_stream_that_was_never_read_finishes_the_turn_itself() -> None:
    run = FakeRun()
    tracker = StreamTracker()
    stream = TurnStream(run, heartbeat_seconds=0, tracker=tracker)

    await stream.aclose()

    assert run.finished == 1
    assert run.generator_started is False
    assert tracker.open_count == 0


async def test_closing_twice_changes_nothing() -> None:
    run = FakeRun()
    tracker = StreamTracker()
    stream = TurnStream(run, heartbeat_seconds=0, tracker=tracker)
    await stream.aclose()

    await stream.aclose()

    assert (run.finished, tracker.open_count) == (1, 0)


async def test_a_body_canceled_by_a_scope_still_stops_the_turn_through_its_close() -> None:
    """Starlette cancels the body when the client goes. The close, in the `finally`, is shielded."""
    run = FakeRun(forever)
    stream = TurnStream(run, heartbeat_seconds=0)

    async def body() -> None:
        try:
            async for _ in stream:
                pass
        finally:
            await stream.aclose()

    async with anyio.create_task_group() as group:
        group.start_soon(body)
        await asyncio.sleep(0.1)
        group.cancel_scope.cancel()

    assert run.saved
    assert run.generator_finished


async def test_an_error_in_the_turn_becomes_an_internal_error_event_and_ends_the_stream(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def broken(run: FakeRun) -> AsyncGenerator[TurnEvent]:
        yield TurnStarted(TURN)
        raise RuntimeError("boom with a secret answer")

    stream = TurnStream(FakeRun(broken), heartbeat_seconds=0)
    await stream.__anext__()

    chunk = await stream.__anext__()

    assert chunk == encode_event(Error("internal", ERROR_TEXTS["internal"]))
    with pytest.raises(StopAsyncIteration):
        await stream.__anext__()
    await stream.aclose()
    # Only the error's type is logged, never its message.
    assert "RuntimeError" in caplog.text
    assert "secret answer" not in caplog.text


def test_a_lone_surrogate_in_model_output_is_replaced_not_fatal() -> None:
    encoded = encode_event(TextDelta("a\ud800b"))

    assert encoded == b'event: text.delta\ndata: {"text":"a?b"}\n\n'


async def test_closing_takes_the_exception_of_a_read_that_failed_unseen(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A read that fails while the body is being canceled is never collected by `__anext__`."""

    async def broken(run: FakeRun) -> AsyncGenerator[TurnEvent]:
        yield TurnStarted(TURN)
        await asyncio.sleep(0.05)
        raise RuntimeError("late")

    stream = TurnStream(FakeRun(broken), heartbeat_seconds=0)
    await stream.__anext__()
    stream._scope = anyio.CancelScope()
    stream._pending = asyncio.ensure_future(stream._read(stream._scope))
    await asyncio.sleep(0.2)  # The read has failed and no one has collected it.

    await stream.aclose()
    gc.collect()

    assert "never retrieved" not in caplog.text


# --- The response ---------------------------------------------------------------------------


class Sink:
    """An ASGI `send` that records messages, and can block."""

    def __init__(self, block_after: int | None = None) -> None:
        self.messages: list[MutableMapping[str, Any]] = []
        self.block_after = block_after

    async def __call__(self, message: MutableMapping[str, Any]) -> None:
        if self.block_after is not None and len(self.messages) >= self.block_after:
            await asyncio.Event().wait()  # Never returns: a client that stopped reading.
        self.messages.append(message)


def scope() -> dict[str, Any]:
    return {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"}}


async def never_receive() -> dict[str, Any]:
    await asyncio.Event().wait()
    return {}  # pragma: no cover


async def test_the_response_has_the_event_stream_headers_and_no_compression() -> None:
    response = TurnResponse(TurnStream(FakeRun(), heartbeat_seconds=0))

    headers = dict(response.headers)
    assert headers["content-type"] == "text/event-stream; charset=utf-8"
    assert headers["cache-control"] == "no-store, no-transform"
    assert headers["x-accel-buffering"] == "no"
    # A proxy that compresses by content type skips a response that already names an encoding.
    assert headers["content-encoding"] == "identity"


async def test_the_response_writes_the_start_each_event_and_the_end() -> None:
    sink = Sink()
    response = TurnResponse(TurnStream(FakeRun(), heartbeat_seconds=0))

    await response(scope(), never_receive, sink)

    types = [m["type"] for m in sink.messages]
    assert types == ["http.response.start"] + ["http.response.body"] * 3
    assert sink.messages[-1] == {"type": "http.response.body", "body": b"", "more_body": False}
    assert sink.messages[1]["body"].startswith(b"event: turn.started")


async def test_a_write_that_stalls_ends_the_stream_and_stops_the_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sse, "WRITE_TIMEOUT_SECONDS", 0.2)
    run = FakeRun(forever)
    tracker = StreamTracker()
    sink = Sink(block_after=2)  # The start and one event go through; the next write stalls.
    response = TurnResponse(TurnStream(run, heartbeat_seconds=0, tracker=tracker))

    async def send_status_then_stall() -> None:
        await response(scope(), never_receive, sink)

    # `forever` yields one event and then waits 60 s; make the second write the stalled one by
    # giving the turn a second event straight away.
    async def two_events(fake: FakeRun) -> AsyncGenerator[TurnEvent]:
        yield TurnStarted(TURN)
        yield Status("second")
        await asyncio.sleep(60)

    run.script = two_events
    with anyio.fail_after(5):
        await send_status_then_stall()

    assert len(sink.messages) == 2
    assert run.saved
    assert run.generator_finished
    assert tracker.open_count == 0


async def test_a_client_that_disconnects_stops_the_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    run = FakeRun(forever)
    sink = Sink()
    response = TurnResponse(TurnStream(run, heartbeat_seconds=0))
    disconnect_after = 0.2

    async def receive() -> dict[str, Any]:
        await asyncio.sleep(disconnect_after)
        return {"type": "http.disconnect"}

    with anyio.fail_after(5):
        await response(scope(), receive, sink)

    assert run.saved
    assert run.generator_finished


# --- The tracker ----------------------------------------------------------------------------


async def test_the_tracker_waits_until_every_stream_has_closed() -> None:
    tracker = StreamTracker()
    tracker.opened()
    asyncio.get_running_loop().call_later(0.15, tracker.closed)

    assert await tracker.wait_until_idle(2.0) is True
    assert tracker.open_count == 0


async def test_the_tracker_gives_up_at_its_limit() -> None:
    tracker = StreamTracker()
    tracker.opened()

    assert await tracker.wait_until_idle(0.1) is False


async def test_the_tracker_measures_its_limit_by_the_clock_not_by_its_sleeps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Under load a sleep runs long; the wait must still end at its limit."""
    real_sleep = asyncio.sleep

    async def slow_sleep(seconds: float) -> None:
        await real_sleep(0.3)  # Each 0.05 s sleep takes 0.3 s.

    monkeypatch.setattr(asyncio, "sleep", slow_sleep)
    tracker = StreamTracker()
    tracker.opened()
    loop = asyncio.get_running_loop()
    started = loop.time()

    assert await tracker.wait_until_idle(0.5) is False

    assert loop.time() - started < 0.5 + 0.35  # One sleep past the limit at most.
