"""The cleanup job (`python -m app.jobs.cleanup`) deletes what has outlived its retention.

It runs as the cleanup login. Rows the API's login can't backdate (the ledger, the start counter,
and handbook versions) are made as the database owner. The database is shared with the other
tests, so every assertion looks at the rows this test made, by ID, and never at the whole table.
"""

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.errors import has_sqlstate
from app.jobs.cleanup import STEP_TIMEOUT, run, run_cleanup, step
from tests.integration.conftest import MakeTenant
from tests.integration.test_cleanup import rows_left

pytestmark = pytest.mark.integration

OLD = datetime(2000, 1, 1, tzinfo=UTC)


async def insert_spend(owner_engine: AsyncEngine, *, days_ago: int) -> UUID:
    """A ledger row dated `days_ago` days back (UTC). A trigger stamps created_at, and a check ties
    `day` to it, so the row is made and then moved, as the owner."""
    row_id = uuid4()
    moment = datetime.now(UTC).replace(hour=12, minute=0, second=0, microsecond=0) - timedelta(
        days=days_ago
    )
    async with owner_engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO ai_spend_daily (id, kind, amount_usd) VALUES (:id, 'settle', 0.000001)"
            ),
            {"id": row_id},
        )
        await connection.execute(
            text(
                "UPDATE ai_spend_daily SET created_at = :moment,"
                " day = (CAST(:moment AS timestamptz) AT TIME ZONE 'UTC')::date WHERE id = :id"
            ),
            {"id": row_id, "moment": moment},
        )
    return row_id


async def insert_start(owner_engine: AsyncEngine, *, hours_ago: float) -> UUID:
    row_id = uuid4()
    async with owner_engine.begin() as connection:
        await connection.execute(
            text("INSERT INTO sandbox_starts (id, ip_hash) VALUES (:id, :hash)"),
            {"id": row_id, "hash": b"\x01" * 32},
        )
        await connection.execute(
            text(
                "UPDATE sandbox_starts SET created_at = now() - make_interval(secs => :secs)"
                " WHERE id = :id"
            ),
            {"id": row_id, "secs": hours_ago * 3600},
        )
    return row_id


async def insert_version(
    owner_engine: AsyncEngine,
    *,
    created_at: datetime,
    published_at: datetime | None,
) -> UUID:
    version_id = uuid4()
    async with owner_engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO handbook_versions (id, label, content_hash, embedding_model,"
                " embedding_dimensions, updated_on, created_at, published_at) VALUES (:id,"
                " :label, :label, 'voyage-4', 1024, '2026-10-01', :created, :published)"
            ),
            {
                "id": version_id,
                "label": f"cleanup-test-{version_id}",
                "created": created_at,
                "published": published_at,
            },
        )
        await connection.execute(
            text(
                "INSERT INTO handbook_sections (version_id, section_key, position, kind, chapter,"
                " title, audience, updated_on, sources, blocks) VALUES (:id, '9.9', 0, 'company',"
                " 9, 'Cleanup test', '{}'::jsonb, '2026-10-01', '[]'::jsonb, '[]'::jsonb)"
            ),
            {"id": version_id},
        )
    return version_id


async def count_where(owner_engine: AsyncEngine, table: str, ids: list[UUID]) -> int:
    async with owner_engine.connect() as connection:
        return int(
            await connection.scalar(
                text(f"SELECT count(*) FROM {table} WHERE id = ANY(:ids)"),  # noqa: S608
                {"ids": ids},
            )
            or 0
        )


async def sections_of(owner_engine: AsyncEngine, version_id: UUID) -> int:
    async with owner_engine.connect() as connection:
        return int(
            await connection.scalar(
                text("SELECT count(*) FROM handbook_sections WHERE version_id = :id"),
                {"id": version_id},
            )
            or 0
        )


async def newest_published_id(owner_engine: AsyncEngine) -> UUID:
    async with owner_engine.connect() as connection:
        newest = await connection.scalar(
            text(
                "SELECT id FROM handbook_versions WHERE published_at IS NOT NULL"
                " ORDER BY published_at DESC, created_at DESC, id DESC LIMIT 1"
            )
        )
    assert isinstance(newest, UUID), "the handbook must be loaded (make db)"
    return newest


