"""The same-origin check on requests to the API: every unsafe method, and reads of `/api/`.

Plain ASGI middleware, so every endpoint is covered by default, including sandbox creation, which
has no session and so no CSRF token yet. The safe methods are GET, HEAD, OPTIONS, and TRACE.

**A request that changes data**, meaning any method that isn't safe. The check lists the methods it
lets through, not the ones it guards, so a method it has never heard of, or a safe one in
lowercase, gets the full check. A browser says where a request came from in two headers, read in
this order:

1. `Sec-Fetch-Site` (Fetch Metadata). If present, it must be `same-origin`.
2. Otherwise `Origin`, which must equal APP_ORIGIN exactly.
3. With neither, the request can't show that it came from the app, so it is refused.

A request with a body must also be JSON. That rule is defense in depth. It runs only after the
origin check has passed, it blocks a same-origin HTML form post (a form can send only form
encodings and plain text), and it still holds if the origin rules are ever loosened.

**A read of `/api/`**, meaning a safe method. Reads are not free of side effects: a read of a
person's private details writes an audit row. And the session cookie is `SameSite=Lax`, so a
browser sends it on a cross-site top-level navigation, and on any request from a sibling subdomain,
which is same-site. Another site could then make an HR partner's browser perform an audited read in
their name. So a read of `/api/` whose `Sec-Fetch-Site` is `cross-site` or `same-site` is refused.
`same-origin`, `none` (a typed URL or a bookmark), and no header at all (a script, or an old
browser) go through, and so does a read of any path outside `/api/`, so the web app can still be
opened from a link on another site. "Under `/api/`" means the path the router matches, so a root
path (`uvicorn --root-path`) doesn't hide it.

A refusal is a 403 in problem details. It carries the request ID, because the request-ID
middleware wraps this one.
"""

from starlette import status
from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.api_paths import is_api_request
from app.core.problems import problem_response
from app.modules.identity.security_log import SecurityEvent, log_security_event

# Compared exactly, so a lowercase "get" is not safe and gets the check.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})
JSON_MEDIA_TYPE = "application/json"
# What Sec-Fetch-Site says about a request from another site, or from a sibling subdomain.
OTHER_SITE = frozenset({"cross-site", "same-site"})

WRITE_REFUSED = "Requests that change data must come from the Open Door app, as JSON."
READ_REFUSED = "Requests to the API must come from the Open Door app."


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


def _read_refusal(scope: Scope, headers: Headers) -> str | None:
    """Why a read is refused, as a fixed phrase for the log, or None if it may proceed."""
    if is_api_request(scope) and headers.get("sec-fetch-site") in OTHER_SITE:
        return "a read from another site"
    return None


class SameOriginMiddleware:
    def __init__(self, app: ASGIApp, *, app_origin: str) -> None:
        self.app = app
        self.app_origin = app_origin

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        if scope["method"] in SAFE_METHODS:
            reason = _read_refusal(scope, headers)
            detail = READ_REFUSED
        else:
            reason = _refusal(headers, self.app_origin)
            detail = WRITE_REFUSED
        if reason is None:
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        log_security_event(SecurityEvent.ORIGIN_REJECTED, request, reason)
        response = problem_response(request, status.HTTP_403_FORBIDDEN, detail)
        await response(scope, receive, send)
