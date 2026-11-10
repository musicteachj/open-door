"""Cap request bodies at 64 KiB, so a few large requests can't exhaust a task's memory.

Plain ASGI middleware, so it never buffers anything. Two checks:

1. A `Content-Length` over the cap is refused with 413 before the app reads a byte.
2. Every body is also counted as the app reads it, so a chunked body (no `Content-Length`) or one
   whose header understates its size is cut off at the cap. The 413 is sent at that moment, the
   app's read ends as a disconnect, and whatever the app then sends or raises is dropped. If the
   app has already started its own response, there is nothing left to refuse: the read just ends
   as a disconnect, because a second response start would break the connection's framing.

The largest body any route accepts is about 32 KB (8,000 four-byte characters of case words, as
JSON), so the cap leaves room. The 413 is a problem-details response like every other refusal.
"""

from starlette import status
from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.problems import problem_response

MAX_BODY_BYTES = 64 * 1024
TOO_LARGE = "The request is too large."


class BodyLimitMiddleware:
    def __init__(self, app: ASGIApp, *, max_bytes: int = MAX_BODY_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def _refuse(self, scope: Scope, receive: Receive, send: Send) -> None:
        response = problem_response(
            Request(scope),
            status.HTTP_413_CONTENT_TOO_LARGE,
            TOO_LARGE,
            headers={"Connection": "close"},
        )
        await response(scope, receive, send)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        declared = Headers(scope=scope).get("content-length")
        if declared is not None and declared.isdigit() and int(declared) > self.max_bytes:
            await self._refuse(scope, receive, send)
            return

        received = 0
        refused = False
        started = False

        async def counting_receive() -> Message:
            nonlocal received, refused
            if refused:
                return {"type": "http.disconnect"}
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    refused = True
                    if not started:
                        await self._refuse(scope, receive, send)
                    return {"type": "http.disconnect"}
            return message

        async def guarded_send(message: Message) -> None:
            nonlocal started
            if not refused:
                if message["type"] == "http.response.start":
                    started = True
                await send(message)

        try:
            await self.app(scope, counting_receive, guarded_send)
        except Exception:
            # After the 413 the app saw a disconnect, and it fails however it fails to read one.
            # That is the cut working, not an error to log.
            if not refused:
                raise
