"""Who am I, switching persona, and signing out."""

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select

from app.api.schemas import CamelModel
from app.db.models import Person
from app.modules.audit.service import record_event
from app.modules.identity.actor import load_actor
from app.modules.identity.cookies import clear_session_cookies, set_session_cookies
from app.modules.identity.deps import NOT_SIGNED_IN, SignedInDep
from app.modules.identity.security_log import SecurityEvent, log_security_event
from app.modules.identity.sessions import SessionGoneError, end_session, rotate_session
from app.modules.people.queries import get_me
from app.modules.people.schemas import Me, PersonaKey

router = APIRouter(tags=["session"])


class PersonaChoice(CamelModel):
    persona: PersonaKey


@router.get(
    "/me",
    operation_id="getMe",
    summary="The signed-in person's own card, and when their sandbox expires",
    response_model=Me,
)
async def get_current_person(signed_in: SignedInDep) -> Me:
    return await get_me(signed_in.db, signed_in.actor, signed_in.session.expires_at)


@router.put(
    "/session/persona",
    operation_id="switchPersona",
    summary="Sign in as another persona in the same sandbox, with new session and CSRF tokens",
    response_model=Me,
)
async def switch_persona(
    choice: PersonaChoice, signed_in: SignedInDep, request: Request, response: Response
) -> Me:
    db, actor, current = signed_in.db, signed_in.actor, signed_in.session
    person_id = await db.scalar(select(Person.id).where(Person.persona_key == choice.persona))
    new_actor = None if person_id is None else await load_actor(db, actor.tenant_id, person_id)
    if new_actor is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This sandbox has no such persona.")
    switching_from = await db.scalar(select(Person.persona_key).where(Person.id == actor.person_id))
    try:
        tokens = await rotate_session(db, current, new_actor.person_id)
    except SessionGoneError:
        # Ended in another tab, rotated by another request, or expired since the lookup.
        log_security_event(
            SecurityEvent.SESSION_INVALID,
            request,
            "unknown or expired session",
            tenant_id=actor.tenant_id,
            actor_id=actor.person_id,
        )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, NOT_SIGNED_IN) from None
    await record_event(
        db,
        tenant_id=actor.tenant_id,
        actor_id=actor.person_id,
        action="session.persona_switched",
        target_type="person",
        target_id=new_actor.person_id,
        before={"personaKey": switching_from},
        after={"personaKey": choice.persona},
    )
    set_session_cookies(response, tokens, current.expires_at)
    return await get_me(db, new_actor, current.expires_at)


@router.delete(
    "/session",
    operation_id="endSession",
    summary="Sign out: end the session and clear its cookies",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def sign_out(signed_in: SignedInDep, response: Response) -> None:
    ended = await end_session(signed_in.db, signed_in.session.token_hash)
    # A session that was already gone (ended in another tab) still gets its cookies cleared, but
    # that request ended nothing, so it writes no second `session.ended` event.
    if ended:
        await record_event(
            signed_in.db,
            tenant_id=signed_in.actor.tenant_id,
            actor_id=signed_in.actor.person_id,
            action="session.ended",
        )
    clear_session_cookies(response)
