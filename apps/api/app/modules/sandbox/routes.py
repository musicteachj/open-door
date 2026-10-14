"""POST /api/v1/sandboxes: start a new sandbox company and sign in to it."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api.deps import get_engine
from app.api.problems import problem_responses
from app.api.schemas import CamelModel
from app.modules.identity.cookies import SESSION_COOKIE, set_session_cookies
from app.modules.identity.tokens import hash_token
from app.modules.people.schemas import Me, PersonaKey
from app.modules.sandbox.service import HandbookNotLoadedError, create_sandbox

router = APIRouter(tags=["sandboxes"])


class NewSandboxRequest(CamelModel):
    persona: PersonaKey = "priya"


class TenantInfo(CamelModel):
    id: UUID
    expires_at: datetime


class SandboxCreated(CamelModel):
    tenant: TenantInfo
    me: Me


@router.post(
    "/sandboxes",
    operation_id="createSandbox",
    summary="Start a new sandbox company and sign in to it as one of its personas",
    status_code=status.HTTP_201_CREATED,
    response_model=SandboxCreated,
    # A 403 is the same-origin check refusing a cross-site request. A 503 means no handbook version
    # is published yet.
    responses=problem_responses(
        status.HTTP_403_FORBIDDEN,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        status.HTTP_503_SERVICE_UNAVAILABLE,
    ),
)
async def post_sandbox(
    request: Request,
    response: Response,
    engine: Annotated[AsyncEngine, Depends(get_engine)],
    body: NewSandboxRequest | None = None,
) -> SandboxCreated:
    # The same-origin check has already run. There is no CSRF token to check: a visitor without a
    # session has none, and this creates the session.
    persona = (body or NewSandboxRequest()).persona
    current = request.cookies.get(SESSION_COOKIE)
    try:
        sandbox = await create_sandbox(engine, persona, hash_token(current) if current else None)
    except HandbookNotLoadedError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "The handbook isn't loaded yet."
        ) from None
    set_session_cookies(response, sandbox.tokens, sandbox.expires_at)
    return SandboxCreated(
        tenant=TenantInfo(id=sandbox.tenant_id, expires_at=sandbox.expires_at), me=sandbox.me
    )
