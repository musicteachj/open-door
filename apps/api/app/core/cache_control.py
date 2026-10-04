"""Keep API responses out of shared caches: `Cache-Control: no-store` on everything under /api/.

A response such as `/me` depends on the session cookie. A CDN or proxy that forwards cookies to the
API but leaves them out of its cache key could otherwise serve one visitor's response to another.
"""

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

API_PREFIX = "/api/"
CACHE_CONTROL_HEADER = "Cache-Control"
NO_STORE = "no-store"


def is_api_path(path: str) -> bool:
    return path.startswith(API_PREFIX)


class NoStoreMiddleware:
    """Pure ASGI middleware, so it never buffers a streamed response.

    It only adds the header to the `http.response.start` message, and only when the route didn't
    set a `Cache-Control` of its own.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not is_api_path(scope["path"]):
            await self.app(scope, receive, send)
            return

        async def send_with_no_store(message: Message) -> None:
            if message["type"] == "http.response.start":
                # The ASGI spec makes "headers" optional, so make sure the key exists first.
                message.setdefault("headers", [])
                MutableHeaders(scope=message).setdefault(CACHE_CONTROL_HEADER, NO_STORE)
            await send(message)

        await self.app(scope, receive, send_with_no_store)
