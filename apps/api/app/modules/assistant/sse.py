"""The turn's server-sent-event stream: the encoder, the body that relays a started turn, and the
response that writes it with a time limit on every write.

The turn (`app/ai/turn.py`) decides everything a person sees; this only relays its events. Three
things make that safe to leave running:

- **The heartbeat.** After `heartbeat_seconds` without an event the body sends a `: keep-alive`
  comment, so a proxy that cuts a quiet connection does not cut a turn that is only thinking. The
  wait never cancels the turn's pending read (see `TurnStream`).
- **Stop is a disconnect.** When the client goes, Starlette cancels the body. The turn's own
  shielded cleanup saves the partial answer as `stopped`, settles what was spent, and frees the
  conversation for the next question. `TurnStream.aclose` makes sure that runs on every way out,
  including when the body was never started.
- **Bounded writes.** A client that stops reading blocks `send`, and a blocked write would hold a
  live turn open past the abandoned-turn rule (10 minutes). Each write has a time limit, and a
  write that stalls is treated as a disconnect.
"""

import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncGenerator
from typing import Any, Protocol

import anyio
from starlette.responses import StreamingResponse
from starlette.types import Message, Send

from app.ai.fixed_texts import ERROR_TEXTS
from app.ai.text import error_name
from app.ai.turn import CLEANUP_TIMEOUT, Error, TurnEvent

logger = logging.getLogger(__name__)

KEEP_ALIVE = b": keep-alive\n\n"

# The longest one write may block. A healthy browser drains a few hundred bytes at once (uvicorn
# only blocks a write past a 64 KiB buffer), and the heartbeat is every 15 seconds, so a client
# that cannot take a write in 30 seconds has stopped reading. It is far below the abandoned-turn
# rule (10 minutes), so a stalled write can never carry a live turn past it.
WRITE_TIMEOUT_SECONDS = 30.0

# Closing the stream cancels the pending read and waits for the turn to save itself. The turn's own
# bound for that is `CLEANUP_TIMEOUT`; this adds a second for the wake-up around it.
CLOSE_TIMEOUT_SECONDS = CLEANUP_TIMEOUT.total_seconds() + 1.0


def encode_event(event: TurnEvent) -> bytes:
    """One event as the wire sends it: `event:` and `data:` lines and a blank line.

    The JSON is compact and UTF-8. `json.dumps` escapes every newline inside a string, so the data
    is always one line and cannot end the event early.
    """
    data = json.dumps(event.to_json(), separators=(",", ":"), ensure_ascii=False)
    # The turn loop replaces a lone surrogate in model text with U+FFFD before anything is sent.
    # `errors="replace"` is the last defense: if one still got here (UTF-8 cannot encode it), it
    # becomes "?" and does not end the stream.
    return f"event: {event.name}\ndata: {data}\n\n".encode(errors="replace")


class StreamTracker:
    """Counts the turn streams still open, so the app's shutdown can wait for them to save their
    turns before it closes the database engine (uvicorn does not wait for a canceled request)."""

    def __init__(self) -> None:
        self._open = 0

    @property
    def open_count(self) -> int:
        return self._open

    def opened(self) -> None:
        self._open += 1

    def closed(self) -> None:
        self._open -= 1

    async def wait_until_idle(self, timeout_seconds: float) -> bool:
        """Wait for every stream to close. Returns False if some were still open at the limit.

        It polls instead of using an event, so it does not belong to any one event loop."""
        loop = asyncio.get_running_loop()
        # Measured by the loop's clock: a sleep can run long under load, and the shutdown budget
        # (graceful timeout plus this) has to hold.
        deadline = loop.time() + timeout_seconds
        while self._open > 0:
            if loop.time() >= deadline:
                return False
            await asyncio.sleep(0.05)
        return True


class StartedTurn(Protocol):
    """What the stream needs of a started turn (`TurnRun` is one)."""

    def events(self) -> AsyncGenerator[TurnEvent]: ...

    async def finish(self) -> None: ...


