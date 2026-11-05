"""Database fixtures for the integration tests.

One engine per database login. A test that needs a URL that isn't set fails loudly instead of
skipping:

- `app_engine` connects as DATABASE_URL, the API's own login (a member of od_app).
- `owner_engine` connects as MIGRATION_DATABASE_URL, the database owner.
- `cleanup_engine` connects as CLEANUP_DATABASE_URL, the cleanup login (a member of od_cleanup).

`make_tenant` creates a small sandbox company as the API's login, with a row in every table, and
returns a `SampleTenant`. `seeded_sandbox` creates the full 145-person seed company the same way.
`browser` and `open_browser` give the HTTP tests a client that behaves
like the web app in a browser. Every tenant these create is deleted when the test session ends.
"""

import asyncio
import hashlib
import json
import secrets
from collections.abc import AsyncIterator, Iterator
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID, uuid4

import httpx2 as httpx
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from pydantic import PostgresDsn
from sqlalchemy import delete, insert, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.ai.conversations import (
    TurnOutcome,
    TurnText,
    conversation_cipher,
    finish_turn,
    open_reason,
    open_turn,
    start_turn,
)
from app.ai.proposal_cards import RequestCard
from app.core.config import Settings
from app.core.encryption import (
    TEST_KEY,
    TEST_KEY_ID,
    LocalKeyProvider,
    Place,
    new_data_key,
    seal,
    wrap_aad,
)
from app.db.engine import create_engine
from app.db.models import (
    AiConsoleTurn,
    AiConversation,
    AiFeedback,
    AiMessage,
    AiSpend,
    AiTurn,
    AuditEvent,
    Case,
    CaseEvent,
    CaseSummary,
    Department,
    Holiday,
    Location,
    Person,
    PersonPrivate,
    Tenant,
    UserSession,
)
from app.db.tenancy import TenantContext, set_is_hr, tenant_session
from app.main import create_app
from app.modules.identity.cookies import CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE
from app.modules.sandbox.seed import SeedCompany, build_company, insert_company
from tests.conftest import TEST_KEYRING


@pytest.fixture(scope="session")
def database_settings() -> Settings:
    # Reads the environment (CI) or apps/api/.env (local development). The keyring is always the
    # fixed test one, so that rows the tests seal by hand (`TEST_KEYS`) open in the app, and the
    # app accepts the fake key (APP_ENV=test).
    return Settings().model_copy(
        update={
            "app_env": "test",
            "encryption_keyring": TEST_KEYRING,
            "encryption_keyring_file": None,
        }
    )


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


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def handbook_is_published(database_settings: Settings) -> None:
    """Fail at the start of the session if no handbook version is published.

    A trigger pins every new sandbox to the newest published version and refuses to create one
    without it, so a forgotten ingest would otherwise show up as dozens of baffling failures.
    """
    url = required_url(database_settings.migration_database_url, "MIGRATION_DATABASE_URL")
    engine = create_engine(url)
    try:
        async with engine.connect() as connection:
            published = await connection.scalar(
                text("SELECT count(*) FROM handbook_versions WHERE published_at IS NOT NULL")
            )
    finally:
        await engine.dispose()
    if not published:
        pytest.fail("No published handbook version: run `make ingest`.")


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
    """A tenant with a row in every table: three people, their private details, and the rest.

    The employee has the assistant's rows and the time-off rows: an opening balance, a pending
    proposal, and the pending request that proposal made.
    """

    id: UUID
    # An ordinary employee, with a session. They are the actor on the tenant's audit event.
    employee_id: UUID
    # Another employee in the same tenant.
    colleague_id: UUID
    # The HR partner (is_hr_admin), and the other two people's manager.
    hr_id: UUID
    # The case the employee opened, from the turn in their conversation.
    case_id: UUID


@dataclass(frozen=True)
class AssistantRows:
    """The IDs of the assistant rows `add_assistant_rows` wrote for one person."""

    conversation_id: UUID
    turn_id: UUID


# Stands in for the key provider in rows the tests write by hand. The real store gets its provider
# from the app.
TEST_KEYS = LocalKeyProvider([(TEST_KEY_ID, TEST_KEY)])
# A value the tests store when they only need some bytes in a ciphertext column.
OPAQUE = b"opaque ciphertext"


