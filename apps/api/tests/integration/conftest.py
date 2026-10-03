"""Database fixtures for the integration tests.

One engine per database login. A test that needs a URL that isn't set fails loudly instead of
skipping:

- `app_engine` connects as DATABASE_URL, the API's own login (a member of od_app).
- `owner_engine` connects as MIGRATION_DATABASE_URL, the database owner.
- `cleanup_engine` connects as CLEANUP_DATABASE_URL, the cleanup login (a member of od_cleanup).

`make_tenant` creates a small sandbox company as the API's login, with a row in every table, and
returns a `SampleTenant`. Every tenant it creates is deleted when the test session ends.
"""

import asyncio
import hashlib
import secrets
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Protocol
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from pydantic import PostgresDsn
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from app.db.engine import create_engine
from app.db.models import (
    AuditEvent,
    Department,
    Holiday,
    Location,
    Person,
    PersonPrivate,
    Tenant,
    UserSession,
)
from app.db.tenancy import TenantContext, tenant_session


@pytest.fixture(scope="session")
def database_settings() -> Settings:
    # Reads the environment (CI) or apps/api/.env (local development).
    return Settings()


def required_url(url: PostgresDsn | None, variable: str) -> str:
    if url is None:
        pytest.fail(f"{variable} is not set, so this test can't run. See apps/api/.env.example.")
    return str(url)


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def sweep_leftover_test_roles(database_settings: Settings) -> None:
    """Drop roles that an earlier, interrupted run left behind.

    Roles belong to the whole Postgres server, so a test that was killed before its cleanup leaves
    its throwaway roles in the database for good, some of them with powers such as SUPERUSER. The
    tests give every such role a name that starts with `od_test_`, which nothing else uses.
    """
    url = required_url(database_settings.migration_database_url, "MIGRATION_DATABASE_URL")
    engine = create_engine(url)
    try:
        async with engine.begin() as connection:
            leftovers = await connection.scalars(
                text("SELECT rolname FROM pg_roles WHERE starts_with(rolname, 'od_test_')")
            )
            for name in leftovers.all():
                statement = await connection.scalar(
                    text("SELECT format('DROP ROLE IF EXISTS %I', CAST(:name AS text))"),
                    {"name": name},
                )
                await connection.exec_driver_sql(str(statement))
    finally:
        await engine.dispose()


@pytest.fixture
async def app_engine(database_settings: Settings) -> AsyncIterator[AsyncEngine]:
    """The API's own login: a member of od_app, so row-level security applies to it."""
    engine = create_engine(str(database_settings.database_url))
    yield engine
    await engine.dispose()


@pytest.fixture
async def owner_engine(database_settings: Settings) -> AsyncIterator[AsyncEngine]:
    """The database owner, which runs the migrations."""
    url = required_url(database_settings.migration_database_url, "MIGRATION_DATABASE_URL")
    engine = create_engine(url)
    yield engine
    await engine.dispose()


@pytest.fixture
async def cleanup_engine(database_settings: Settings) -> AsyncIterator[AsyncEngine]:
    """The cleanup login: a member of od_cleanup, which may delete only expired tenants."""
    url = required_url(database_settings.cleanup_database_url, "CLEANUP_DATABASE_URL")
    engine = create_engine(url)
    yield engine
    await engine.dispose()


@dataclass(frozen=True)
class SampleTenant:
    """A tenant with a row in every table: three people, their private details, and the rest."""

    id: UUID
    # An ordinary employee, with a session. They are the actor on the tenant's audit event.
    employee_id: UUID
    # Another employee in the same tenant.
    colleague_id: UUID
    # The HR partner (is_hr_admin), and the other two people's manager.
    hr_id: UUID


class MakeTenant(Protocol):
    async def __call__(self, *, expired: bool = False) -> SampleTenant: ...


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def owner_is_superuser(database_settings: Settings) -> None:
    """Fail at the start of the session if the owner login is not a superuser.

    The tests delete the tenants they create through the owner, and that only works because a
    superuser bypasses row-level security. Any other login sees no tenant rows, so its DELETE
    would remove nothing without an error and leave the tenants in the database.
    """
    url = required_url(database_settings.migration_database_url, "MIGRATION_DATABASE_URL")
    engine = create_engine(url)
    try:
        async with engine.connect() as connection:
            is_superuser = await connection.scalar(
                text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
            )
    finally:
        await engine.dispose()
    if is_superuser is not True:
        pytest.fail(
            "MIGRATION_DATABASE_URL must name a superuser (the Compose database owner). The tests"
            " delete their tenants through it, and any other login can't see them under row-level"
            " security, so they would be left behind in the database."
        )


