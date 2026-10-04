"""Session and CSRF tokens, and the cookies that carry them."""

import hashlib
import re
from datetime import UTC, datetime, timedelta

from starlette.responses import Response

from app.modules.identity.cookies import (
    clear_session_cookies,
    seconds_until,
    set_session_cookies,
)
from app.modules.identity.tokens import SessionTokens, hash_token, new_token, token_matches

# 32 random bytes in URL-safe base64, without padding.
TOKEN = re.compile(r"[A-Za-z0-9_-]{43}")
EXPIRES = re.compile(r"expires=[^;]+; ")
MAX_AGE = re.compile(r"Max-Age=([0-9]+)")


def test_a_token_is_32_random_bytes_in_43_cookie_safe_characters() -> None:
    tokens = {new_token() for _ in range(100)}

    assert len(tokens) == 100
    assert all(TOKEN.fullmatch(token) for token in tokens)


def test_the_server_keeps_a_tokens_sha256_digest() -> None:
    token = new_token()

    assert hash_token(token) == hashlib.sha256(token.encode()).digest()
    assert len(hash_token(token)) == 32


def test_a_token_matches_only_its_own_hash() -> None:
    token = new_token()

    assert token_matches(token, hash_token(token)) is True
    assert token_matches(new_token(), hash_token(token)) is False
    assert token_matches("", hash_token("")) is False
    assert token_matches(None, hash_token(token)) is False


def test_the_raw_tokens_never_appear_in_a_repr() -> None:
    tokens = SessionTokens.new()

    assert tokens.session not in repr(tokens)
    assert tokens.csrf not in repr(tokens)
    assert (tokens.session_hash, tokens.csrf_hash) == (
        hash_token(tokens.session),
        hash_token(tokens.csrf),
    )


def test_both_cookies_are_host_only_secure_lax_and_last_until_the_sandbox_expires() -> None:
    tokens = SessionTokens("session-token", "csrf-token")
    response = Response()
    expires_at = datetime.now(UTC) + timedelta(hours=24)

    set_session_cookies(response, tokens, expires_at)

    headers = response.headers.getlist("set-cookie")
    max_age = int(MAX_AGE.findall(headers[0])[0])
    assert 86_390 < max_age < 86_400
    assert headers == [
        f"__Host-od_session=session-token; HttpOnly; Max-Age={max_age}; Path=/; SameSite=lax;"
        " Secure",
        f"__Host-od_csrf=csrf-token; Max-Age={max_age}; Path=/; SameSite=lax; Secure",
    ]


def test_an_expired_sandbox_gives_a_cookie_age_of_zero() -> None:
    assert seconds_until(datetime.now(UTC) - timedelta(minutes=1)) == 0


def test_clearing_expires_both_cookies_with_the_same_attributes() -> None:
    response = Response()

    clear_session_cookies(response)

    # Starlette also sends an Expires of the current time, which the comparison leaves out.
    headers = [EXPIRES.sub("", header) for header in response.headers.getlist("set-cookie")]
    assert headers == [
        '__Host-od_session=""; HttpOnly; Max-Age=0; Path=/; SameSite=lax; Secure',
        '__Host-od_csrf=""; Max-Age=0; Path=/; SameSite=lax; Secure',
    ]