def conversation_key(tenant_id: UUID, conversation_id: UUID) -> tuple[str, bytes, bytes]:
    """A new data key for a conversation: its key ID, its wrapped form, and the key itself."""
    data_key = new_data_key()
    key_id, wrapped = TEST_KEYS.wrap(
        data_key, aad=wrap_aad(tenant_id, "ai_conversations", conversation_id)
    )
    return key_id, wrapped, data_key


async def write_assistant_rows(
    session: AsyncSession, tenant_id: UUID, person_id: UUID
) -> AssistantRows:
    """Write a conversation, a completed turn with its two messages and a thumbs-up (with a reason),
    and a spend row, and flush them. The text is sealed with the conversation's own data key.

    The session must be scoped to `person_id`: Postgres shows a person's conversations only to
    that person, and refuses to write one for anyone else.
    """
    rows = AssistantRows(conversation_id=uuid4(), turn_id=uuid4())
    key_id, wrapped_key, data_key = conversation_key(tenant_id, rows.conversation_id)

    def sealed(text_: str, table: str, column: str, row_id: UUID) -> bytes:
        return seal(data_key, text_.encode(), place=Place(table, column, tenant_id, row_id))

    session.add(
        AiConversation(
            id=rows.conversation_id,
            tenant_id=tenant_id,
            person_id=person_id,
            model="claude-opus-5-5",
            guard_model="claude-haiku-5-5",
            effort="medium",
            prompt_version="test",
            toolset_version="test",
            key_id=key_id,
            wrapped_key=wrapped_key,
        )
    )
    await session.flush()
    session.add(
        AiTurn(
            id=rows.turn_id,
            tenant_id=tenant_id,
            person_id=person_id,
            conversation_id=rows.conversation_id,
            question_ciphertext=sealed(
                "How much sick leave do I get?", "ai_turns", "question_ciphertext", rows.turn_id
            ),
            status="completed",
            answer_ciphertext=sealed(
                "You get 40 hours.", "ai_turns", "answer_ciphertext", rows.turn_id
            ),
        )
    )
    await session.flush()
    messages = [
        (uuid4(), position, role, [{"type": "text", "text": text_}])
        for position, role, text_ in (
            (0, "user", "How much sick leave do I get?"),
            (1, "assistant", "You get 40 hours."),
        )
    ]
    session.add_all(
        [
            AiMessage(
                id=message_id,
                tenant_id=tenant_id,
                person_id=person_id,
                conversation_id=rows.conversation_id,
                turn_id=rows.turn_id,
                position=position,
                role=role,
                content_ciphertext=sealed(
                    json.dumps(content), "ai_messages", "content_ciphertext", message_id
                ),
            )
            for message_id, position, role, content in messages
        ]
    )
    feedback_id = uuid4()
    session.add(
        AiFeedback(
            id=feedback_id,
            tenant_id=tenant_id,
            person_id=person_id,
            turn_id=rows.turn_id,
            helpful=True,
            reason_ciphertext=sealed(
                "Clear answer.", "ai_feedback", "reason_ciphertext", feedback_id
            ),
        )
    )
    session.add(
        AiSpend(
            tenant_id=tenant_id, turn_id=rows.turn_id, kind="reserve", amount_usd=Decimal("0.05")
        )
    )
    await session.flush()
    return rows


