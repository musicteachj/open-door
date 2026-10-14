"""The handbook tables are read-only to the API, and a version a tenant uses can't be deleted."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

pytestmark = pytest.mark.integration

HANDBOOK_TABLES = ["handbook_versions", "handbook_sections", "handbook_chunks"]

# One write per table. The privilege check runs before any column or constraint is looked at, so
# these statements need not be valid rows: the refusal is for the verb, not the values.
REFUSED_WRITES = [
    f"{verb} {table}"
    for table in HANDBOOK_TABLES
    for verb in ("INSERT INTO", "UPDATE", "DELETE FROM")
]


def refused_statement(statement: str) -> str:
    if statement.startswith("INSERT INTO"):
        return f"{statement} DEFAULT VALUES"
    if statement.startswith("UPDATE"):
        return f"{statement} SET id = id"
    return statement


@pytest.mark.parametrize("statement", REFUSED_WRITES)
async def test_the_api_login_cannot_write_the_handbook(
    app_engine: AsyncEngine, statement: str
) -> None:
    async with app_engine.connect() as connection:
        with pytest.raises(DBAPIError, match="permission denied"):
            await connection.execute(text(refused_statement(statement)))


@pytest.mark.parametrize("table", HANDBOOK_TABLES)
async def test_the_api_login_can_read_the_handbook(app_engine: AsyncEngine, table: str) -> None:
    async with app_engine.connect() as connection:
        await connection.execute(text(f"SELECT count(*) FROM {table}"))  # noqa: S608


@pytest.mark.parametrize("table", HANDBOOK_TABLES)
async def test_the_cleanup_login_cannot_touch_the_handbook(
    cleanup_engine: AsyncEngine, table: str
) -> None:
    async with cleanup_engine.connect() as connection:
        with pytest.raises(DBAPIError, match="permission denied"):
            await connection.execute(text(f"SELECT count(*) FROM {table}"))  # noqa: S608


async def test_the_handbook_version_column_is_a_nullable_uuid(app_engine: AsyncEngine) -> None:
    # Nullable for sandboxes created before the handbook existed; the trigger always pins new ones.
    async with app_engine.connect() as connection:
        row = (
            await connection.execute(
                text(
                    "SELECT data_type, is_nullable FROM information_schema.columns"
                    " WHERE table_schema = 'public' AND table_name = 'tenants'"
                    " AND column_name = 'handbook_version_id'"
                )
            )
        ).one()
    assert tuple(row) == ("uuid", "YES")


@asynccontextmanager
async def rolled_back(engine: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    """A transaction on the owner's connection that never commits, so nothing is left behind."""
    async with engine.connect() as connection:
        transaction = await connection.begin()
        try:
            yield connection
        finally:
            await transaction.rollback()


async def insert_version(connection: AsyncConnection, label: str) -> str:
    version_id = str(uuid4())
    await connection.execute(
        text(
            "INSERT INTO handbook_versions (id, label, content_hash, embedding_model,"
            " embedding_dimensions, updated_on) VALUES (:id, :label, :hash, 'voyage-4', 1024,"
            " '2026-10-01')"
        ),
        {"id": version_id, "label": label, "hash": f"hash-{version_id}"},
    )
    return version_id


async def test_a_version_a_tenant_uses_cannot_be_deleted(owner_engine: AsyncEngine) -> None:
    async with owner_engine.connect() as connection:
        delete_action = await connection.scalar(
            text(
                "SELECT c.confdeltype::text FROM pg_constraint c"
                " JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)"
                " WHERE c.contype = 'f' AND c.conrelid = 'public.tenants'::regclass"
                " AND c.confrelid = 'public.handbook_versions'::regclass"
                " AND a.attname = 'handbook_version_id'"
            )
        )
    # 'r' is RESTRICT. NO ACTION ('a') would also refuse, but it can be deferred to commit.
    assert delete_action == "r"
    now = datetime.now(UTC)
    async with rolled_back(owner_engine) as connection:
        version_id = await insert_version(connection, "test-in-use")
        # A trigger pins a new tenant to the newest published version, so publish this one first.
        await connection.execute(
            text(
                "UPDATE handbook_versions SET published_at = now() + interval '1 day'"
                " WHERE id = :id"
            ),
            {"id": version_id},
        )
        await connection.execute(
            text(
                "INSERT INTO tenants (id, expires_at, anchor_date) VALUES (:id, :expires, :anchor)"
            ),
            {"id": uuid4(), "expires": now + timedelta(hours=24), "anchor": now.date()},
        )
        with pytest.raises(IntegrityError, match="handbook_version_id"):
            await connection.execute(
                text("DELETE FROM handbook_versions WHERE id = :id"), {"id": version_id}
            )


