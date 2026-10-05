"""The dependencies a signed-in route uses: the session, the CSRF check, and the actor.

For each request:

1. The `__Host-od_session` cookie is hashed and looked up. A missing, unknown, or expired session
   is a 401. Only an unknown or expired one is logged as a security event.
2. A request that changes state must also echo the CSRF token in X-CSRF-Token, matching the
   session's hash in constant time, or it gets a 403. Every session-bound route gets this check,
   with nothing to remember.
3. One transaction opens, scoped to the session's tenant and person. The actor is loaded in it,
   with their reports fresh from the database, and the HR flag is set for the private-details rule.
4. The route runs in that transaction, which commits before the response is sent, and only if the
   route succeeded.
"""

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.api.deps import get_engine
from app.db.tenancy import NO_TENANT, TenantContext, set_is_hr, tenant_session
from app.modules.identity.actor import load_actor
from app.modules.identity.cookies import CSRF_HEADER, SESSION_COOKIE
from app.modules.identity.same_origin import SAFE_METHODS
from app.modules.identity.security_log import SecurityEvent, log_security_event
from app.modules.identity.sessions import SessionRecord, find_session
from app.modules.identity.tokens import hash_token, token_matches
from app.policy import Action, Actor, PersonResource, can

logger = logging.getLogger(__name__)

NOT_SIGNED_IN = "There is no current session. Start a sandbox to sign in."


@dataclass(frozen=True, slots=True)
class SignedIn:
    """What a signed-in route works with: the actor, and the request's one transaction."""

    actor: Actor
    db: AsyncSession
    session: SessionRecord


async def current_session(
    request: Request, engine: Annotated[AsyncEngine, Depends(get_engine)]
) -> SessionRecord:
    """The request's live session, after the CSRF check if the request changes state."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        # A first visit, or a signed-out browser, has no cookie. That is not a refusal worth
        # the security log, which holds only refused requests.
        logger.debug("No session cookie on %s %s", request.method, request.url.path)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, NOT_SIGNED_IN)
    # The sessions table has no row-level security, so the lookup needs no tenant.
    async with tenant_session(engine, NO_TENANT) as db:
        record = await find_session(db, hash_token(token))
    if record is None:
        log_security_event(SecurityEvent.SESSION_INVALID, request, "unknown or expired session")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, NOT_SIGNED_IN)
    if request.method not in SAFE_METHODS and not token_matches(
        request.headers.get(CSRF_HEADER), record.csrf_hash
    ):
        log_security_event(
            SecurityEvent.CSRF_REJECTED,
            request,
            "X-CSRF-Token is missing or wrong",
            tenant_id=record.tenant_id,
            actor_id=record.person_id,
        )
        raise HTTPException(status.HTTP_403_FORBIDDEN, "The CSRF token is missing or wrong.")
    return record


async def signed_in(
    request: Request,
    engine: Annotated[AsyncEngine, Depends(get_engine)],
    record: Annotated[SessionRecord, Depends(current_session)],
) -> AsyncIterator[SignedIn]:
    context = TenantContext(record.tenant_id, record.person_id)
    async with tenant_session(engine, context) as db:
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