async def write_case_rows(
    session: AsyncSession, tenant_id: UUID, person_id: UUID, assistant: AssistantRows
) -> UUID:
    """Write a case from the person's turn, its `opened` event, and a written summary, and return
    the case's ID. The ciphertext columns hold opaque bytes.

    The session must be scoped to `person_id`, as the API's own request is. The summary and the
    event are Core inserts with no RETURNING, as the service writes them: the person can't read
    them back, and Postgres checks RETURNING against the SELECT rule.
    """
    case_id = uuid4()
    session.add(
        Case(
            id=case_id,
            tenant_id=tenant_id,
            person_id=person_id,
            submission_id=uuid4(),
            category="pay",
            reply_by=datetime.now(UTC).date() + timedelta(days=2),
            screening="ordinary",
            conversation_id=assistant.conversation_id,
            turn_id=assistant.turn_id,
            key_id=TEST_KEY_ID,
            wrapped_key=OPAQUE,
            text_ciphertext=OPAQUE,
        )
    )
    await session.flush()
    await session.execute(
        insert(CaseEvent).values(
            id=uuid4(),
            tenant_id=tenant_id,
            case_id=case_id,
            actor_person_id=person_id,
            kind="opened",
        )
    )
    await session.execute(
        insert(CaseSummary).values(
            id=uuid4(),
            tenant_id=tenant_id,
            case_id=case_id,
            status="written",
            ciphertext=OPAQUE,
            model="claude-haiku-5-5",
            prompt_version="test",
        )
    )
    return case_id


async def write_console_row(
    session: AsyncSession, tenant_id: UUID, assistant: AssistantRows
) -> None:
    """Write the console row for the person's turn, as the turn's own finish does: a Core insert
    with no RETURNING, since only HR can read the row back."""
    await session.execute(
        insert(AiConsoleTurn).values(
            id=uuid4(),
            tenant_id=tenant_id,
            turn_id=assistant.turn_id,
            occurred_on=date(2026, 10, 30),
            occurred_at=datetime(2026, 10, 30, 17, 0, tzinfo=UTC),
            flagged=False,
            asker_role="employee",
            asker_location="Denver, CO",
            outcome="answered",
            injection_suspected=False,
            tools=[],
            sections_retrieved=[],
            sections_cited=[],
            fallback=False,
        )
    )


@dataclass(frozen=True)
class TimeOffRows:
    """The IDs of the time-off rows `write_time_off_rows` wrote for one person."""

    proposal_id: UUID
    request_id: UUID


async def write_time_off_rows(
    session: AsyncSession, tenant_id: UUID, person_id: UUID, assistant: AssistantRows
) -> TimeOffRows:
    """Write an opening balance, a pending proposal in the person's conversation, and a pending
    request that the proposal made, and flush them.

    A person who already has an opening (everyone in a seeded sandbox) keeps it, since a person
    has only one. The request is a single day, 30 days from the real today, so it overlaps none of
    the seed's, which are dated from a fixed anchor (and only Zara's pending one is ahead of it).

    The session must be scoped to `person_id`, like `write_assistant_rows`. The proposal belongs
    to the conversation and turn `assistant` names.
    """
    rows = TimeOffRows(proposal_id=uuid4(), request_id=uuid4())
    today = datetime.now(UTC).date()
    day = today + timedelta(days=30)
    # A real card, so reading the proposal back (the conversation read validates it) works.
    card = RequestCard.model_validate(
        {
            "kind": "request",
            "type": "pto",
            "startDate": day.isoformat(),
            "endDate": day.isoformat(),
            "partialMinutes": None,
            "countedDays": [day.isoformat()],
            "skippedDays": [],
            "amountMinutes": 480,
            "amountLabel": "8 hours (1 day)",
            "draws": [
                {
                    "year": None,
                    "amountMinutes": 480,
                    "amountLabel": "8 hours (1 day)",
                    "availableBeforeMinutes": 960,
                    "availableBeforeLabel": "16 hours (2 days)",
                    "availableAfterMinutes": 480,
                    "availableAfterLabel": "8 hours (1 day)",
                }
            ],
            "warnings": [],
            "approver": None,
            "rules": [],
        }
    )
    await session.execute(
        text(
            "INSERT INTO time_off_openings (tenant_id, person_id, as_of, amount_minutes)"
            " VALUES (:tenant_id, :person_id, :as_of, 4800)"
            # A person in a seeded sandbox already has the seed's opening: keep it.
            " ON CONFLICT (tenant_id, person_id) DO NOTHING"
        ),
        {"tenant_id": tenant_id, "person_id": person_id, "as_of": today},
    )
    await session.execute(
        text(
            "INSERT INTO ai_proposals (id, tenant_id, person_id, conversation_id, turn_id, action,"
            " payload, card, status, expires_at)"
            " VALUES (:id, :tenant_id, :person_id, :conversation_id, :turn_id, 'timeoff.request',"
            " CAST(:payload AS jsonb), CAST(:card AS jsonb), 'pending',"
            " now() + interval '15 minutes')"
        ),
        {
            "id": rows.proposal_id,
            "tenant_id": tenant_id,
            "person_id": person_id,
            "conversation_id": assistant.conversation_id,
            "turn_id": assistant.turn_id,
            "payload": json.dumps(
                {"type": "pto", "startDate": day.isoformat(), "endDate": day.isoformat()}
            ),
            "card": card.model_dump_json(by_alias=True),
        },
    )
    await session.execute(
        text(
            "INSERT INTO time_off_requests (id, tenant_id, person_id, type, start_date, end_date,"
            " amount_minutes, status, created_via, proposal_id)"
            " VALUES (:id, :tenant_id, :person_id, 'pto', :start_date, :end_date, 480, 'pending',"
            " 'assistant', :proposal_id)"
        ),
        {
            "id": rows.request_id,
            "tenant_id": tenant_id,
            "person_id": person_id,
            "start_date": today + timedelta(days=30),
            "end_date": today + timedelta(days=30),
            "proposal_id": rows.proposal_id,
        },
    )
    return rows


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
            code="den",
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
                work_email=f"{given.lower()}@juniperrow.example",
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
        # The assistant's rows are visible only to the person they belong to, so the employee
        # writes them in a transaction of their own.
        async with tenant_session(app_engine, TenantContext(tenant_id, employee.id)) as session:
            assistant = await write_assistant_rows(session, tenant_id, employee.id)
            await write_time_off_rows(session, tenant_id, employee.id, assistant)
            case_id = await write_case_rows(session, tenant_id, employee.id, assistant)
            await write_console_row(session, tenant_id, assistant)
        return SampleTenant(tenant_id, employee.id, colleague.id, hr.id, case_id)

    return make


