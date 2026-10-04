"""Session and CSRF tokens: 32 random bytes each, kept by the server only as SHA-256 hashes.

The raw tokens live only in the visitor's cookies. The sessions table stores their hashes, so a
copy of the table can't be used to sign in, and a token is compared with its hash in constant
time.
"""

import hashlib
import hmac
import secrets
from dataclasses import dataclass, field

TOKEN_BYTES = 32


def new_token() -> str:
    """32 random bytes, as 43 URL-safe characters that a cookie can hold without quoting."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> bytes:
    """The SHA-256 digest the server stores and looks the token up by."""
    return hashlib.sha256(token.encode()).digest()


def token_matches(token: str | None, expected_hash: bytes) -> bool:
    """Whether `token` hashes to `expected_hash`, compared in constant time."""
    if not token:
        return False
    return hmac.compare_digest(hash_token(token), expected_hash)


@dataclass(frozen=True, slots=True)
class SessionTokens:
    """A new session's two raw tokens, on their way to the visitor's cookies.

    Neither appears in the repr, so logging this object can't leak them.
    """

    session: str = field(repr=False)
    csrf: str = field(repr=False)

    @classmethod
    def new(cls) -> "SessionTokens":
        return cls(new_token(), new_token())

    @property
    def session_hash(self) -> bytes:
        return hash_token(self.session)

    @property
    def csrf_hash(self) -> bytes:
        return hash_token(self.csrf)
