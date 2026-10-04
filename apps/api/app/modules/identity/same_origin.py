"""The same-origin check on every request except the safe ones: GET, HEAD, OPTIONS, and TRACE.

Plain ASGI middleware, so every endpoint is covered by default, including sandbox creation, which
has no session and so no CSRF token yet. The check lists the methods it lets through, not the ones
it guards, so a method it has never heard of, or a safe one in lowercase, gets the full check. A
browser says where a request came from in two headers, read in this order:

1. `Sec-Fetch-Site` (Fetch Metadata). If present, it must be `same-origin`.
2. Otherwise `Origin`, which must equal APP_ORIGIN exactly.
3. With neither, the request can't show that it came from the app, so it is refused.

A request with a body must also be JSON. That rule is defense in depth. It runs only after the
origin check has passed, it blocks a same-origin HTML form post (a form can send only form
encodings and plain text), and it still holds if the origin rules are ever loosened.

A refusal is a 403 in problem details. It carries the request ID, because the request-ID
middleware wraps this one.
"""

from starlette import status
from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.problems import problem_response
from app.modules.identity.security_log import SecurityEvent, log_security_event

# Compared exactly, so a lowercase "get" is not safe and gets the check.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})
JSON_MEDIA_TYPE = "application/json"


def _refusal(headers: Headers, app_origin: str) -> str | None:
    """Why the request is refused, as a fixed phrase for the log, or None if it may proceed."""
    fetch_site = headers.get("sec-fetch-site")
    if fetch_site is not None:
        if fetch_site != "same-origin":
            return "Sec-Fetch-Site is not same-origin"
    elif "origin" not in headers:
        return "neither Sec-Fetch-Site nor Origin is present"
    elif headers["origin"] != app_origin:
        return "Origin is not the app's origin"
    has_body = headers.get("content-length", "0") != "0" or "transfer-encoding" in headers
    media_type = headers.get("content-type", "").split(";")[0].strip().lower()
    if has_body and media_type != JSON_MEDIA_TYPE:
        return "the body is not JSON"
    return None


class SameOriginMiddleware:
    def __init__(self, app: ASGIApp, *, app_origin: str) -> None:
        self.app = app
        self.app_origin = app_origin

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] in SAFE_METHODS:
            await self.app(scope, receive, send)
            return
        reason = _refusal(Headers(scope=scope), self.app_origin)
        if reason is None:
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        log_security_event(SecurityEvent.ORIGIN_REJECTED, request, reason)
        response = problem_response(
            request,
            status.HTTP_403_FORBIDDEN,
            "Requests that change data must come from the Open Door app, as JSON.",
        )
        await response(scope, receive, send)