@pytest.fixture
async def seeded_sandbox(app_engine: AsyncEngine, created_tenant_ids: list[UUID]) -> SeedCompany:
    """A new tenant with the full seed company (145 people), created as the API's login.

    Read it back with `tenant_session(app_engine, TenantContext(company.tenant_id, None))`. The
    tenant is deleted when the test session ends, like every tenant `make_tenant` creates.
    """
    tenant_id = uuid4()
    created_tenant_ids.append(tenant_id)
    anchor = date(2026, 10, 5)
    company = build_company(tenant_id, anchor)
    expires_at = datetime.now(UTC) + timedelta(hours=24)
    async with tenant_session(app_engine, TenantContext(tenant_id, None)) as session:
        session.add(Tenant(id=tenant_id, expires_at=expires_at, anchor_date=anchor))
        # The tenant row goes first: every seeded row refers to it.
        await session.flush()
        await insert_company(session, company, TEST_KEYS)
    return company


class Browser:
    """The web app in a browser, as the API sees it.

    It uses HTTPS, because a client never sends a Secure cookie over plain HTTP, and sends
    `Sec-Fetch-Site: same-origin`, as a browser does on the app's own requests. Each browser has its
    own app, database engine, and cookie jar.
    """

    def __init__(self, client: TestClient, created_tenant_ids: list[UUID]) -> None:
        self.client = client
        self._created_tenant_ids = created_tenant_ids

    def create_sandbox(self, body: object = None, **kwargs: Any) -> httpx.Response:
        """POST /sandboxes. A sandbox it creates is deleted when the test session ends."""
        response = self.client.post("/api/v1/sandboxes", json=body, **kwargs)
        if response.status_code == 201:
            self._created_tenant_ids.append(UUID(response.json()["tenant"]["id"]))
        return response

    def start_sandbox(self, persona: str | None = None) -> dict[str, Any]:
        """Create a sandbox as `persona`, or the default, and return the response body."""
        response = self.create_sandbox(None if persona is None else {"persona": persona})
        assert response.status_code == 201, response.text
        sandbox: dict[str, Any] = response.json()
        return sandbox

    @property
    def session_token(self) -> str:
        return self.client.cookies[SESSION_COOKIE]

    @property
    def csrf_token(self) -> str:
        return self.client.cookies[CSRF_COOKIE]

    @property
    def csrf(self) -> dict[str, str]:
        """The header the web app adds to every request that changes something."""
        return {CSRF_HEADER: self.csrf_token}


