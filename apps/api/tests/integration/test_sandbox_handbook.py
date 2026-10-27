"""A new sandbox is pinned to the newest published handbook version, by a database trigger.

The trigger (migration 0005) overrides whatever version a caller supplies and refuses to create a
tenant when no version is published. Nothing here commits a change to the handbook tables: the
tests that publish or unpublish versions do it inside a transaction that is rolled back.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import insert, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from app.modules.sandbox import service
from tests.integration.conftest import OpenBrowser

pytestmark = pytest.mark.integration

NEWEST_PUBLISHED = text(
    "SELECT id FROM handbook_versions WHERE published_at IS NOT NULL"
    " ORDER BY published_at DESC, created_at DESC, id DESC LIMIT 1"
)
INSERT_VERSION = text(
    "INSERT INTO handbook_versions (id, label, content_hash, embedding_model, embedding_dimensions,"
    " updated_on, published_at) VALUES (:id, :label, :label, 'voyage-4', 1024, current_date,"
    " :published_at)"
)
SET_TENANT = text("SELECT set_config('app.tenant_id', :tenant_id, true)")
INSERT_TENANT = text(
    "INSERT INTO tenants (id, expires_at, anchor_date, handbook_version_id)"
    " VALUES (:id, now() + interval '24 hours', current_date, :version_id)"
)
READ_PIN = text("SELECT handbook_version_id FROM tenants WHERE id = :id")
COUNT_TENANT = text("SELECT count(*) FROM tenants WHERE id = :id")


@asynccontextmanager
async def rolled_back(engine: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    """A connection in a transaction that is never committed."""
    async with engine.connect() as connection:
        transaction = await connection.begin()
        try:
            yield connection
        finally:
            await transaction.rollback()


async def newest_published(connection: AsyncConnection) -> UUID:
    version_id = await connection.scalar(NEWEST_PUBLISHED)
    assert isinstance(version_id, UUID)
    return version_id


async def add_version(connection: AsyncConnection, published_at: datetime | None) -> UUID:
    version_id = uuid4()
    await connection.execute(
        INSERT_VERSION, {"id": version_id, "label": str(version_id), "published_at": published_at}
    )
    return version_id


async def insert_tenant(connection: AsyncConnection, version_id: UUID | None = None) -> UUID:
    """Insert a tenant as whoever the connection is, naming `version_id` as its version."""
    tenant_id = uuid4()
    await connection.execute(SET_TENANT, {"tenant_id": str(tenant_id)})
    await connection.execute(INSERT_TENANT, {"id": tenant_id, "version_id": version_id})
    return tenant_id


async def pin_of(connection: AsyncConnection, tenant_id: UUID) -> UUID | None:
    return (await connection.execute(READ_PIN, {"id": tenant_id})).scalar_one()


async def test_a_sandbox_created_through_the_api_is_pinned_to_the_newest_published_version(
    open_browser: OpenBrowser, owner_engine: AsyncEngine
) -> None:
    sandbox = open_browser().start_sandbox()

    async with rolled_back(owner_engine) as connection:
        tenant_id = UUID(sandbox["tenant"]["id"])
        assert await pin_of(connection, tenant_id) == await newest_published(connection)


async def test_a_newly_published_version_is_pinned_and_a_newer_draft_is_ignored(
    owner_engine: AsyncEngine,
) -> None:
    now = datetime.now(UTC)
    async with rolled_back(owner_engine) as connection:
        published = await add_version(connection, published_at=now + timedelta(days=1))
        await add_version(connection, published_at=None)  # a draft, loaded but not published

        assert await pin_of(connection, await insert_tenant(connection)) == published


async def test_the_database_overrides_a_version_the_caller_names(
    owner_engine: AsyncEngine,
) -> None:
    # Acting as the API's role, which is how a bug in the service would reach the database.
    async with rolled_back(owner_engine) as connection:
        newest = await add_version(connection, published_at=datetime.now(UTC) + timedelta(days=2))
        older = await add_version(connection, published_at=datetime.now(UTC) + timedelta(days=1))
        draft = await add_version(connection, published_at=None)
        await connection.execute(text("SET LOCAL ROLE od_app"))

        for named in (older, draft, None):
            assert await pin_of(connection, await insert_tenant(connection, named)) == newest


async def test_with_no_published_version_the_insert_fails_with_od001(
    owner_engine: AsyncEngine,
) -> None:
    async with rolled_back(owner_engine) as connection:
        await connection.execute(text("UPDATE handbook_versions SET published_at = NULL"))

        with pytest.raises(DBAPIError, match="No published handbook version") as raised:
            await insert_tenant(connection)

    assert getattr(raised.value.orig, "sqlstate", None) == service.NO_PUBLISHED_HANDBOOK


class RecordingInsert:
    """Wraps `insert(Tenant)` to record the tenant's ID. The real insert still runs."""

    written: list[UUID] = []  # noqa: RUF012

    def __init__(self, table: Any) -> None:
        self._statement = insert(table)

    def values(self, **values: Any) -> Any:
        self.written.append(values["id"])
        return self._statement.values(**values)


async def fail_like_the_trigger(db: AsyncSession, _company: Any, _keys: Any) -> None:
    """Stands in for `insert_company`, which runs after the tenant insert in the same transaction.
    It raises the trigger's exact error (SQLSTATE OD001) from a real statement."""
    await db.execute(
        text(
            "DO $$ BEGIN RAISE EXCEPTION 'No published handbook version' USING ERRCODE = 'OD001';"
            " END $$"
        )
    )


async def test_the_service_answers_503_and_leaves_no_tenant_when_no_version_is_published(
    open_browser: OpenBrowser,
    owner_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # The service opens its own connections, and unpublishing for real would mean committing a
    # change to the shared handbook. So the real tenant insert runs and succeeds as its own
    # statement, and a later statement in the same transaction raises the trigger's exact error.
    # The tenant row can then only be gone if the service rolled its transaction back. Everything
    # else is the real code: the driver's error, the mapping, and the problem response.
    RecordingInsert.written = []
    monkeypatch.setattr(service, "insert", RecordingInsert)
    monkeypatch.setattr(service, "insert_company", fail_like_the_trigger)

    with caplog.at_level(logging.WARNING, logger=service.logger.name):
        response = open_browser().create_sandbox()

    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["detail"] == "The handbook isn't loaded yet."
    assert any("No published handbook version" in record.getMessage() for record in caplog.records)
    assert "set-cookie" not in response.headers
    (tenant_id,) = RecordingInsert.written
    async with rolled_back(owner_engine) as connection:
        assert await connection.scalar(COUNT_TENANT, {"id": tenant_id}) == 0
