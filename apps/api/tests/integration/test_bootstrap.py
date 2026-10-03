"""The bootstrap script creates a login user from a URL, quotes it safely, and can run again.

It also refuses to reuse a role that already exists with extra powers, and it never lets a
plaintext password reach its output or the server's log.
"""

import asyncio
import os
import secrets
import sys
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from app.db.engine import create_engine

pytestmark = pytest.mark.integration

API_DIR = Path(__file__).resolve().parents[2]

# Quotes, a semicolon, a comment, a backslash, and placeholder lookalikes. Pasted into SQL by hand,
# any of them would break the statement or change which user and password it sets. The password is
# a test value, not a secret.
ODD_USER = 'od_test_o\'brien "x"; --'
ODD_PASSWORD = 'it\'s "quoted"; -- \\ :name %(x)s %s $1 ?'  # noqa: S105

# Throwaway roles for the refusal and leak tests. The sweep in conftest.py drops leftovers whose
# names start with od_test_, and each test drops what it creates.
#
# The refusal tests create their roles NOLOGIN with no password, because the script decides from a
# role's name, attributes, and memberships alone. They still need some password in the URL they hand
# to the script, which a test can assert never appears in its output. These passwords are made up
# for each run, so no password for a database role is committed.
URL_PASSWORD = secrets.token_urlsafe(12)
LEAKY_USER = "od_test_leaky"
LEAKY_PASSWORD = "od-test-must-not-leak-4f9a"  # noqa: S105
WEAK_MIGRATOR = "od_test_migrator"
WEAK_MIGRATOR_PASSWORD = secrets.token_urlsafe(12)
GROUP_ROLE = "od_test_group"

CreateRole = Callable[[str, str], Awaitable[None]]


@dataclass(frozen=True)
class Run:
    returncode: int | None
    stdout: str
    stderr: str


async def run_bootstrap_script(database_url: str, migration_database_url: str | None = None) -> Run:
    environment = {**os.environ, "DATABASE_URL": database_url}
    if migration_database_url is not None:
        environment["MIGRATION_DATABASE_URL"] = migration_database_url
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "scripts/bootstrap_db_users.py",
        cwd=API_DIR,
        env=environment,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    return Run(process.returncode, stdout.decode(), stderr.decode())


async def run_bootstrap(database_url: str) -> str:
    run = await run_bootstrap_script(database_url)
    assert run.returncode == 0, run.stdout + run.stderr
    return run.stdout


async def drop_role(owner_engine: AsyncEngine, name: str) -> None:
    async with owner_engine.begin() as connection:
        statement: str = (
            await connection.execute(
                text("SELECT format('DROP ROLE IF EXISTS %I', CAST(:name AS text))"),
                {"name": name},
            )
        ).scalar_one()
        await connection.exec_driver_sql(statement)


@pytest.fixture
async def create_role(owner_engine: AsyncEngine) -> AsyncIterator[CreateRole]:
    """Create a throwaway role as the owner, and drop every role it made when the test ends."""
    created: list[str] = []

    async def create(name: str, options: str) -> None:
        async with owner_engine.begin() as connection:
            await connection.exec_driver_sql(f'CREATE ROLE "{name}" {options}')
        created.append(name)

    yield create
    for name in reversed(created):
        await drop_role(owner_engine, name)


def url_for(database_settings: Settings, user: str, password: str) -> str:
    url = make_url(str(database_settings.database_url)).set(username=user, password=password)
    return url.render_as_string(hide_password=False)


async def is_member(owner_engine: AsyncEngine, user: str, role: str) -> bool:
    """Whether `role` was granted to `user`. (pg_has_role would say yes for any superuser.)"""
    async with owner_engine.connect() as connection:
        granted = await connection.scalar(
            text(
                "SELECT EXISTS (SELECT FROM pg_auth_members m"
                " JOIN pg_roles g ON g.oid = m.roleid JOIN pg_roles u ON u.oid = m.member"
                " WHERE g.rolname = :role AND u.rolname = :user)"
            ),
            {"user": user, "role": role},
        )
    return bool(granted)


async def test_odd_names_and_passwords_are_quoted_and_a_second_run_only_updates(
    database_settings: Settings, owner_engine: AsyncEngine
) -> None:
    odd_url = url_for(database_settings, ODD_USER, ODD_PASSWORD)
    try:
        first = await run_bootstrap(odd_url)
        second = await run_bootstrap(odd_url)

        engine = create_engine(odd_url)
        try:
            async with engine.connect() as connection:
                who = await connection.execute(
                    text("SELECT current_user, pg_has_role(current_user, 'od_app', 'USAGE')")
                )
                row = tuple(who.one())
        finally:
            await engine.dispose()
    finally:
        await drop_role(owner_engine, ODD_USER)

    assert f"{ODD_USER}: created, with od_app" in first
    assert f"{ODD_USER}: password reset, with od_app" in second
    assert row == (ODD_USER, True)