def session_cookie(token: str) -> dict[str, str]:
    """A Cookie header carrying `token`. It replaces the browser's own cookies for one request."""
    return {"Cookie": f"{SESSION_COOKIE}={token}"}


class OpenBrowser(Protocol):
    def __call__(
        self, *, same_origin_header: bool = True, raise_server_exceptions: bool = True
    ) -> Browser: ...


@pytest.fixture
def open_browser(
    database_settings: Settings, created_tenant_ids: list[UUID]
) -> Iterator[OpenBrowser]:
    """Open as many browsers as a test needs. Pass `same_origin_header=False` for one that sends
    no Sec-Fetch-Site, as an old browser or a script would. Pass `raise_server_exceptions=False`
    to see a crash as the 500 response a real client gets, instead of as a raised exception."""
    with ExitStack() as stack:

        def open_one(
            *, same_origin_header: bool = True, raise_server_exceptions: bool = True
        ) -> Browser:
            client = TestClient(
                create_app(database_settings),
                base_url="https://testserver",
                raise_server_exceptions=raise_server_exceptions,
                headers={"Sec-Fetch-Site": "same-origin"} if same_origin_header else None,
            )
            return Browser(stack.enter_context(client), created_tenant_ids)

        yield open_one


@pytest.fixture
def browser(open_browser: OpenBrowser) -> Browser:
    return open_browser()


@pytest.fixture
async def daily_ledger_untouched(owner_engine: AsyncEngine) -> AsyncIterator[None]:
    """Leave the demo-wide daily AI ledger as the test found it.

    The daily ledger has no tenant, so deleting a test's sandbox leaves its rows behind, and the
    stream tests reserve real amounts (a stopped call keeps its reservation) that would add up to
    the day's cap. Use it with `pytest.mark.usefixtures`. Like the budget tests, such a test must
    not run at the same time as another run.
    """
    async with owner_engine.connect() as connection:
        existing: list[UUID] = list(
            (await connection.execute(text("SELECT id FROM ai_spend_daily"))).scalars()
        )
    yield
    async with owner_engine.begin() as connection:
        await connection.execute(
            text("DELETE FROM ai_spend_daily WHERE NOT (id = ANY(CAST(:keep AS uuid[])))"),
            {"keep": existing},
        )


class OpenBrowserWith(Protocol):
    def __call__(self, **setting_changes: Any) -> Browser: ...


@pytest.fixture
def open_browser_with(
    database_settings: Settings, created_tenant_ids: list[UUID]
) -> Iterator[OpenBrowserWith]:
    """Open a browser on an app built with some settings changed, such as a smaller daily AI
    budget or a shorter heartbeat. The app's lifespan runs while the test does."""
    with ExitStack() as stack:

        def open_one(**setting_changes: Any) -> Browser:
            client = TestClient(
                create_app(database_settings.model_copy(update=setting_changes)),
                base_url="https://testserver",
                headers={"Sec-Fetch-Site": "same-origin"},
            )
            return Browser(stack.enter_context(client), created_tenant_ids)

        yield open_one


async def audit_events(engine: AsyncEngine, tenant_id: UUID) -> list[AuditEvent]:
    """Every audit event in the tenant, oldest first, read as the API's login. The read is flagged
    HR, since a case's rows and an `escalation.offered` row are visible to HR and to no one else."""
    async with tenant_session(engine, TenantContext(tenant_id, None)) as session:
        await set_is_hr(session, True)
        query = select(AuditEvent).order_by(AuditEvent.occurred_at)
        return list((await session.execute(query)).scalars())


# --- Reading the encrypted conversation text back ----------------------------------------------


