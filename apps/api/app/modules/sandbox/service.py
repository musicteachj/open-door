"""Creating a sandbox: a new company, seeded, with the visitor signed in as one of its personas."""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import insert, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.encryption import KeyProvider
from app.db.errors import has_sqlstate
from app.db.locks import SANDBOX_STARTS_NS, lock_global
from app.db.models import Tenant
from app.db.tenancy import NO_TENANT, TenantContext, tenant_session
from app.modules.audit.service import record_event
from app.modules.identity.actor import load_actor
from app.modules.identity.sessions import end_session_family, find_session, start_session
from app.modules.identity.tokens import SessionTokens
from app.modules.people.queries import get_me
from app.modules.people.schemas import Me, PersonaKey
from app.modules.sandbox.limits import (
    StartLimits,
    check_start_limits,
    record_start,
)
from app.modules.sandbox.seed import build_company, insert_company

logger = logging.getLogger(__name__)

# The SQLSTATE that the trigger on tenants (migration 0005) raises when no handbook version is
# published. A custom code: class OD is ours.
NO_PUBLISHED_HANDBOOK = "OD001"


def is_no_published_handbook(error: DBAPIError) -> bool:
    """Whether the database refused a new tenant because no handbook version is published."""
    return has_sqlstate(error, NO_PUBLISHED_HANDBOOK)


# A sandbox, and every session in it, is deleted 24 hours after it is created (ADR 0007).
SANDBOX_LIFETIME = timedelta(hours=24)


class HandbookNotLoadedError(Exception):
    """No handbook version is published, so a sandbox can't be created (the route answers 503)."""


@dataclass(frozen=True, slots=True)
class NewSandbox:
    tenant_id: UUID
    expires_at: datetime
    tokens: SessionTokens
    me: Me


async def _end_replaced_session(engine: AsyncEngine, token_hash: bytes) -> None:
    # The lookup presents the hash, so it needs no tenant. The whole family ends, in the old
    # sandbox's own context, where `session.ended` is audited once.
    async with tenant_session(engine, NO_TENANT) as db:
        old = await find_session(db, token_hash)
    if old is None:
        return
    async with tenant_session(engine, TenantContext(old.tenant_id, old.person_id)) as db:
        if await end_session_family(db, old):
            await record_event(
                db, tenant_id=old.tenant_id, actor_id=old.person_id, action="session.ended"
            )


# How long a start waits for the one lock that serializes the count. The reservation is a few
# milliseconds of work, so a longer wait means a pile-up: it fails with Postgres's
# lock_not_available (55P03), which the API answers as 503 "busy", instead of holding a connection
# until the 10 s statement timeout. It goes into the SQL text, so it is a constant, never input.
RESERVE_LOCK_TIMEOUT = "5s"


async def reserve_start(engine: AsyncEngine, ip_hash: bytes, limits: StartLimits) -> None:
    """Count this start against the limits and record it, in a short transaction of its own.

    Under the one advisory lock for all starts it counts, then adds the row and commits, so two
    starts at the limit can't both pass. A refusal (or a lock timeout) raises before anything else
    has happened, so the caller leaves the visitor's current session alone. The lock is released
    at that commit, long before the seed runs, so starts don't queue behind each other's
    145-person seeds or hold connections while they wait. Needs no tenant: the table counts every
    address.
    """
    async with tenant_session(engine, NO_TENANT) as db:
        await db.execute(text(f"SET LOCAL lock_timeout = '{RESERVE_LOCK_TIMEOUT}'"))
        await lock_global(db, SANDBOX_STARTS_NS)
        await check_start_limits(db, ip_hash, limits)
        await record_start(db, ip_hash)


async def create_sandbox(
    engine: AsyncEngine,
    persona: PersonaKey,
    replacing: bytes | None,
    keys: KeyProvider,
    ip_hash: bytes,
    limits: StartLimits,
) -> NewSandbox:
    """Reserve a start, then create and seed a sandbox and start a session in it as `persona`.

    The start is counted and recorded first, in its own short transaction (`reserve_start`),
    before the visitor's current session is touched: a start refused by the limits, or by a
    pile-up on the lock, leaves the sandbox they have. The seed then runs in a transaction of its
    own, so the advisory lock is not held across it. A seed that fails after the start was
    recorded still counts: deliberately conservative, since the seed is the expensive work the
    limits exist to bound, and a failed attempt cost it too.

    `replacing` is the token hash of a session the visitor already had. Once the start is
    reserved it ends, in its own transaction scoped to its own sandbox, where `session.ended` is
    audited, so each sandbox creation leaves the browser with exactly one session. If creating
    the new sandbox then fails, the visitor has no session.

    The database pins the new tenant to the newest published handbook version (a trigger,
    migration 0005), so there is no version logic here. If none is published, the insert fails, the
    transaction rolls back, and this raises `HandbookNotLoadedError`.
    """
    await reserve_start(engine, ip_hash, limits)
    if replacing is not None:
        await _end_replaced_session(engine, replacing)
    tenant_id = uuid4()
    created_at = datetime.now(UTC)
    expires_at = created_at + SANDBOX_LIFETIME
    company = build_company(tenant_id, created_at.date())
    person_id = next(person.id for person in company.people if person.persona_key == persona)
    try:
        async with tenant_session(engine, TenantContext(tenant_id, person_id)) as db:
            await db.execute(
                insert(Tenant).values(
                    id=tenant_id, expires_at=expires_at, anchor_date=company.anchor_date
                )
            )
            await insert_company(db, company, keys)
            tokens = await start_session(db, tenant_id, person_id)
            await record_event(
                db,
                tenant_id=tenant_id,
                actor_id=person_id,
                action="sandbox.created",
                target_type="tenant",
                target_id=tenant_id,
                after={"personaKey": persona},
            )
            actor = await load_actor(db, tenant_id, person_id)
            if actor is None:
                msg = f"The seed company has no {persona!r} persona"
                raise RuntimeError(msg)
            me = await get_me(db, actor, expires_at)
    except DBAPIError as error:
        if not is_no_published_handbook(error):
            raise
        # The transaction has rolled back, so no tenant exists.
        logger.warning("Sandbox not created: %s", error.orig)
        raise HandbookNotLoadedError from error
    return NewSandbox(tenant_id, expires_at, tokens, me)
