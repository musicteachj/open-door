"""The public flag: is the live assistant available. It needs no session and is cached."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.ai.admission import room_needed_usd
from app.ai.context import actor_view
from app.ai.conversations import CURRENT_PINS
from app.db.models import HandbookVersion
from app.db.tenancy import TenantContext, tenant_session
from app.modules.assistant.availability import LANDING_ROOM_USD
from app.modules.handbook.search import pinned_version_id
from app.modules.identity.actor import load_actor
from app.modules.people.queries import get_me
from tests.integration.conftest import OpenBrowserWith
from tests.integration.test_assistant_routes import sign_in, todays_spend_usd

pytestmark = [
    pytest.mark.integration,
    pytest.mark.usefixtures("daily_ledger_untouched"),
]

URL = "/api/v1/assistant/availability"


async def test_the_flag_needs_no_session(open_browser_with: OpenBrowserWith) -> None:
    browser = open_browser_with()

    response = browser.client.get(URL)

    assert response.status_code == 200
    assert isinstance(response.json()["available"], bool)


async def test_the_flag_is_cacheable(open_browser_with: OpenBrowserWith) -> None:
    browser = open_browser_with()

    response = browser.client.get(URL)

    assert response.headers["cache-control"] == "public, max-age=30"


async def test_the_flag_is_false_when_the_month_is_used(
    open_browser_with: OpenBrowserWith,
) -> None:
    browser = open_browser_with(ai_monthly_budget_usd=Decimal(0))

    assert browser.client.get(URL).json() == {"available": False}


async def test_the_flag_is_false_when_today_has_less_than_a_question(
    open_browser_with: OpenBrowserWith, owner_engine: AsyncEngine
) -> None:
    browser = open_browser_with(
        ai_daily_budget_usd=await todays_spend_usd(owner_engine) + Decimal("0.10")
    )

    assert browser.client.get(URL).json() == {"available": False}


async def test_the_flag_is_true_with_room(
    open_browser_with: OpenBrowserWith, owner_engine: AsyncEngine
) -> None:
    browser = open_browser_with(
        ai_monthly_budget_usd=None,
        ai_daily_budget_usd=await todays_spend_usd(owner_engine) + Decimal("1.00"),
    )

    assert browser.client.get(URL).json() == {"available": True}


async def test_the_landing_room_covers_a_first_question(
    open_browser_with: OpenBrowserWith, app_engine: AsyncEngine
) -> None:
    """A first question from a new sandbox fits under the threshold, and the threshold is not so
    large that it stops being meaningful."""
    browser = open_browser_with()
    tenant_id, person_id = sign_in(browser)
    async with tenant_session(app_engine, TenantContext(tenant_id, person_id)) as db:
        actor = await load_actor(db, tenant_id, person_id)
        assert actor is not None
        me = await get_me(db, actor, datetime.now(UTC))
        label = (
            await db.scalars(
                select(HandbookVersion.label).where(
                    HandbookVersion.id == await pinned_version_id(db)
                )
            )
        ).one()

    needed = room_needed_usd(
        model=CURRENT_PINS.model,
        guard_model=CURRENT_PINS.guard_model,
        effort=CURRENT_PINS.effort,
        history=[],
        question="How many sick days do I get?",
        actor_view=actor_view(me),
        handbook_label=label,
        now=datetime.now(UTC),
    )

    assert needed <= LANDING_ROOM_USD
    assert needed > Decimal("0.15")


async def test_a_database_error_is_a_503_availability_unknown(
    open_browser_with: OpenBrowserWith, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sqlalchemy.exc import OperationalError

    async def down(*_args: object) -> bool:
        raise OperationalError("select 1", {}, ConnectionError("down"))

    monkeypatch.setattr("app.modules.assistant.routes.live_assistant_available", down)
    browser = open_browser_with()

    response = browser.client.get(URL)

    assert response.status_code == 503
    assert response.json()["type"] == "availability-unknown"