class OpenTurn:
    """An `AiTurn` row with its encrypted text opened: `question`, `answer_text`, and `tool_calls`
    (input summaries in the clear). Every other attribute is the row's own."""

    def __init__(self, row: AiTurn, text_: TurnText) -> None:
        self._row = row
        self.question = text_.question
        self.answer_text = text_.answer
        self.tool_calls = text_.tool_calls

    def __getattr__(self, name: str) -> Any:
        return getattr(self._row, name)


class OpenMessage:
    """An `AiMessage` row with `content` opened. Every other attribute is the row's own."""

    def __init__(self, row: AiMessage, content: list[dict[str, Any]]) -> None:
        self._row = row
        self.content = content

    def __getattr__(self, name: str) -> Any:
        return getattr(self._row, name)


async def open_turns(db: AsyncSession, rows: list[AiTurn]) -> list[OpenTurn]:
    """Open turns as the test keyring would. Reads the conversation rows it needs."""
    ciphers = {}
    out = []
    for row in rows:
        if row.conversation_id not in ciphers:
            conversation = await db.get(AiConversation, row.conversation_id)
            assert conversation is not None
            ciphers[row.conversation_id] = conversation_cipher(TEST_KEYS, conversation)
        out.append(OpenTurn(row, open_turn(ciphers[row.conversation_id], row)))
    return out


async def open_messages(db: AsyncSession, rows: list[AiMessage]) -> list[OpenMessage]:
    ciphers = {}
    out = []
    for row in rows:
        if row.conversation_id not in ciphers:
            conversation = await db.get(AiConversation, row.conversation_id)
            assert conversation is not None
            ciphers[row.conversation_id] = conversation_cipher(TEST_KEYS, conversation)
        text_ = ciphers[row.conversation_id].open_text(
            row.content_ciphertext, "ai_messages", "content_ciphertext", row.id
        )
        out.append(OpenMessage(row, json.loads(text_)))
    return out


async def open_feedback_reason(db: AsyncSession, row: AiFeedback) -> str | None:
    turn = await db.get(AiTurn, row.turn_id)
    assert turn is not None
    conversation = await db.get(AiConversation, turn.conversation_id)
    assert conversation is not None
    return open_reason(conversation_cipher(TEST_KEYS, conversation), row)


# --- Writing encrypted conversation text by hand -----------------------------------------------


async def begin_turn(db: AsyncSession, conversation: AiConversation, question: str) -> AiTurn:
    """`start_turn` with the test keyring."""
    return await start_turn(
        db, conversation, question, conversation_cipher(TEST_KEYS, conversation)
    )


async def end_turn(
    db: AsyncSession, conversation: AiConversation, turn_id: UUID, outcome: TurnOutcome
) -> None:
    """`finish_turn` with the test keyring."""
    await finish_turn(db, turn_id, outcome, conversation_cipher(TEST_KEYS, conversation))


def message_row(
    conversation: AiConversation,
    turn_id: UUID,
    *,
    position: int,
    role: str,
    content: list[dict[str, Any]],
    sources: list[dict[str, Any]] | None = None,
) -> AiMessage:
    """A message row for the conversation, with `content` sealed as the store seals it."""
    message_id = uuid4()
    sealed = conversation_cipher(TEST_KEYS, conversation).seal_text(
        json.dumps(content), "ai_messages", "content_ciphertext", message_id
    )
    return AiMessage(
        id=message_id,
        tenant_id=conversation.tenant_id,
        person_id=conversation.person_id,
        conversation_id=conversation.id,
        turn_id=turn_id,
        position=position,
        role=role,
        content_ciphertext=sealed,
        sources=sources,
    )


async def turn_row(
    db: AsyncSession, conversation_id: UUID, turn_id: UUID, question: str, **columns: Any
) -> AiTurn:
    """A turn row for a conversation that is already flushed, with the question sealed."""
    conversation = await db.get(AiConversation, conversation_id)
    assert conversation is not None
    sealed = conversation_cipher(TEST_KEYS, conversation).seal_text(
        question, "ai_turns", "question_ciphertext", turn_id
    )
    return AiTurn(
        id=turn_id,
        tenant_id=conversation.tenant_id,
        person_id=conversation.person_id,
        conversation_id=conversation_id,
        question_ciphertext=sealed,
        **columns,
    )
