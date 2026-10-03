"""Give every request an ID, echo it to the client, and make it available to logs and errors."""

import re
import uuid
from contextvars import ContextVar

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,128}")

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


class RequestIdMiddleware:
    """Pure ASGI middleware, so it never buffers a streamed response.

    A well-formed incoming X-Request-ID is reused, which lets a caller correlate its own logs with
    ours. Anything else is replaced with a fresh ID, so a client cannot inject arbitrary text into
    the logs.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = Headers(scope=scope).get(REQUEST_ID_HEADER)
        if incoming is not None and _VALID_REQUEST_ID.fullmatch(incoming):
            request_id = incoming
        else:
            request_id = uuid.uuid4().hex

        # Error handlers run outside this middleware, after the context variable is reset, so
        # the ID also goes on the request state where they can read it.
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                # The ASGI spec makes "headers" optional, so make sure the key exists first.
                message.setdefault("headers", [])
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        token = request_id_var.set(request_id)
        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            request_id_var.reset(token)