@pytest.fixture
async def versions_to_remove(owner_engine: AsyncEngine) -> AsyncIterator[list[UUID]]:
    """Versions a test made, deleted afterward whether or not the job did (a tenant may pin one,
    so the tenants go first in the test, and anything left is removed here)."""
    made: list[UUID] = []
    yield made
    async with owner_engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE tenants SET handbook_version_id = (SELECT id FROM handbook_versions"
                " WHERE published_at IS NOT NULL ORDER BY published_at DESC, created_at DESC,"
                " id DESC LIMIT 1) WHERE handbook_version_id = ANY(:ids)"
            ),
            {"ids": made},
        )
        await connection.execute(
            text("DELETE FROM handbook_versions WHERE id = ANY(:ids)"), {"ids": made}
        )


async def test_the_job_deletes_an_expired_sandbox_and_all_its_rows_but_no_live_one(
    cleanup_engine: AsyncEngine, owner_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    live, expired = await make_tenant(), await make_tenant(expired=True)
    live_before = await rows_left(owner_engine, live.id)
    expired_before = await rows_left(owner_engine, expired.id)

    counts = await run_cleanup(cleanup_engine)

    assert counts.tenants >= 1
    assert await rows_left(owner_engine, expired.id) == dict.fromkeys(expired_before, 0)
    assert await rows_left(owner_engine, live.id) == live_before


async def test_the_job_keeps_thirty_days_of_ledger_rows(
    cleanup_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    old = [await insert_spend(owner_engine, days_ago=days) for days in (31, 45)]
    kept = [await insert_spend(owner_engine, days_ago=days) for days in (30, 1, 0)]
    try:
        counts = await run_cleanup(cleanup_engine)

        assert counts.spend_rows >= 2
        assert await count_where(owner_engine, "ai_spend_daily", old) == 0
        assert await count_where(owner_engine, "ai_spend_daily", kept) == 3
    finally:
        async with owner_engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM ai_spend_daily WHERE id = ANY(:ids)"), {"ids": kept}
            )


async def test_the_job_keeps_a_days_worth_of_start_counts(
    cleanup_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    old = await insert_start(owner_engine, hours_ago=25)
    kept = [await insert_start(owner_engine, hours_ago=hours) for hours in (23, 1, 0)]
    try:
        counts = await run_cleanup(cleanup_engine)

        assert counts.starts >= 1
        assert await count_where(owner_engine, "sandbox_starts", [old]) == 0
        assert await count_where(owner_engine, "sandbox_starts", kept) == 3
    finally:
        async with owner_engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM sandbox_starts WHERE id = ANY(:ids)"), {"ids": kept}
            )


async def test_the_job_deletes_unused_old_handbook_versions_and_keeps_the_rest(
    cleanup_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    make_tenant: MakeTenant,
    versions_to_remove: list[UUID],
) -> None:
    newest = await newest_published_id(owner_engine)
    old_published = await insert_version(
        owner_engine, created_at=OLD, published_at=OLD + timedelta(days=1)
    )
    old_unpublished = await insert_version(owner_engine, created_at=OLD, published_at=None)
    pinned = await insert_version(
        owner_engine, created_at=OLD, published_at=OLD + timedelta(days=2)
    )
    still_loading = await insert_version(
        owner_engine, created_at=datetime.now(UTC) + timedelta(days=1), published_at=None
    )
    versions_to_remove.extend([old_published, old_unpublished, pinned, still_loading])
    sandbox = await make_tenant()
    async with owner_engine.begin() as connection:
        await connection.execute(
            text("UPDATE tenants SET handbook_version_id = :version WHERE id = :id"),
            {"version": pinned, "id": sandbox.id},
        )

    try:
        counts = await run_cleanup(cleanup_engine)

        assert counts.handbook_versions >= 2
        assert counts.handbook_versions_skipped >= 1
        ids = [old_published, old_unpublished]
        assert await count_where(owner_engine, "handbook_versions", ids) == 0
        for deleted in ids:
            assert await sections_of(owner_engine, deleted) == 0
        for kept in (newest, pinned, still_loading):
            assert await count_where(owner_engine, "handbook_versions", [kept]) == 1
        assert await sections_of(owner_engine, pinned) == 1
    finally:
        async with owner_engine.begin() as connection:
            await connection.execute(text("DELETE FROM tenants WHERE id = :id"), {"id": sandbox.id})


async def test_each_step_runs_with_a_sixty_second_statement_timeout(
    cleanup_engine: AsyncEngine,
) -> None:
    assert STEP_TIMEOUT == "60s"
    async with cleanup_engine.connect() as connection:
        assert await connection.scalar(text("SHOW statement_timeout")) == "10s"
    async with step(cleanup_engine) as connection:
        assert await connection.scalar(text("SHOW statement_timeout")) == "1min"


async def test_the_job_logs_one_json_line_of_counts_exits_zero_and_a_second_run_finds_nothing(
    capsys: pytest.CaptureFixture[str], owner_engine: AsyncEngine
) -> None:
    await insert_start(owner_engine, hours_ago=30)
    await insert_spend(owner_engine, days_ago=40)

    assert await run() == 0
    first = [line for line in capsys.readouterr().err.splitlines() if line.strip()]

    assert len(first) == 1
    entry = json.loads(first[0])
    assert entry["message"] == "cleanup finished"
    assert entry["starts"] >= 1
    assert entry["spendRows"] >= 1
    assert {"tenants", "handbookVersions", "handbookVersionsSkipped"} <= entry.keys()

    assert await run() == 0
    second = json.loads(capsys.readouterr().err.strip())
    assert [second[key] for key in ("tenants", "spendRows", "starts", "handbookVersions")] == [
        0,
        0,
        0,
        0,
    ]


async def test_a_failure_is_logged_without_the_url_and_exits_nonzero(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLEANUP_DATABASE_URL", "postgresql+asyncpg://nobody:hunter2@127.0.0.1:1/x")

    assert await run() == 1
    err = capsys.readouterr().err
    assert "cleanup failed" in err
    assert "hunter2" not in err


async def test_the_cleanup_login_itself_cannot_delete_a_recent_ledger_row_or_start(
    cleanup_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    spend = await insert_spend(owner_engine, days_ago=29)
    start = await insert_start(owner_engine, hours_ago=1)
    try:
        async with cleanup_engine.begin() as connection:
            spend_result = await connection.execute(
                text("DELETE FROM ai_spend_daily WHERE id = :id"), {"id": spend}
            )
            start_result = await connection.execute(
                text("DELETE FROM sandbox_starts WHERE id = :id"), {"id": start}
            )
        assert (spend_result.rowcount, start_result.rowcount) == (0, 0)
        assert await count_where(owner_engine, "ai_spend_daily", [spend]) == 1
        assert await count_where(owner_engine, "sandbox_starts", [start]) == 1
    finally:
        async with owner_engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM ai_spend_daily WHERE id = :id"), {"id": spend}
            )
            await connection.execute(
                text("DELETE FROM sandbox_starts WHERE id = :id"), {"id": start}
            )


async def test_the_cleanup_login_itself_cannot_delete_the_newest_published_version(
    cleanup_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    newest = await newest_published_id(owner_engine)

    with pytest.raises(DBAPIError) as refused:
        async with cleanup_engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM handbook_versions WHERE id = :id"), {"id": newest}
            )

    assert has_sqlstate(refused.value, "OD006")
    assert await count_where(owner_engine, "handbook_versions", [newest]) == 1


async def test_the_api_login_still_reads_and_adds_ledger_rows(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    async with app_engine.begin() as connection:
        row_id: UUID = (
            await connection.execute(
                text(
                    "INSERT INTO ai_spend_daily (kind, amount_usd) VALUES ('reserve', 0)"
                    " RETURNING id"
                )
            )
        ).scalar_one()
        seen = await connection.scalar(
            text("SELECT count(*) FROM ai_spend_daily WHERE id = :id"), {"id": row_id}
        )
    try:
        assert seen == 1
        with pytest.raises(DBAPIError):
            async with app_engine.begin() as connection:
                await connection.execute(
                    text("DELETE FROM ai_spend_daily WHERE id = :id"), {"id": row_id}
                )
    finally:
        async with owner_engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM ai_spend_daily WHERE id = :id"), {"id": row_id}
            )
