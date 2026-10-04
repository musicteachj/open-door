"""The audit log refuses private details anywhere in `before` and `after`, however they're spelled.

Refusal happens before the database is touched, so these tests use a stand-in session.
"""

from typing import Any, cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.service import record_event

PRIVATE_PAYLOADS = {
    "top level": {"phone": "555-0100"},
    "top level, camelCase": {"homeAddress": "1 Example Street"},
    "nested dict": {"x": {"phone": "555-0100"}},
    "deeply nested": {"a": {"b": [{"c": {"date_of_birth": "1990-01-01"}}]}},
    "different case": {"Phone": "555-0100"},
    "all caps with underscores": {"HOME_ADDRESS": "1 Example Street"},
    "PascalCase": {"PersonalEmail": "priya@example.com"},
    "key inside a list of dicts": {"people": [{"given_name": "Priya"}, {"phone": "555-0100"}]},
    "key inside a tuple of dicts": {"people": ({"dateOfBirth": "1990-01-01"},)},
    "list of pairs": [("phone", "555-0100")],
    "list of pairs, camelCase": [("personalEmail", "priya@example.com")],
}

ALLOWED_PAYLOADS = {
    "persona switch": {"personaKey": "priya"},
    "private read": {"fields": ["phone", "home_address"]},
    "nested names as values": {"x": {"fields": ["phone", "dateOfBirth"]}},
    "directory fields": {"givenName": "Priya", "workEmail": "priya@opendoor.example"},
    "empty": {},
}


def stand_in_session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


async def record(session: AsyncMock, *, before: Any = None, after: Any = None) -> None:
    await record_event(
        cast("AsyncSession", session),
        tenant_id=uuid4(),
        actor_id=uuid4(),
        action="person_private.read",
        before=before,
        after=after,
    )


@pytest.mark.parametrize("payload", PRIVATE_PAYLOADS.values(), ids=PRIVATE_PAYLOADS.keys())
@pytest.mark.parametrize("side", ["before", "after"])
async def test_a_private_field_is_refused_wherever_it_hides(payload: Any, side: str) -> None:
    session = stand_in_session()

    with pytest.raises(ValueError, match="directory fields only"):
        await record(session, **{side: payload})

    session.execute.assert_not_awaited()


@pytest.mark.parametrize("payload", ALLOWED_PAYLOADS.values(), ids=ALLOWED_PAYLOADS.keys())
async def test_the_real_payloads_are_recorded(payload: dict[str, object]) -> None:
    session = stand_in_session()

    await record(session, before=payload, after=payload)

    session.execute.assert_awaited_once()
