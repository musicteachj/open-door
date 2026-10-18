"""The browser tests' cleanup deletes the daily AI ledger rows a run created, and nothing older.

A stopped or failed turn keeps its model reservation, and the daily ledger has no tenant, so a
browser run leaves its reservations behind when its sandboxes are cleaned up. The script deletes
rows from a given moment on, as the database owner. These tests run it as the browser run's
teardown does, as a separate process.
"""

import asyncio
import os
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("daily_ledger_untouched")]

API_DIR = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Run:
    returncode: int | None
    stdout: str
    stderr: str


async def run_script(*arguments: str) -> Run:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "scripts/clear_browser_test_spend.py",
        *arguments,
        cwd=API_DIR,
        env=dict(os.environ),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    return Run(process.returncode, stdout.decode(), stderr.decode())


async def add_row(owner_engine: AsyncEngine, amount: str) -> UUID:
    async with owner_engine.begin() as connection:
        row_id: UUID = (
            await connection.execute(
                text(
                    "INSERT INTO ai_spend_daily (kind, amount_usd)"
                    " VALUES ('reserve', CAST(:amount AS numeric)) RETURNING id"
                ),
                {"amount": amount},
            )
        ).scalar_one()
    return row_id


async def database_clock(owner_engine: AsyncEngine) -> datetime:
    async with owner_engine.connect() as connection:
        moment: datetime = (await connection.execute(text("SELECT clock_timestamp()"))).scalar_one()
    return moment


async def still_there(owner_engine: AsyncEngine, ids: Sequence[UUID]) -> set[UUID]:
    async with owner_engine.connect() as connection:
        rows = await connection.execute(
            text("SELECT id FROM ai_spend_daily WHERE id = ANY(CAST(:ids AS uuid[]))"),
            {"ids": list(ids)},
        )
        return set(rows.scalars())


async def test_rows_from_since_on_are_deleted_and_older_rows_are_kept(
    owner_engine: AsyncEngine,
) -> None:
    older = await add_row(owner_engine, "0.011")
    since = await database_clock(owner_engine)
    newer_a = await add_row(owner_engine, "0.022")
    newer_b = await add_row(owner_engine, "0.033")

    run = await run_script("--since", since.isoformat())

    assert run.returncode == 0, run.stdout + run.stderr
    assert await still_there(owner_engine, [older, newer_a, newer_b]) == {older}
    # It says how many it deleted and what they added up to. Rows from anything else that used the
    # database since then go too, so these are at least the two rows added here.
    said = re.search(r"Deleted (\d+) .* \$([0-9.]+)\.", run.stdout)
    assert said is not None, run.stdout
    assert int(said.group(1)) >= 2
    assert Decimal(said.group(2)) >= Decimal("0.055")


async def test_it_accepts_a_utc_timestamp_ending_in_z(owner_engine: AsyncEngine) -> None:
    since = await database_clock(owner_engine)
    added = await add_row(owner_engine, "0.044")

    run = await run_script("--since", since.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"))

    assert run.returncode == 0, run.stdout + run.stderr
    assert await still_there(owner_engine, [added]) == set()


async def test_a_since_more_than_24_hours_old_is_refused_and_deletes_nothing(
    owner_engine: AsyncEngine,
) -> None:
    added = await add_row(owner_engine, "0.011")
    too_old = (await database_clock(owner_engine)) - timedelta(hours=24, minutes=1)

    run = await run_script("--since", too_old.isoformat())

    assert run.returncode != 0
    assert "24 hours" in run.stdout + run.stderr
    assert await still_there(owner_engine, [added]) == {added}


async def test_a_since_just_inside_24_hours_is_allowed(owner_engine: AsyncEngine) -> None:
    added = await add_row(owner_engine, "0.011")
    recent = (await database_clock(owner_engine)) - timedelta(hours=23, minutes=59)

    run = await run_script("--since", recent.isoformat())

    assert run.returncode == 0, run.stdout + run.stderr
    assert await still_there(owner_engine, [added]) == set()


async def test_without_since_it_refuses_and_deletes_nothing(owner_engine: AsyncEngine) -> None:
    added = await add_row(owner_engine, "0.011")

    run = await run_script()

    assert run.returncode == 2
    assert "--since" in run.stderr
    assert await still_there(owner_engine, [added]) == {added}


@pytest.mark.parametrize("since", ["yesterday", "2026-10-18", "2026-10-18T12:00:00", ""])
async def test_a_since_that_is_not_a_utc_timestamp_is_refused(
    owner_engine: AsyncEngine, since: str
) -> None:
    # A date alone and a time with no zone are refused: a wrong guess about the zone would delete
    # the wrong rows.
    added = await add_row(owner_engine, "0.011")

    run = await run_script("--since", since)

    assert run.returncode != 0
    assert await still_there(owner_engine, [added]) == {added}


async def test_now_prints_the_database_clock_and_deletes_nothing(
    owner_engine: AsyncEngine,
) -> None:
    added = await add_row(owner_engine, "0.011")
    before = await database_clock(owner_engine)

    run = await run_script("--now")

    after = await database_clock(owner_engine)
    assert run.returncode == 0, run.stdout + run.stderr
    printed = datetime.fromisoformat(run.stdout.strip())
    assert printed.tzinfo is not None
    assert before <= printed <= after
    assert await still_there(owner_engine, [added]) == {added}


async def test_since_and_now_cannot_be_combined(owner_engine: AsyncEngine) -> None:
    added = await add_row(owner_engine, "0.011")
    since = (await database_clock(owner_engine)).isoformat()

    run = await run_script("--since", since, "--now")

    assert run.returncode == 2
    assert await still_there(owner_engine, [added]) == {added}