async def test_deleting_an_unused_version_removes_its_sections_and_chunks(
    owner_engine: AsyncEngine,
) -> None:
    async with rolled_back(owner_engine) as connection:
        version_id = await insert_version(connection, "test-cascade")
        section_id = uuid4()
        await connection.execute(
            text(
                "INSERT INTO handbook_sections (id, version_id, section_key, position, kind,"
                " chapter, title, audience, updated_on, sources, blocks) VALUES (:id, :version,"
                " '4.3', 1, 'company', 4, 'Paid time off', '{}'::jsonb, '2026-10-01',"
                " '[]'::jsonb, '[]'::jsonb)"
            ),
            {"id": section_id, "version": version_id},
        )
        await connection.execute(
            text(
                "INSERT INTO handbook_chunks (id, version_id, section_id, section_key,"
                " section_title, position, heading, passage_ids, text, embedding)"
                " VALUES (:id, :version, :section, '4.3', 'Paid time off', 1, 'Accrual',"
                " ARRAY['4.3-1'], 'Employees accrue vacation hours.',"
                " array_fill(0.1::real, ARRAY[1024])::vector)"
            ),
            {"id": uuid4(), "version": version_id, "section": section_id},
        )
        await connection.execute(
            text("DELETE FROM handbook_versions WHERE id = :id"), {"id": version_id}
        )
        remaining = await connection.scalar(
            text(
                "SELECT (SELECT count(*) FROM handbook_sections WHERE section_key = '4.3'"
                " AND title = 'Paid time off' AND version_id = :version)"
                " + (SELECT count(*) FROM handbook_chunks WHERE version_id = :version)"
            ),
            {"version": version_id},
        )
    assert remaining == 0


async def test_the_search_column_weights_the_section_key_and_title_above_the_text(
    owner_engine: AsyncEngine,
) -> None:
    async with rolled_back(owner_engine) as connection:
        version_id = await insert_version(connection, "test-search")
        section_id = uuid4()
        await connection.execute(
            text(
                "INSERT INTO handbook_sections (id, version_id, section_key, position, kind,"
                " chapter, title, audience, updated_on, sources, blocks) VALUES (:id, :version,"
                " '4.3', 1, 'company', 4, 'Bereavement leave', '{}'::jsonb, '2026-10-01',"
                " '[]'::jsonb, '[]'::jsonb)"
            ),
            {"id": section_id, "version": version_id},
        )
        await connection.execute(
            text(
                "INSERT INTO handbook_chunks (id, version_id, section_id, section_key,"
                " section_title, position, heading, passage_ids, text, embedding)"
                " VALUES (:id, :version, :section, '4.3', 'Bereavement leave', 1, 'Eligibility',"
                " ARRAY['4.3-1'], 'Employees may take three days.',"
                " array_fill(0.1::real, ARRAY[1024])::vector)"
            ),
            {"id": uuid4(), "version": version_id, "section": section_id},
        )
        rows = (
            await connection.execute(
                text(
                    "SELECT search @@ to_tsquery('english', 'bereavement') AS in_title,"
                    " search @@ to_tsquery('english', 'days') AS in_text,"
                    " search::text LIKE '%''bereav'':%A%' AS title_is_a,"
                    " search::text LIKE '%''day'':%B%' AS text_is_b FROM handbook_chunks"
                    " WHERE version_id = :version"
                ),
                {"version": version_id},
            )
        ).one()
    assert tuple(rows) == (True, True, True, True)
