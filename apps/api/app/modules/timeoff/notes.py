"""A denial's note, sealed.

The note is text a person wrote, so it is stored encrypted like a case's words (ADR 0015): each
noted request has a data key of its own, wrapped by the key provider, and the note is sealed with
it. The place (associated data) is the table, the column, the tenant, and the request, so a note
copied to another request does not open.

Only two things live here: sealing a new note, and opening a stored one. Who may read a note is
decided by the policy before the second is called; a list of requests opens only the rows that
have a note.
"""

import logging
from typing import NamedTuple
from uuid import UUID

from app.core.encryption import (
    DataKey,
    DecryptionFailed,
    KeyProvider,
    Place,
    new_data_key,
    open_,
    seal,
    wrap_aad,
)

NOTES_TABLE = "time_off_requests"
NOTE_COLUMN = "decision_note"

logger = logging.getLogger(__name__)


class SealedNote(NamedTuple):
    """A note sealed under its own data key, and the key wrapped for storage."""

    key_id: str
    wrapped_key: bytes
    ciphertext: bytes

    @classmethod
    def from_columns(
        cls, key_id: str | None, wrapped_key: bytes | None, ciphertext: bytes | None
    ) -> "SealedNote | None":
        """The stored columns as a sealed note, or None when the request has no note (the
        table's check keeps the three all set or all null)."""
        if key_id is None or wrapped_key is None or ciphertext is None:
            return None
        return cls(key_id, bytes(wrapped_key), bytes(ciphertext))


def _place(tenant_id: UUID, request_id: UUID) -> Place:
    return Place(NOTES_TABLE, NOTE_COLUMN, tenant_id, request_id)


def seal_note(keys: KeyProvider, tenant_id: UUID, request_id: UUID, note: str) -> SealedNote:
    """Make the request's data key, wrap it, and seal the note with it."""
    data_key = new_data_key()
    key_id, wrapped_key = keys.wrap(data_key, aad=wrap_aad(tenant_id, NOTES_TABLE, request_id))
    return SealedNote(
        key_id,
        wrapped_key,
        seal(data_key, note.encode(), place=_place(tenant_id, request_id)),
    )


def open_note(
    keys: KeyProvider,
    tenant_id: UUID,
    request_id: UUID,
    *,
    key_id: str,
    wrapped_key: bytes,
    ciphertext: bytes,
) -> str:
    """The note, opened. Raises `DecryptionFailed` if the key or the text does not open."""
    aad = wrap_aad(tenant_id, NOTES_TABLE, request_id)
    data_key = DataKey(keys.unwrap(key_id, wrapped_key, aad=aad))
    return open_(data_key, ciphertext, place=_place(tenant_id, request_id)).decode()


def open_note_or_none(
    keys: KeyProvider, tenant_id: UUID, request_id: UUID, sealed: SealedNote | None
) -> str | None:
    """The note for a reader the policy has already allowed, or None when there is none or it does
    not open. One note that does not open must not break a page for everyone who sees the
    request: it just does not show, and the log names the request only, never any text."""
    if sealed is None:
        return None
    try:
        return open_note(
            keys,
            tenant_id,
            request_id,
            key_id=sealed.key_id,
            wrapped_key=sealed.wrapped_key,
            ciphertext=sealed.ciphertext,
        )
    except DecryptionFailed:
        logger.warning("A denial note could not be opened (request %s)", request_id)
        return None
