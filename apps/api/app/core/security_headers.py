"""Security headers on every response, and the Content Security Policy for the page.

The CSP is built here but sent only with the HTML page (`app.web_app` calls
`content_security_policy` with that response's nonce), so JSON and asset responses don't carry it.
"""

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

HSTS = "max-age=31536000; includeSubDomains"
PERMISSIONS_POLICY = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
COOP = "same-origin"
REFERRER_POLICY = "same-origin"

# The text is the spec's ("The production image"). `style-src` carries the per-response nonce, for
# the two inline <style> tags Radix injects.
_CSP_TEMPLATE = (
    "default-src 'self'; "
    "script-src 'self' https://challenges.cloudflare.com; "
    "style-src 'self' 'nonce-{nonce}'; "
    "img-src 'self' data:; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "frame-src https://challenges.cloudflare.com; "
    "media-src 'self'; "
    "object-src 'none'; "
    "base-uri 'none'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)

_FIXED_HEADERS = (
    ("Strict-Transport-Security", HSTS),
    ("X-Content-Type-Options", "nosniff"),
    # `same-origin`, not the spec's `no-referrer`: under `no-referrer` a browser sends
    # `Origin: null` on its own same-origin writes, and one without Fetch Metadata (Safari before
    # 16.4) would then fail the same-origin check on every write. `same-origin` still sends no
    # referrer to any other site (ADR 0020's amendment).
    ("Referrer-Policy", REFERRER_POLICY),
    ("Permissions-Policy", PERMISSIONS_POLICY),
    ("Cross-Origin-Opener-Policy", COOP),
)


def content_security_policy(nonce: str) -> str:
    return _CSP_TEMPLATE.format(nonce=nonce)


def set_security_headers(headers: MutableHeaders) -> None:
    """Set the fixed headers. The middleware uses it, and so does the 500 handler, whose response
    Starlette sends from outside every middleware."""
    for name, value in _FIXED_HEADERS:
        headers[name] = value


class SecurityHeadersMiddleware:
    """Pure ASGI middleware, so it never buffers a streamed response.

    It sets the headers on the `http.response.start` message. Added outermost, so a refusal from
    any inner middleware (413, same-origin 403) carries them too.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                message.setdefault("headers", [])
                set_security_headers(MutableHeaders(scope=message))
            await send(message)

        await self.app(scope, receive, send_with_headers)
