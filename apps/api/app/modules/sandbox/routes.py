"""POST /api/v1/sandboxes: start a new sandbox company and sign in to it."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api.deps import get_engine
from app.api.schemas import CamelModel
from app.modules.identity.cookies import SESSION_COOKIE, set_session_cookies
from app.modules.identity.tokens import hash_token
from app.modules.people.schemas import Me, PersonaKey
from app.modules.sandbox.service import create_sandbox

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
)
async def post_sandbox(
    request: Request,
    response: Response,
    engine: Annotated[AsyncEngine, Depends(get_engine)],
    body: NewSandboxRequest | None = None,
) -> SandboxCreated:
    # The same-origin check has already run. There is no CSRF token to check: a visitor without a
    # session has none, and this creates the session.
    persona = body.persona if body is not None else "priya"
    current = request.cookies.get(SESSION_COOKIE)
    sandbox = await create_sandbox(engine, persona, hash_token(current) if current else None)
    set_session_cookies(response, sandbox.tokens, sandbox.expires_at)
    return SandboxCreated(
        tenant=TenantInfo(id=sandbox.tenant_id, expires_at=sandbox.expires_at), me=sandbox.me
    )