class TurnStream:
    """The body of the response: a turn's events as bytes, and a way to stop it for good.

    It is an iterator with an `aclose`, not an async generator, because a generator that was never
    started does not run its `finally` when it is closed, and a turn that was started (its row is
    `running`) and then never read would hold the conversation for ten minutes.

    **One pending read.** The turn's generator is read by one task at a time, and the heartbeat
    waits on that task with a timeout instead of wrapping the read in `asyncio.wait_for`: a timeout
    would cancel the read and break the generator in the middle of a model call.

    **Stopping.** The read task runs inside an `anyio` cancel scope, and `aclose` cancels the
    scope. That is shielded cancellation: the turn's cleanup (`TurnRun.finish`) runs in a shielded
    scope of its own, so it completes. A plain `task.cancel()` would not be shielded, and could cut
    the cleanup that saves the turn.
    """

    def __init__(
        self,
        run: StartedTurn,
        *,
        heartbeat_seconds: float,
        tracker: StreamTracker | None = None,
        counted: bool = False,
    ) -> None:
        self._run = run
        self._events = run.events()
        self._heartbeat = float(heartbeat_seconds) if heartbeat_seconds > 0 else None
        self._tracker = tracker
        self._pending: asyncio.Task[TurnEvent | None] | None = None
        self._scope: anyio.CancelScope | None = None
        self._started = False
        self._ended = False
        self._closed = False
        # `counted`: the caller already opened the tracker for this stream's start, and this takes
        # over that count, so the shutdown's drain also waits for a turn that is still starting.
        if tracker is not None and not counted:
            tracker.opened()

    def __aiter__(self) -> "TurnStream":
        return self

    async def __anext__(self) -> bytes:
        if self._ended or self._closed:
            raise StopAsyncIteration
        if self._pending is None:
            self._scope = anyio.CancelScope()
            self._pending = asyncio.ensure_future(self._read(self._scope))
        pending = self._pending
        done, _ = await asyncio.wait({pending}, timeout=self._heartbeat)
        if not done:
            return KEEP_ALIVE
        if self._pending is pending:
            self._pending = None
        try:
            # None when the turn ended, or when `aclose` canceled this read from another task.
            event = pending.result()
        except Exception as error:
            # Something the turn did not handle, such as an error building its closing events. The
            # person gets the plain internal error, and the log gets only the error's type.
            logger.error("A turn stream's read failed (%s)", error_name(error))
            self._ended = True
            return encode_event(Error("internal", ERROR_TEXTS["internal"]))
        if event is None:
            self._ended = True
            raise StopAsyncIteration
        return encode_event(event)

    async def _read(self, scope: anyio.CancelScope) -> TurnEvent | None:
        """The turn's next event, or None once it has ended or the read was canceled."""
        self._started = True
        with scope:
            try:
                return await self._events.__anext__()
            except StopAsyncIteration:
                return None
        # The scope was canceled. The cancellation went through the turn's generator, which saved
        # the turn in its `finally`, so it has ended.
        return None

    async def aclose(self) -> None:
        """Stop the turn if it is still running and wait, within a limit, for it to save itself.

        Safe to call more than once, and from a canceled task: the wait is shielded."""
        if self._closed:
            return
        self._closed = True
        try:
            with anyio.CancelScope(shield=True), anyio.move_on_after(CLOSE_TIMEOUT_SECONDS):
                await self._stop()
        finally:
            if self._tracker is not None:
                self._tracker.closed()

    async def _stop(self) -> None:
        pending, self._pending = self._pending, None
        if pending is not None:
            if self._scope is not None:
                self._scope.cancel()
            await asyncio.wait({pending})
            with contextlib.suppress(asyncio.CancelledError):
                pending.exception()  # Taken, so asyncio does not warn that nobody retrieved it.
        # A generator suspended at a `yield` is stopped here; one that ended or was canceled is
        # already closed and this does nothing.
        await self._events.aclose()
        if not self._started:
            # Never read, so its `finally` has not run and will not: finish the turn here.
            await self._run.finish()


class WriteStalled(Exception):  # noqa: N818
    """A write did not complete within the time limit."""


class TurnResponse(StreamingResponse):
    """A streaming response whose every write has a time limit, and that always closes its body.

    A write that stalls is a client that has stopped reading: the response stops, the body closes
    (which stops the turn and saves it as `stopped`), and the connection is dropped by the server
    when the app returns without finishing the response.
    """

    body_iterator: Any  # A TurnStream.

    def __init__(self, stream: TurnStream) -> None:
        super().__init__(
            stream,
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-store, no-transform",
                "X-Accel-Buffering": "no",
                # A proxy that compresses by content type (nginx with `gzip_types
                # text/event-stream`, CloudFront) holds events back to compress them, and nginx
                # ignores `no-transform` on a direct request. It leaves a response alone that
                # already names an encoding, and `identity` means none.
                "Content-Encoding": "identity",
            },
        )
        self._stream = stream

    async def _write(self, send: Send, message: Message) -> None:
        try:
            async with asyncio.timeout(WRITE_TIMEOUT_SECONDS):
                await send(message)
        except TimeoutError:
            raise WriteStalled from None

    async def stream_response(self, send: Send) -> None:
        try:
            await self._write(
                send,
                {
                    "type": "http.response.start",
                    "status": self.status_code,
                    "headers": self.raw_headers,
                },
            )
            async for chunk in self._stream:
                await self._write(
                    send, {"type": "http.response.body", "body": chunk, "more_body": True}
                )
            await self._write(send, {"type": "http.response.body", "body": b"", "more_body": False})
        except WriteStalled:
            # No content in the log: only that it happened.
            logger.warning("A client stopped reading a turn stream; closing it")
        finally:
            await self._stream.aclose()
