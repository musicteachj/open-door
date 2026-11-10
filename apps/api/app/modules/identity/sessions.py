"""The sessions table: start, find, rotate, and end a session.

`sessions` is under row-level security (migration 0017) with rules of its own. A session is looked
up before the tenant is known, so the lookup first presents the token's hash in its transaction
(`SET_SESSION_LOOKUP`), and the rules show a row to a transaction that presented its hash or that
is scoped to its sandbox. A session is only ever found by its token's hash, never listed or
searched. The API's login may select, insert, and delete these rows, but not update them.
Inserts must be for the transaction's sandbox, expiring no later than it. Rotating a session
deletes the old row and inserts a new one, in the caller's transaction.

Each session belongs to a family: a new sandbox's session starts one, and a persona switch copies
it. Signing out ends the whole family, so a switch racing a sign-out can't leave a replacement
signed in.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import LargeBinary, Uuid, delete, func, insert, literal, select, text
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
    # Shared by a session and every session a persona switch made from it.
    family_id: UUID


# Presents a token's hash to the row-level security rules for the rest of this transaction. The
# hash is hex, because a setting holds text. A transaction that presents a hash can read and delete
# the row with that hash, whatever its tenant context.
SET_SESSION_LOOKUP = text("SELECT set_config('app.session_token_hash', :hash, true)")


async def present_token_hash(session: AsyncSession, token_hash: bytes) -> None:
    await session.execute(SET_SESSION_LOOKUP, {"hash": token_hash.hex()})


async def find_session(session: AsyncSession, token_hash: bytes) -> SessionRecord | None:
    """The live session with this token hash. An expired one is never returned.

    It presents the hash first, so it works in a transaction with no tenant."""
    await present_token_hash(session, token_hash)
    query = select(
        UserSession.token_hash,
        UserSession.csrf_hash,
        UserSession.tenant_id,
        UserSession.person_id,
        UserSession.expires_at,
        UserSession.family_id,
    ).where(UserSession.token_hash == token_hash, UserSession.expires_at > func.now())
    row = (await session.execute(query)).one_or_none()
    return None if row is None else SessionRecord(*row)


async def start_session(
    session: AsyncSession, tenant_id: UUID, person_id: UUID, family_id: UUID | None = None
) -> SessionTokens:
    """Store a new session for `person_id` and return its raw tokens, which only the cookies hold.

    The session starts a family of its own unless `family_id` joins an existing one (a persona
    switch passes the old session's).

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
            literal(family_id or uuid4(), Uuid),
        )
        .join_from(Person, Tenant, Tenant.id == Person.tenant_id)
        .where(Person.id == person_id, Person.tenant_id == tenant_id)
    )
    stored = await session.scalar(
        insert(UserSession)
        .from_select(
            ["token_hash", "csrf_hash", "tenant_id", "person_id", "expires_at", "family_id"],
            new_session,
        )
        .returning(UserSession.token_hash)
    )
    if stored is None:
        raise PersonNotInTenantError
    return tokens


async def end_session(session: AsyncSession, token_hash: bytes) -> bool:
    """Delete a live session. Whether this call deleted it: False if it was already gone.

    It presents the hash first, so it may end the session from a transaction with no tenant."""
    await present_token_hash(session, token_hash)
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
    return await start_session(session, current.tenant_id, person_id, family_id=current.family_id)


async def end_session_family(session: AsyncSession, current: SessionRecord) -> bool:
    """Sign out: delete `current` and every session in its family. Whether this call deleted any.

    Two statements, on purpose. A persona switch that has deleted `current` and inserted its
    replacement, but not yet committed, holds the row lock on `current`. The first DELETE waits for
    it. The second is a new statement, so under READ COMMITTED it takes a new snapshot and sees the
    replacement the switch committed. One DELETE by family would have taken its snapshot before the
    switch committed and missed it. A switch that starts after this finds `current` gone.

    The family is looked up inside the caller's sandbox only (row-level security), so a record that
    names another sandbox's family deletes nothing there.
    """
    own = await end_session(session, current.token_hash)
    family = await session.scalars(
        delete(UserSession)
        .where(UserSession.family_id == current.family_id)
        .returning(UserSession.token_hash)
        .execution_options(synchronize_session=False)
    )
    replacements = family.all()
    return own or bool(replacements)
