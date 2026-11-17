"""The dependencies a signed-in route uses: the session, the CSRF check, and the actor.

For each request:

1. The `__Host-od_session` cookie is hashed and looked up. A missing, unknown, or expired session
   is a 401. Only an unknown or expired one is logged as a security event.
2. Every request must echo the CSRF token in X-CSRF-Token, matching the session's hash in constant
   time, or it gets a 403 (logged). That includes a read: no navigation, image, or cross-site form
   can send the header, so a future audited route cannot forget it. Only routes with no session
   (the health checks, and starting a sandbox) are exempt, because they never come here.
3. The tenant context is set in the same transaction as the lookup (`scope_transaction`), and the
   actor is loaded in it, with their reports fresh from the database, and the HR flag is set for the
   private-details rule. So the session lookup and the route's work share one transaction and one
   connection (one round trip fewer, and the tenant context is set in the same transaction as the
   lookup). The lookup is a plain read with no row lock, so a sign-out that commits during a request
   does not stop that request, as in any web app.
4. The route runs in that transaction, which commits before the response is sent, and only if the
   route succeeded.

`current_session` and `signed_in_caller` are the short form for the turn stream, which keeps its
own short transactions: they look up the session in a transaction that closes at once.
"""

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.api.deps import get_engine
from app.core.problems import ProblemError
from app.db.tenancy import (
    NO_TENANT,
    TenantContext,
    scope_transaction,
    set_is_hr,
    tenant_session,
)
from app.modules.identity.actor import load_actor
from app.modules.identity.cookies import CSRF_HEADER, SESSION_COOKIE
from app.modules.identity.security_log import SecurityEvent, log_security_event
from app.modules.identity.sessions import SessionRecord, find_session
from app.modules.identity.tokens import hash_token, token_matches
from app.policy import Action, Actor, PersonResource, can

logger = logging.getLogger(__name__)

CSRF_REJECTED = "csrf-rejected"
CSRF_DETAIL = "The CSRF token is missing or wrong."
NOT_SIGNED_IN = "There is no current session. Start a sandbox to sign in."


@dataclass(frozen=True, slots=True)
class SignedIn:
    """What a signed-in route works with: the actor, and the request's one transaction."""

    actor: Actor
    db: AsyncSession
    session: SessionRecord


def _check_csrf(request: Request, record: SessionRecord) -> None:
    """Refuse (403 `csrf-rejected`, logged) a request whose X-CSRF-Token is missing or wrong.

    The problem has a type of its own so the web app can tell it from a permission denial: a browser
    that lost its CSRF cookie is, for the app, signed out."""
    if token_matches(request.headers.get(CSRF_HEADER), record.csrf_hash):
        return
    log_security_event(
        SecurityEvent.CSRF_REJECTED,
        request,
        "X-CSRF-Token is missing or wrong",
        tenant_id=record.tenant_id,
        actor_id=record.person_id,
    )
    raise ProblemError(status.HTTP_403_FORBIDDEN, CSRF_REJECTED, CSRF_DETAIL)


async def _find_live_session(request: Request, db: AsyncSession) -> SessionRecord:
    """The request's live session, looked up in `db`, or a 401 (logged if the cookie was a
    session that is unknown or expired). The CSRF check is the caller's next step."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        # A first visit, or a signed-out browser, has no cookie. That is not a refusal worth
        # the security log, which holds only refused requests.
        logger.debug("No session cookie on %s %s", request.method, request.url.path)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, NOT_SIGNED_IN)
    record = await find_session(db, hash_token(token))
    if record is None:
        log_security_event(SecurityEvent.SESSION_INVALID, request, "unknown or expired session")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, NOT_SIGNED_IN)
    return record


async def current_session(
    request: Request, engine: Annotated[AsyncEngine, Depends(get_engine)]
) -> SessionRecord:
    """The request's live session, after the CSRF check, in a transaction that closes at once.
    For routes that take several connections one after another (the turn stream) or that need only
    the session; a route that reads or writes the tenant's data uses `signed_in` instead."""
    # The lookup presents the token's hash, so it needs no tenant.
    async with tenant_session(engine, NO_TENANT) as db:
        record = await _find_live_session(request, db)
    _check_csrf(request, record)
    return record


async def signed_in(
    request: Request, engine: Annotated[AsyncEngine, Depends(get_engine)]
) -> AsyncIterator[SignedIn]:
    # One transaction for the lookup and for the route's work. It starts with no tenant, finds the
    # session by the hash it presents, and then takes on the session's tenant and person.
    async with tenant_session(engine, NO_TENANT) as db:
        record = await _find_live_session(request, db)
        _check_csrf(request, record)
        context = TenantContext(record.tenant_id, record.person_id)
        await scope_transaction(db, context)
        actor = await load_actor(db, record.tenant_id, record.person_id)
        if actor is None:
            # Only if the sandbox was deleted between the session lookup and now.
            log_security_event(
                SecurityEvent.SESSION_INVALID,
                request,
                "the sandbox is gone",
                tenant_id=record.tenant_id,
                actor_id=record.person_id,
            )
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, NOT_SIGNED_IN)
        await set_is_hr(db, actor.is_hr_admin)
        yield SignedIn(actor, db, record)


@dataclass(frozen=True, slots=True)
class Caller:
    """The signed-in actor and session, with no transaction open. For a route that takes several
    database connections one after another (the assistant's turn stream), so it must not hold the
    request's own while it waits for another: with enough such requests at once, every one would
    hold a connection and wait for a second, and the pool would never free."""

    actor: Actor
    session: SessionRecord


async def signed_in_caller(
    request: Request,
    engine: Annotated[AsyncEngine, Depends(get_engine)],
    record: Annotated[SessionRecord, Depends(current_session)],
) -> Caller:
    context = TenantContext(record.tenant_id, record.person_id)
    async with tenant_session(engine, context) as db:
        actor = await load_actor(db, record.tenant_id, record.person_id)
    if actor is None:
        log_security_event(
            SecurityEvent.SESSION_INVALID,
            request,
            "the sandbox is gone",
            tenant_id=record.tenant_id,
            actor_id=record.person_id,
        )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, NOT_SIGNED_IN)
    return Caller(actor, record)


CallerDep = Annotated[Caller, Depends(signed_in_caller)]

# scope="function" ends the dependency, and so commits the transaction, before the response is
# sent. A failed commit is then a 500, not a success the client was already told about.
SignedInDep = Annotated[SignedIn, Depends(signed_in, scope="function")]


def authorize(
    request: Request, signed_in: SignedIn, action: Action, target: PersonResource
) -> None:
    """Ask the policy layer. A denial is a 403, recorded in the security log."""
    if can(signed_in.actor, action, target):
        return
    log_security_event(
        SecurityEvent.AUTHZ_DENIED,
        request,
        action.value,
        tenant_id=signed_in.actor.tenant_id,
        actor_id=signed_in.actor.person_id,
        target_id=target.person_id,
    )
    raise HTTPException(status.HTTP_403_FORBIDDEN, "You don't have permission to see this.")
