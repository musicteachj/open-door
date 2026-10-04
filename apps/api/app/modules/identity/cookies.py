"""The two cookies a session lives in.

Both names start with `__Host-`, which makes the browser insist on Secure, Path=/, and no Domain,
so no other host or path can set or overwrite them. Both last until the sandbox expires.

- `__Host-od_session` holds the session token. It is HttpOnly, so the page's scripts never see it.
- `__Host-od_csrf` holds the CSRF token. The page reads it and sends it back in the X-CSRF-Token
  header on every request that changes something.
"""

from datetime import UTC, datetime

from starlette.responses import Response

from app.modules.identity.tokens import SessionTokens

SESSION_COOKIE = "__Host-od_session"
CSRF_COOKIE = "__Host-od_csrf"
CSRF_HEADER = "X-CSRF-Token"


def seconds_until(expires_at: datetime) -> int:
    """Whole seconds from now until `expires_at`, rounded down, so a cookie never outlives it."""
    return max(0, int((expires_at - datetime.now(UTC)).total_seconds()))


def set_session_cookies(response: Response, tokens: SessionTokens, expires_at: datetime) -> None:
    max_age = seconds_until(expires_at)
    response.set_cookie(
        SESSION_COOKIE,
        tokens.session,
        max_age=max_age,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )
    response.set_cookie(
        CSRF_COOKIE,
        tokens.csrf,
        max_age=max_age,
        path="/",
        secure=True,
        httponly=False,
        samesite="lax",
    )


def clear_session_cookies(response: Response) -> None:
    """Expire both cookies. A browser accepts the change only with the same `__Host-` attributes."""
    response.delete_cookie(SESSION_COOKIE, path="/", secure=True, httponly=True, samesite="lax")
    response.delete_cookie(CSRF_COOKIE, path="/", secure=True, samesite="lax")