@pytest.fixture(scope="session")
def created_tenant_ids(
    database_settings: Settings, owner_is_superuser: None
) -> Iterator[list[UUID]]:
    """Every tenant the tests create, deleted through the owner when the test session ends.

    The owner is the Compose superuser in development and CI, and a superuser bypasses row-level
    security, so it can delete any tenant. Each tenant's rows go with it (ON DELETE CASCADE).
    """
    tenant_ids: list[UUID] = []
    yield tenant_ids
    if tenant_ids:
        url = required_url(database_settings.migration_database_url, "MIGRATION_DATABASE_URL")
        asyncio.run(delete_tenants(url, tenant_ids))


async def delete_tenants(url: str, tenant_ids: list[UUID]) -> None:
    engine = create_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.execute(delete(Tenant).where(Tenant.id.in_(tenant_ids)))
    finally:
        await engine.dispose()


def sha256_of_random_token() -> bytes:
    return hashlib.sha256(secrets.token_bytes(32)).digest()


@pytest.fixture
def make_tenant(app_engine: AsyncEngine, created_tenant_ids: list[UUID]) -> MakeTenant:
    """Create a `SampleTenant` as the API's login. Pass `expired=True` for one past its expiry."""

    async def make(*, expired: bool = False) -> SampleTenant:
        tenant_id = uuid4()
        created_tenant_ids.append(tenant_id)
        now = datetime.now(UTC)
        expires_at = now - timedelta(hours=1) if expired else now + timedelta(hours=24)
        location = Location(
            id=uuid4(),
            tenant_id=tenant_id,
            code="DEN",
            name="Denver HQ",
            city="Denver",
            state="CO",
            timezone="America/Denver",
        )
        department = Department(id=uuid4(), tenant_id=tenant_id, name="People")

        def person(given: str, family: str, manager_id: UUID | None, **extra: object) -> Person:
            return Person(
                id=uuid4(),
                tenant_id=tenant_id,
                given_name=given,
                family_name=family,
                title="Associate",
                department_id=department.id,
                location_id=location.id,
                manager_id=manager_id,
                work_email=f"{given.lower()}@opendoor.example",
                employment_type="salaried",
                hire_date=date(2024, 3, 4),
                **extra,
            )

        hr = person("Dana", "Whitfield", None, is_hr_admin=True, persona_key="dana")
        employee = person("Priya", "Shah", hr.id, persona_key="priya")
        colleague = person("Leo", "Marsh", hr.id)
        private_rows = [
            PersonPrivate(
                person_id=someone.id,
                tenant_id=tenant_id,
                personal_email=f"{someone.given_name.lower()}@example.com",
                phone="555-0100",
                home_address="1 Example Street, Denver, CO",
                date_of_birth=date(1990, 1, 1),
            )
            for someone in (hr, employee, colleague)
        ]

        # WITH CHECK accepts only rows of the tenant the transaction is scoped to, so the context
        # names the new tenant before its first row is written.
        async with tenant_session(app_engine, TenantContext(tenant_id, None)) as session:
            # Each flush writes the rows that the next ones refer to.
            session.add(Tenant(id=tenant_id, expires_at=expires_at, anchor_date=now.date()))
            await session.flush()
            session.add_all([location, department])
            await session.flush()
            session.add(hr)
            await session.flush()
            session.add_all([employee, colleague])
            await session.flush()
            session.add_all(private_rows)
            session.add(
                Holiday(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    location_id=location.id,
                    holiday_date=date(now.year, 1, 1),
                    name="New Year's Day",
                )
            )
            session.add(
                UserSession(
                    token_hash=sha256_of_random_token(),
                    csrf_hash=sha256_of_random_token(),
                    tenant_id=tenant_id,
                    person_id=employee.id,
                    expires_at=expires_at,
                )
            )
            session.add(
                AuditEvent(
                    tenant_id=tenant_id,
                    actor_person_id=employee.id,
                    via="system",
                    action="sandbox.created",
                    target_type="tenant",
                    target_id=tenant_id,
                )
            )
        return SampleTenant(tenant_id, employee.id, colleague.id, hr.id)

    return make
