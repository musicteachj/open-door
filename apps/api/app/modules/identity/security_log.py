"""Refused requests, recorded in the JSON application log under the `app.security` logger.

Failures go here, not to the audit table: the audit log records what people did, and this records
what they were stopped from doing. Each event carries the request ID, the tenant and actor when
they are known, the client's IP address, and the first 8 characters of the session token's hash,
which is enough to connect events from one session. A raw token is never logged.
"""

import logging
from enum import StrEnum
from uuid import UUID

from starlette.requests import HTTPConnection

from app.core.request_id import request_id_var
from app.modules.identity.cookies import SESSION_COOKIE
from app.modules.identity.tokens import hash_token

logger = logging.getLogger("app.security")

TOKEN_HASH_PREFIX_LENGTH = 8


class SecurityEvent(StrEnum):
    SESSION_INVALID = "security.session_invalid"
    ORIGIN_REJECTED = "security.origin_rejected"
    CSRF_REJECTED = "security.csrf_rejected"
    AUTHZ_DENIED = "security.authz_denied"


def log_security_event(
    event: SecurityEvent,
    request: HTTPConnection,
    reason: str,
    *,
    tenant_id: UUID | None = None,
    actor_id: UUID | None = None,
    target_id: UUID | None = None,
) -> None:
    """Log one refused request. `reason` is a fixed phrase, never text from the request."""
    token = request.cookies.get(SESSION_COOKIE)
    fields = {
        "event": event.value,
        "reason": reason,
        "tenantId": None if tenant_id is None else str(tenant_id),
        "actorId": None if actor_id is None else str(actor_id),
        "targetId": None if target_id is None else str(target_id),
        "clientIp": None if request.client is None else request.client.host,
        "tokenHashPrefix": hash_token(token).hex()[:TOKEN_HASH_PREFIX_LENGTH] if token else None,
    }
    logger.warning(event.value, extra={"request_id": request_id_var.get(), "fields": fields})
