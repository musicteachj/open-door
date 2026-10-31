"""Envelope encryption for case text and conversation text (ADR 0015).

Each conversation (and, from migration 0013, each case) has a random data key. A value is sealed
with AES-256-GCM under that key, and the key itself is stored wrapped by a key-encryption key from
a `KeyProvider`. The associated data binds every ciphertext to its table, column, sandbox, and row,
and every wrapped key to its sandbox and owning row, so a copied value fails to open.

Nothing here logs, and no error holds a key or plaintext: `DecryptionFailed` has one fixed message.
"""

import base64
import binascii
import contextlib
import os
import re
import secrets
import stat
import uuid
from pathlib import Path
from typing import NamedTuple, Protocol, runtime_checkable

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# The first byte of every ciphertext and wrapped key, so a later format can be told apart.
VERSION_BYTE = b"\x01"
KEY_BYTES = 32
NONCE_BYTES = 12
TAG_BYTES = 16
MIN_CIPHERTEXT_BYTES = len(VERSION_BYTE) + NONCE_BYTES + TAG_BYTES

# The fixed, obviously fake key the tests and CI use (ID "test"). The API refuses it outside tests.
TEST_KEY = bytes(KEY_BYTES)
TEST_KEY_ID = "test"

KEY_ID_PATTERN = re.compile(r"[A-Za-z0-9_.-]+")

# Separates the two kinds of associated data, so a wrapped key can never pass as a sealed value.
VALUE_PURPOSE = b"od.v1.value"
WRAP_PURPOSE = b"od.v1.wrap"


class DecryptionFailed(Exception):  # noqa: N818  (the name is the plan's)
    """A value or key did not open: wrong place, wrong key, or changed bytes.

    One type and one fixed message for every cause, so an error never tells an attacker which part
    was wrong, and never holds a key or plaintext.
    """

    def __init__(self) -> None:
        super().__init__("The value could not be decrypted.")


class Place(NamedTuple):
    """Where a sealed value lives. It is part of the associated data."""

    table: str
    column: str
    tenant_id: uuid.UUID
    row_id: uuid.UUID


