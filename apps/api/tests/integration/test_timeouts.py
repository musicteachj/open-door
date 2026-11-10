"""The database timeouts: statement and idle-in-transaction on every connection, the confirm's lock
timeout, and the bootstrap script's role-level copy of the same values."""

import asyncio
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

import app.ai.proposals as proposals
from app.core.config import Settings
from app.core.problems import install_problem_handlers
from app.db.engine import create_engine
from app.db.errors import has_sqlstate
from app.db.locks import TIMEOFF_PERSON_NS
from tests.integration.conftest import OpenBrowser
from tests.integration.test_bootstrap import run_bootstrap
from tests.integration.test_proposal_routes import (
    book,
    confirm_path,
    post,
)
from tests.integration.test_proposals import row_of
from tests.integration.test_timeoff_routes import StartWorld, World, problem_of

pytestmark = pytest.mark.integration

QUERY_CANCELED = "57014"


@pytest.fixture
def start(
    open_browser: OpenBrowser, app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> StartWorld:
    def begin(persona: str = "priya") -> World:
        browser = open_browser()
        sandbox = browser.start_sandbox(persona)
        return World(browser, sandbox, app_engine, owner_engine, datetime.now(UTC))

    return begin


async def setting(engine: AsyncEngine, name: str) -> str:
    async with engine.connect() as connection:
        return str((await connection.execute(text(f"SHOW {name}"))).scalar_one())


async def test_the_app_engine_sets_both_timeouts_on_every_connection(
    app_engine: AsyncEngine,
) -> None:
    assert await setting(app_engine, "statement_timeout") == "10s"
    assert await setting(app_engine, "idle_in_transaction_session_timeout") == "30s"


async def test_a_statement_past_ten_seconds_is_canceled_not_left_hanging(
    app_engine: AsyncEngine,
) -> None:
    started = time.monotonic()
    with pytest.raises(DBAPIError) as raised:
        async with app_engine.connect() as connection:
            await connection.execute(text("SELECT pg_sleep(11)"))
    elapsed = time.monotonic() - started

    assert has_sqlstate(raised.value, QUERY_CANCELED)
    assert 9.5 < elapsed < 10.9


@pytest.fixture
async def impatient_engine(database_settings: Settings) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(str(database_settings.database_url), statement_timeout="200ms")
    yield engine
    await engine.dispose()


async def test_a_canceled_statement_is_a_503_problem(impatient_engine: AsyncEngine) -> None:
    app = FastAPI()
    install_problem_handlers(app)

    @app.get("/slow")
    async def slow() -> None:
        async with impatient_engine.connect() as connection:
            await connection.execute(text("SELECT pg_sleep(2)"))

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get("/slow")

    assert response.status_code == 503
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["type"] == "database-busy"
    assert "pg_sleep" not in response.text


async def test_a_held_person_lock_fails_the_confirm_cleanly_with_the_card_pending(
    start: StartWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(proposals, "CONFIRM_LOCK_TIMEOUT", "300ms")
    world = start("priya")
    await world.fund("priya")
    proposal_id = await book(world)
    person = world.person("priya")

    async with world.owner.connect() as holder:
        await holder.execute(
            text(
                f"SELECT pg_advisory_xact_lock({TIMEOFF_PERSON_NS},"
                " hashtext(CAST(:tenant AS text) || ':' || CAST(:person AS text)))"
            ),
            {"tenant": str(world.tenant_id), "person": str(person)},
        )
        started = time.monotonic()
        response = await asyncio.to_thread(post, world, confirm_path(proposal_id))
        waited = time.monotonic() - started
        await holder.rollback()

    assert problem_of(response, 503)["type"] == "database-busy"
    assert waited < 5
    row = await row_of(world.owner, proposal_id)
    assert row["status"] == "pending"
    assert row["no_outcome"]

    retry = await asyncio.to_thread(post, world, confirm_path(proposal_id))
    assert retry.status_code == 200, retry.text


def test_the_confirm_waits_five_seconds_for_a_lock_by_default() -> None:
    assert proposals.CONFIRM_LOCK_TIMEOUT == "5s"


async def test_the_bootstrap_script_sets_each_login_its_timeouts(
    database_settings: Settings, cleanup_url: str, owner_engine: AsyncEngine
) -> None:
    app_login = make_url(str(database_settings.database_url)).username
    cleanup_login = make_url(cleanup_url).username
    # Start from logins with neither setting, so the script is what puts them there.
    async with owner_engine.begin() as connection:
        for login in (app_login, cleanup_login):
            await connection.exec_driver_sql(f'ALTER ROLE "{login}" RESET ALL')
    try:
        await run_bootstrap(str(database_settings.database_url))
        configured: dict[str, list[str]] = {}
        async with owner_engine.connect() as connection:
            for login in (app_login, cleanup_login):
                configured[str(login)] = (
                    await connection.execute(
                        text(
                            "SELECT s.setconfig FROM pg_db_role_setting s JOIN pg_roles r"
                            " ON r.oid = s.setrole WHERE r.rolname = :login AND s.setdatabase = 0"
                        ),
                        {"login": login},
                    )
                ).scalar_one()
    finally:
        # Whatever happened above, leave the local logins with their settings again.
        await run_bootstrap(str(database_settings.database_url))

    assert "statement_timeout=10s" in configured[str(app_login)]
    assert "idle_in_transaction_session_timeout=30s" in configured[str(app_login)]
    # Deleting an expired sandbox cascades through every table, so its login gets a longer limit.
    assert "statement_timeout=60s" in configured[str(cleanup_login)]
    assert "idle_in_transaction_session_timeout=30s" in configured[str(cleanup_login)]
