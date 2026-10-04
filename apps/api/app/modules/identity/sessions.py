"""The sessions table: start, find, rotate, and end a session.

`sessions` is the one table outside row-level security, because a session is looked up before the
tenant is known. So a session is only ever found by its token's hash, never listed or searched.
The API's login may select, insert, and delete these rows, but not update them. Rotating a
session deletes the old row and inserts a new one, in the caller's transaction.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import LargeBinary, delete, func, insert, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Person, Tenant, UserSession
from app.modules.identity.tokens import SessionTokens


class SessionGoneError(Exception):
    """The session to replace no longer exists: it was ended, rotated, or expired."""


class PersonNotInTenantError(Exception):
    """No such person in the transaction's tenant, so no session was started."""


@dataclass(frozen=True, slots=True)
class SessionRecord:
    """A live session, as stored. It holds hashes only, never the raw tokens."""

    token_hash: bytes
    csrf_hash: bytes
    tenant_id: UUID
    person_id: UUID
    # Copied from the tenant: a session never outlives its sandbox.
    expires_at: datetime


async def find_session(session: AsyncSession, token_hash: bytes) -> SessionRecord | None:
    """The live session with this token hash. An expired one is never returned."""
    query = select(
        UserSession.token_hash,
        UserSession.csrf_hash,
        UserSession.tenant_id,
        UserSession.person_id,
        UserSession.expires_at,
    ).where(UserSession.token_hash == token_hash, UserSession.expires_at > func.now())
    row = (await session.execute(query)).one_or_none()
    return None if row is None else SessionRecord(*row)


async def start_session(session: AsyncSession, tenant_id: UUID, person_id: UUID) -> SessionTokens:
    """Store a new session for `person_id` and return its raw tokens, which only the cookies hold.

    The row is built from the database's own people and tenants, not from the caller's values.
    Row-level security shows this transaction only its own tenant, so the person must be in that
    tenant, and the session's expiry is copied from the tenant, so it can never outlive it. A
    person that isn't there, or that belongs to a different tenant than `tenant_id`, raises
    `PersonNotInTenantError`, and nothing is stored.
    """
    tokens = SessionTokens.new()
    new_session = (
        select(
            literal(tokens.session_hash, LargeBinary),
            literal(tokens.csrf_hash, LargeBinary),
            Person.tenant_id,
            Person.id,
            Tenant.expires_at,
        )
        .join_from(Person, Tenant, Tenant.id == Person.tenant_id)
        .where(Person.id == person_id, Person.tenant_id == tenant_id)
    )
    stored = await session.scalar(
        insert(UserSession)
        .from_select(
            ["token_hash", "csrf_hash", "tenant_id", "person_id", "expires_at"], new_session
        )
        .returning(UserSession.token_hash)
    )
    if stored is None:
        raise PersonNotInTenantError
    return tokens


async def end_session(session: AsyncSession, token_hash: bytes) -> bool:
    """Delete a live session. Whether this call deleted it: False if it was already gone."""
    deleted = await session.scalar(
        delete(UserSession)
        .where(UserSession.token_hash == token_hash, UserSession.expires_at > func.now())
        .returning(UserSession.token_hash)
        .execution_options(synchronize_session=False)
    )
    return deleted is not None


async def rotate_session(
    session: AsyncSession, current: SessionRecord, person_id: UUID
) -> SessionTokens:
    """Replace `current` with a new session for `person_id`, with a new session token and a new
    CSRF token. Both old tokens stop working when the caller's transaction commits.

    Raises `SessionGoneError`, and stores nothing, if `current` has already been ended, rotated by
    another request, or expired. Two requests that rotate the same session can't both succeed:
    the second one's delete finds the row already gone.
    """
    if not await end_session(session, current.token_hash):
        raise SessionGoneError
    return await start_session(session, current.tenant_id, person_id)
