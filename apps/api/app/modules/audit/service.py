"""record_event: a row in the append-only audit log for each action taken in a sandbox.

Each row carries the request's ID, so it can be matched with that request's log lines. `before`
and `after` hold directory fields only. A read of private details records the names of the fields
it returned, never their values, so a privacy deletion request never means editing this log. A
person's free text, such as a denial's note, is never recorded either.

Refused requests are not audited here. They go to the security log (see
app/modules/identity/security_log.py).
"""

from collections.abc import Mapping
from typing import Literal
from uuid import UUID

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.request_id import request_id_var
from app.db.models import AuditEvent, PersonPrivate

type AuditAction = Literal[
    "sandbox.created",
    "session.persona_switched",
    "session.ended",
    "person_private.read",
    "escalation.offered",
    "timeoff.requested",
    "timeoff.recorded",
    "timeoff.approved",
    "timeoff.denied",
    "timeoff.canceled",
    "proposal.created",
    "proposal.confirmed",
    "proposal.canceled",
    "proposal.failed",
]
type Via = Literal["ui", "assistant", "system"]


def _normalized(key: object) -> str:
    """A key without case, underscores, or other punctuation: `home_address`, `homeAddress`, and
    `HOME-ADDRESS` all become `homeaddress`."""
    return "".join(char for char in str(key).lower() if char.isalnum())


# Every private column, in the one form that all its spellings normalize to. The two ID columns
# say whose details a row holds and are not private themselves.
_PRIVATE_KEYS = frozenset(
    _normalized(column.name)
    for column in PersonPrivate.__table__.columns
    if column.name not in {"person_id", "tenant_id"}
)

# Text a person wrote, which never belongs in the log: a denial's note (`decision_note` is the
# column, `note` the field name the service and the routes use).
_FREE_TEXT_KEYS = frozenset({"decisionnote", "note"})
_REFUSED_KEYS = _PRIVATE_KEYS | _FREE_TEXT_KEYS


def _hides_a_private_field(value: object) -> bool:
    """Whether any dict inside `value`, however deep, has a private or free-text field name as a
    key.

    Only keys count. Field *names* as values, such as `{"fields": ["phone"]}`, are what a read of
    private details records.
    """
    if isinstance(value, Mapping):
        return any(
            _normalized(key) in _REFUSED_KEYS or _hides_a_private_field(item)
            for key, item in value.items()
        )
    if isinstance(value, list | tuple | set | frozenset):
        return any(_hides_a_private_field(item) for item in value)
    return False


async def record_event(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    actor_id: UUID | None,
    action: AuditAction,
    target_type: str | None = None,
    target_id: UUID | None = None,
    before: Mapping[str, object] | None = None,
    after: Mapping[str, object] | None = None,
    via: Via = "ui",
    proposal_id: UUID | None = None,
) -> None:
    """Add the event in the caller's transaction, so it commits or rolls back with the action."""
    # Turned into plain dicts first, so what is checked is exactly what is stored.
    before_json = None if before is None else dict(before)
    after_json = None if after is None else dict(after)
    if _hides_a_private_field(before_json) or _hides_a_private_field(after_json):
        msg = (
            "An audit event's before and after hold directory fields only, never private ones"
            " or a person's notes"
        )
        raise ValueError(msg)
    await session.execute(
        insert(AuditEvent).values(
            tenant_id=tenant_id,
            actor_person_id=actor_id,
            via=via,
            proposal_id=proposal_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            before=before_json,
            after=after_json,
            request_id=request_id_var.get(),
        )
    )
