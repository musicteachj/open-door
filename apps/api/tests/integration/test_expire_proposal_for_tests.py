"""The browser tests' script that makes a confirm card expire without a 15-minute wait.

It moves a pending proposal's created_at and expires_at back by 16 minutes, as the database
owner, and refuses a database that is not on this machine. These tests run it as a separate
process, the way the browser test does.
"""

import asyncio
import os
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.ai.proposals import Conflict
from tests.integration.conftest import MakeTenant
from tests.integration.test_proposals import (
    confirm_as,
    make_chat,
    propose_request,
    ready,
    row_of,
)
from tests.integration.test_timeoff_service import pto

pytestmark = pytest.mark.integration

API_DIR = Path(__file__).resolve().parents[2]
MON_NOV_9 = date(2026, 11, 9)


@dataclass(frozen=True)
class Run:
    returncode: int | None
    output: str


async def run_script(proposal_id: str, **env: str) -> Run:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "scripts/expire_proposal_for_tests.py",
        proposal_id,
        cwd=API_DIR,
        env={**os.environ, **env},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await process.communicate()
    return Run(process.returncode, stdout.decode())


async def test_it_expires_a_pending_card_so_the_next_confirm_is_refused(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    org = await ready(app_engine, make_tenant)
    chat = await make_chat(app_engine, org.tenant.id, org.report)
    proposal_id = await propose_request(app_engine, org.tenant.id, org.report, chat, pto(MON_NOV_9))
    before = await row_of(owner_engine, proposal_id)

    run = await run_script(str(proposal_id))

    assert run.returncode == 0, run.output
    after = await row_of(owner_engine, proposal_id)
    assert after["expires_at"] < before["expires_at"]
    assert before["expires_at"] - after["expires_at"] == before["created_at"] - after["created_at"]
    assert after["status"] == "pending"
    result = await confirm_as(app_engine, org.tenant.id, org.report, proposal_id)
    assert isinstance(result, Conflict)
    assert result.status == "expired"


async def test_it_leaves_a_proposal_that_already_ended_alone(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    org = await ready(app_engine, make_tenant)
    chat = await make_chat(app_engine, org.tenant.id, org.report)
    proposal_id = await propose_request(app_engine, org.tenant.id, org.report, chat, pto(MON_NOV_9))
    await confirm_as(app_engine, org.tenant.id, org.report, proposal_id)
    before = await row_of(owner_engine, proposal_id)

    run = await run_script(str(proposal_id))

    assert run.returncode != 0
    assert "No pending proposal" in run.output
    assert await row_of(owner_engine, proposal_id) == before


async def test_it_refuses_a_proposal_that_does_not_exist() -> None:
    run = await run_script(str(uuid4()))

    assert run.returncode != 0
    assert "No pending proposal" in run.output


async def test_it_refuses_something_that_is_not_an_id() -> None:
    run = await run_script("not-an-id")

    assert run.returncode == 2


@pytest.mark.parametrize("host", ["db.example.com", "10.0.0.5", "opendoor.internal"])
async def test_it_refuses_a_database_that_is_not_on_this_machine(host: str) -> None:
    run = await run_script(
        str(uuid4()),
        MIGRATION_DATABASE_URL=f"postgresql+asyncpg://opendoor:opendoor@{host}:5432/opendoor",
    )

    assert run.returncode != 0
    assert "not this machine" in run.output


@pytest.mark.parametrize("parameter", ["host=db.example.com", "hostaddr=10.0.0.5"])
async def test_it_refuses_a_url_whose_query_names_another_host(parameter: str) -> None:
    # A libpq-style `host` in the query overrides the URL's own host, so a local-looking URL could
    # still reach a remote database.
    run = await run_script(
        str(uuid4()),
        MIGRATION_DATABASE_URL=(
            f"postgresql+asyncpg://opendoor:opendoor@127.0.0.1:5433/opendoor?{parameter}"
        ),
    )

    assert run.returncode != 0
    assert "host" in run.output
    assert "Nothing was changed" in run.output


async def test_it_refuses_to_run_in_production() -> None:
    run = await run_script(str(uuid4()), APP_ENV="production")

    assert run.returncode != 0
    assert "production" in run.output
    assert "Nothing was changed" in run.output
