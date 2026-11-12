"""POST /api/v1/sandboxes: start a new sandbox company and sign in to it."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api.deps import get_app_settings, get_engine, get_keys, get_turnstile
from app.api.problems import problem_responses
from app.api.schemas import CamelModel
from app.core.config import Settings
from app.core.encryption import KeyProvider
from app.core.problems import ProblemError
from app.modules.identity.cookies import SESSION_COOKIE, set_session_cookies
from app.modules.identity.tokens import hash_token
from app.modules.people.schemas import Me, PersonaKey
from app.modules.sandbox import texts
from app.modules.sandbox.limits import StartLimitError, StartLimits, address_hash
from app.modules.sandbox.service import HandbookNotLoadedError, create_sandbox
from app.modules.sandbox.turnstile import TurnstileVerifier, Verdict

router = APIRouter(tags=["sandboxes"])


class NewSandboxRequest(CamelModel):
    persona: PersonaKey = "priya"
    # The Turnstile token the page's widget produced. Cloudflare's tokens are at most 2,048
    # characters. Empty is allowed here so the check refuses it with its own text.
    turnstile_token: Annotated[str, Field(max_length=2048)]


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
    # A 403 is the same-origin check refusing a cross-site request, or the person check failing
    # (`turnstile-failed`). A 429 is `sandbox-start-limit` (this address) or `sandbox-day-limit`
    # (all addresses today), with `Retry-After`. A 503 is `turnstile-unavailable` (the check
    # couldn't run), or no handbook version is published yet.
    responses=problem_responses(
        status.HTTP_403_FORBIDDEN,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        status.HTTP_429_TOO_MANY_REQUESTS,
        status.HTTP_503_SERVICE_UNAVAILABLE,
    ),
)
async def post_sandbox(
    request: Request,
    response: Response,
    engine: Annotated[AsyncEngine, Depends(get_engine)],
    keys: Annotated[KeyProvider, Depends(get_keys)],
    settings: Annotated[Settings, Depends(get_app_settings)],
    turnstile: Annotated[TurnstileVerifier, Depends(get_turnstile)],
    body: NewSandboxRequest,
) -> SandboxCreated:
    # The same-origin check has already run. There is no CSRF token to check: a visitor without a
    # session has none, and this creates the session.
    #
    # The person check comes first, before anything is counted or the old session is touched. The
    # address is the one uvicorn put in `client`, which it takes from X-Forwarded-For only for
    # FORWARDED_ALLOW_IPS.
    address = request.client.host if request.client is not None else None
    verdict = await turnstile.verify(body.turnstile_token, address)
    if verdict is Verdict.UNAVAILABLE:
        raise ProblemError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "turnstile-unavailable",
            texts.TURNSTILE_UNAVAILABLE_TEXT,
        )
    if verdict is not Verdict.PASSED:
        raise ProblemError(
            status.HTTP_403_FORBIDDEN, "turnstile-failed", texts.TURNSTILE_FAILED_TEXT
        )
    ip_hash = address_hash(settings.sandbox_ip_hash_key.get_secret_value().encode(), address)
    limits = StartLimits(
        per_hour=settings.sandbox_starts_per_hour,
        per_day=settings.sandbox_starts_per_day,
        daily_total=settings.sandbox_starts_daily_total,
    )
    current = request.cookies.get(SESSION_COOKIE)
    try:
        # The limits are counted before the old session ends, so a refused visitor keeps the
        # sandbox they have.
        sandbox = await create_sandbox(
            engine,
            body.persona,
            hash_token(current) if current else None,
            keys,
            ip_hash,
            limits,
        )
    except StartLimitError as limit:
        raise _limit_problem(limit) from None
    except HandbookNotLoadedError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "The handbook isn't loaded yet."
        ) from None
    set_session_cookies(response, sandbox.tokens, sandbox.expires_at)
    return SandboxCreated(
        tenant=TenantInfo(id=sandbox.tenant_id, expires_at=sandbox.expires_at), me=sandbox.me
    )


def _limit_problem(limit: StartLimitError) -> ProblemError:
    headers = {"Retry-After": str(limit.retry_after_seconds)}
    if limit.scope == "day":
        return ProblemError(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "sandbox-day-limit",
            texts.DAY_LIMIT_TEXT,
            headers=headers,
        )
    return ProblemError(
        status.HTTP_429_TOO_MANY_REQUESTS,
        "sandbox-start-limit",
        texts.START_LIMIT_TEXT.format(wait=texts.wait_phrase(limit.retry_after_seconds)),
        headers=headers,
    )
