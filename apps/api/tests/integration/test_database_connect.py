"""The database admits only Open Door's own logins (migration 0020).

On a server shared with another app, `CONNECT` on PUBLIC would let that app's logins open Open
Door's database. The migration moves it to the two roles the logins inherit.
"""

import secrets

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from app.db.engine import create_engine

pytestmark = pytest.mark.integration

STRANGER = "od_test_stranger"
STRANGER_PASSWORD = secrets.token_urlsafe(12)


async def test_public_cannot_connect(owner_engine: AsyncEngine) -> None:
    async with owner_engine.connect() as connection:
        granted_to_public = await connection.scalar(
            text(
                "SELECT EXISTS (SELECT FROM pg_database d,"
                " LATERAL aclexplode(COALESCE(d.datacl, acldefault('d', d.datdba))) AS a"
                " WHERE d.datname = current_database() AND a.grantee = 0"
                " AND a.privilege_type = 'CONNECT')"
            )
        )

    assert granted_to_public is False


@pytest.mark.parametrize("role", ["od_app", "od_cleanup"])
async def test_open_doors_roles_can_connect(owner_engine: AsyncEngine, role: str) -> None:
    async with owner_engine.connect() as connection:
        allowed = await connection.scalar(
            text("SELECT has_database_privilege(:role, current_database(), 'CONNECT')"),
            {"role": role},
        )

    assert allowed is True


async def test_a_login_without_open_doors_roles_cannot_connect(
    database_settings: Settings, owner_engine: AsyncEngine
) -> None:
    async with owner_engine.begin() as connection:
        await connection.exec_driver_sql(
            f"CREATE ROLE {STRANGER} LOGIN PASSWORD '{STRANGER_PASSWORD}'"
        )
    url = (
        make_url(str(database_settings.database_url))
        .set(username=STRANGER, password=STRANGER_PASSWORD)
        .render_as_string(hide_password=False)
    )
    engine = create_engine(url)
    try:
        with pytest.raises(DBAPIError, match="permission denied for database"):
            async with engine.connect():
                pass
    finally:
        await engine.dispose()
        async with owner_engine.begin() as connection:
            await connection.exec_driver_sql(f"DROP ROLE IF EXISTS {STRANGER}")