@pytest.mark.parametrize(
    "attribute", ["SUPERUSER", "BYPASSRLS", "CREATEROLE", "CREATEDB", "REPLICATION"]
)
async def test_an_existing_role_with_an_extra_power_is_refused_and_not_granted_od_app(
    attribute: str,
    database_settings: Settings,
    owner_engine: AsyncEngine,
    create_role: CreateRole,
) -> None:
    user = f"od_test_{attribute.lower()}"
    await create_role(user, f"NOLOGIN {attribute}")

    run = await run_bootstrap_script(url_for(database_settings, user, URL_PASSWORD))

    assert run.returncode not in (0, None), run.stdout + run.stderr
    assert user in run.stderr
    assert attribute in run.stderr
    assert URL_PASSWORD not in run.stdout + run.stderr
    assert not await is_member(owner_engine, user, "od_app")


async def test_an_existing_role_that_belongs_to_another_role_is_refused_and_not_granted_od_app(
    database_settings: Settings,
    owner_engine: AsyncEngine,
    create_role: CreateRole,
) -> None:
    user = "od_test_member"
    await create_role(GROUP_ROLE, "NOLOGIN")
    await create_role(user, f"NOLOGIN IN ROLE {GROUP_ROLE}")

    run = await run_bootstrap_script(url_for(database_settings, user, URL_PASSWORD))

    assert run.returncode not in (0, None), run.stdout + run.stderr
    assert user in run.stderr
    assert GROUP_ROLE in run.stderr
    assert URL_PASSWORD not in run.stdout + run.stderr
    assert not await is_member(owner_engine, user, "od_app")


async def test_an_existing_login_that_could_pass_on_od_app_is_refused(
    database_settings: Settings,
    owner_engine: AsyncEngine,
    create_role: CreateRole,
) -> None:
    # WITH ADMIN OPTION lets the holder grant od_app to any other role, which would then inherit
    # everything the API can do.
    user = "od_test_admin"
    await create_role(user, "NOLOGIN")
    async with owner_engine.begin() as connection:
        await connection.exec_driver_sql(f'GRANT od_app TO "{user}" WITH ADMIN OPTION')

    run = await run_bootstrap_script(url_for(database_settings, user, URL_PASSWORD))

    assert run.returncode not in (0, None), run.stdout + run.stderr
    assert user in run.stderr
    assert "ADMIN OPTION" in run.stderr
    assert URL_PASSWORD not in run.stdout + run.stderr


async def test_an_existing_login_that_has_members_is_refused_and_not_granted_od_app(
    database_settings: Settings,
    owner_engine: AsyncEngine,
    create_role: CreateRole,
) -> None:
    # A role that is a member of the login inherits whatever the login is granted, so granting
    # od_app to the login would also give it to that role.
    user = "od_test_hub"
    inheritor = "od_test_inheritor"
    await create_role(user, "NOLOGIN")
    await create_role(inheritor, f"NOLOGIN IN ROLE {user}")

    run = await run_bootstrap_script(url_for(database_settings, user, URL_PASSWORD))

    assert run.returncode not in (0, None), run.stdout + run.stderr
    assert user in run.stderr
    assert inheritor in run.stderr
    assert URL_PASSWORD not in run.stdout + run.stderr
    assert not await is_member(owner_engine, user, "od_app")


@pytest.mark.parametrize("already_has_its_role", [False, True])
async def test_an_existing_plain_role_is_reused_and_gets_only_its_role(
    already_has_its_role: bool,
    database_settings: Settings,
    owner_engine: AsyncEngine,
    create_role: CreateRole,
) -> None:
    user = "od_test_plain"
    await create_role(user, "NOLOGIN IN ROLE od_app" if already_has_its_role else "NOLOGIN")

    run = await run_bootstrap_script(url_for(database_settings, user, URL_PASSWORD))

    assert run.returncode == 0, run.stdout + run.stderr
    assert f"{user}: password reset, with od_app" in run.stdout
    assert await is_member(owner_engine, user, "od_app")
    assert not await is_member(owner_engine, user, "od_cleanup")


async def test_a_failure_never_prints_the_password(
    database_settings: Settings,
    owner_engine: AsyncEngine,
    create_role: CreateRole,
) -> None:
    # A migrator without CREATEROLE makes the CREATE ROLE statement fail. Its error used to print
    # the statement, plaintext password included, to stderr (and, through the server's
    # log_min_error_statement, to the server's log).
    await create_role(WEAK_MIGRATOR, f"LOGIN NOCREATEROLE PASSWORD '{WEAK_MIGRATOR_PASSWORD}'")

    run = await run_bootstrap_script(
        url_for(database_settings, LEAKY_USER, LEAKY_PASSWORD),
        migration_database_url=url_for(database_settings, WEAK_MIGRATOR, WEAK_MIGRATOR_PASSWORD),
    )

    assert run.returncode not in (0, None)
    assert "InsufficientPrivilegeError" in run.stderr
    assert LEAKY_PASSWORD not in run.stdout
    assert LEAKY_PASSWORD not in run.stderr
    assert WEAK_MIGRATOR_PASSWORD not in run.stdout + run.stderr
    async with owner_engine.connect() as connection:
        created = await connection.scalar(
            text("SELECT EXISTS (SELECT FROM pg_roles WHERE rolname = :user)"),
            {"user": LEAKY_USER},
        )
    assert created is False