class DataKey(bytes):
    """A data key. It is plain bytes for the cipher but never shows itself in a repr or str."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "DataKey(<redacted>)"

    __str__ = __repr__


@runtime_checkable
class KeyProvider(Protocol):
    def wrap(self, data_key: bytes, *, aad: bytes) -> tuple[str, bytes]:
        """Wrap a data key. Returns the ID of the key that wrapped it, and the wrapped key."""
        ...

    def unwrap(self, key_id: str, wrapped: bytes, *, aad: bytes) -> bytes: ...


def _encode(purpose: bytes, *parts: bytes) -> bytes:
    """Associated data: each part after a 4-byte length, so no two lists of parts match."""
    out = bytearray()
    for part in (purpose, *parts):
        out += len(part).to_bytes(4, "big") + part
    return bytes(out)


def _place_aad(place: Place) -> bytes:
    return _encode(
        VALUE_PURPOSE,
        place.table.encode(),
        place.column.encode(),
        place.tenant_id.bytes,
        place.row_id.bytes,
    )


def wrap_aad(tenant_id: uuid.UUID, owner_table: str, owner_id: uuid.UUID) -> bytes:
    """The associated data of a wrapped data key: its sandbox and the row that owns the key."""
    return _encode(WRAP_PURPOSE, tenant_id.bytes, owner_table.encode(), owner_id.bytes)


def new_data_key() -> DataKey:
    return DataKey(secrets.token_bytes(KEY_BYTES))


def _require_key_length(key: bytes) -> None:
    # AES-GCM takes 16 and 24 bytes too, which would quietly weaken a key.
    if len(key) != KEY_BYTES:
        msg = f"A key is {KEY_BYTES} bytes."
        raise ValueError(msg)


def _encrypt(key: bytes, plaintext: bytes, aad: bytes) -> bytes:
    _require_key_length(key)
    # A fresh random 96-bit nonce every time. A key seals far fewer values than random nonces allow.
    nonce = os.urandom(NONCE_BYTES)
    return VERSION_BYTE + nonce + AESGCM(key).encrypt(nonce, plaintext, aad)


def _decrypt(key: bytes, ciphertext: bytes, aad: bytes) -> bytes:
    _require_key_length(key)
    if len(ciphertext) < MIN_CIPHERTEXT_BYTES or ciphertext[:1] != VERSION_BYTE:
        raise DecryptionFailed
    nonce = ciphertext[1 : 1 + NONCE_BYTES]
    try:
        return AESGCM(key).decrypt(nonce, ciphertext[1 + NONCE_BYTES :], aad)
    except InvalidTag:
        # `from None` so nothing from the cipher travels with the error.
        raise DecryptionFailed from None


def seal(data_key: bytes, plaintext: bytes, *, place: Place) -> bytes:
    """Encrypt for one place: version byte, nonce, then the ciphertext and tag."""
    return _encrypt(data_key, plaintext, _place_aad(place))


def open_(data_key: bytes, ciphertext: bytes, *, place: Place) -> bytes:
    """Decrypt a value sealed for the same place. Anything else raises `DecryptionFailed`."""
    return _decrypt(data_key, ciphertext, _place_aad(place))


class _Key:
    """One key-encryption key. Its repr shows nothing of the bytes."""

    __slots__ = ("_cipher_key",)

    def __init__(self, key: bytes) -> None:
        self._cipher_key = key

    def __repr__(self) -> str:
        return "Key(<redacted>)"

    def encrypt(self, plaintext: bytes, aad: bytes) -> bytes:
        return _encrypt(self._cipher_key, plaintext, aad)

    def decrypt(self, ciphertext: bytes, aad: bytes) -> bytes:
        return _decrypt(self._cipher_key, ciphertext, aad)

    @property
    def is_test_key(self) -> bool:
        return secrets.compare_digest(self._cipher_key, TEST_KEY)


class LocalKeyProvider:
    """Key-encryption keys from a keyring: lines of `id:base64`, newest first.

    The newest key wraps; any key in the ring unwraps, so a key can be rotated.
    """

    def __init__(self, keys: list[tuple[str, bytes]]) -> None:
        if not keys:
            msg = "The keyring has no keys."
            raise ValueError(msg)
        self._keys = {key_id: _Key(key) for key_id, key in keys}
        self._newest = keys[0][0]

    @classmethod
    def from_keyring(cls, text: str) -> "LocalKeyProvider":
        """Parse a keyring. Every error names the line, never the key."""
        keys: list[tuple[str, bytes]] = []
        for number, raw in enumerate(text.splitlines(), start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            key_id, separator, encoded = line.partition(":")
            if not separator or KEY_ID_PATTERN.fullmatch(key_id) is None:
                msg = f"Line {number} of the keyring is not `id:base64`."
                raise ValueError(msg)
            if any(key_id == known for known, _ in keys):
                msg = f"Line {number} of the keyring repeats a key ID."
                raise ValueError(msg)
            try:
                key = base64.b64decode(encoded, validate=True)
            except binascii.Error:
                msg = f"Line {number} of the keyring has a key that is not base64."
                raise ValueError(msg) from None
            if len(key) != KEY_BYTES:
                msg = f"Line {number} of the keyring has a key that is not {KEY_BYTES} bytes."
                raise ValueError(msg)
            keys.append((key_id, key))
        if not keys:
            msg = "The keyring has no keys."
            raise ValueError(msg)
        return cls(keys)

    @property
    def key_ids(self) -> tuple[str, ...]:
        return tuple(self._keys)

    @property
    def uses_test_key(self) -> bool:
        return any(key.is_test_key for key in self._keys.values())

    def __repr__(self) -> str:
        return f"LocalKeyProvider(key_ids={list(self._keys)!r})"

    def wrap(self, data_key: bytes, *, aad: bytes) -> tuple[str, bytes]:
        _require_key_length(data_key)
        return self._newest, self._keys[self._newest].encrypt(data_key, aad)

    def unwrap(self, key_id: str, wrapped: bytes, *, aad: bytes) -> bytes:
        key = self._keys.get(key_id)
        if key is None:
            raise DecryptionFailed
        data_key = key.decrypt(wrapped, aad)
        if len(data_key) != KEY_BYTES:
            raise DecryptionFailed
        return DataKey(data_key)


# Where `make keyring` writes the development keyring, relative to apps/api.
DEFAULT_KEYRING_PATH = ".keys/keyring"
_API_DIR = Path(__file__).resolve().parents[2]


def resolve_keyring_path(value: str) -> Path:
    """A relative keyring path is relative to apps/api, whatever the working directory."""
    path = Path(value)
    return path if path.is_absolute() else _API_DIR / path


def load_key_provider(*, keyring: str | None, keyring_file: str | None) -> LocalKeyProvider:
    """Build the provider from the keyring text, or else the keyring file.

    A file that anyone but its owner can read is refused. Errors name the problem and never the key.
    """
    if keyring is not None:
        return LocalKeyProvider.from_keyring(keyring)
    if keyring_file is None:
        msg = "No keyring: set ENCRYPTION_KEYRING or ENCRYPTION_KEYRING_FILE."
        raise ValueError(msg)
    path = resolve_keyring_path(keyring_file)
    try:
        mode = path.stat().st_mode
    except OSError:
        msg = "The keyring file is missing or unreadable. Run `make keyring` to write one."
        raise ValueError(msg) from None
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        msg = "The keyring file is readable by group or others. Run `chmod 600` on it."
        raise ValueError(msg)
    text: str | None = None
    with contextlib.suppress(OSError, UnicodeDecodeError):
        text = path.read_text(encoding="utf-8")
    if text is None:
        # Raised outside the handler so no context travels: a decode error holds the file's bytes.
        msg = "The keyring file could not be read as text. Check that it is a file."
        raise ValueError(msg) from None
    return LocalKeyProvider.from_keyring(text)
