"""A denial's note is stored sealed (migration 0018, ADR 0015's amendment).

The row holds a key ID, a wrapped key, and ciphertext, never the words. The people who could read
the note before still read it, through the real service and routes; a list opens only the rows that
have one; the 300-character limit is the service's. The migration's data step is tested on a
temporary table, never on the shared database's real one.
"""

import importlib.util
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import insert, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.encryption import DecryptionFailed, KeyProvider
from app.db.models import TimeOffRequest
from app.db.tenancy import TenantContext, tenant_session
from app.modules.timeoff import service
from app.modules.timeoff.notes import NOTE_COLUMN, NOTES_TABLE, open_note, seal_note
from app.modules.timeoff.service import Decided
from tests.integration.conftest import (
    TEST_KEYS,
    MakeTenant,
    OpenBrowser,
    opened_note,
    sealed_note_columns,
)
from tests.integration.test_case_service import WatchedKeys
from tests.integration.test_timeoff_routes import StartWorld, World, far
from tests.integration.test_timeoff_service import NOW as SERVICE_NOW
from tests.integration.test_timeoff_service import (
    decide_as,
    get_request,
    make_org,
    put_request,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def start(
    open_browser: OpenBrowser, app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> StartWorld:
    """A sandbox signed in as a persona, as test_timeoff_routes.py builds one."""

    def begin(persona: str = "priya", *, now: datetime | None = None) -> World:
        browser = open_browser()
        sandbox = browser.start_sandbox(persona)
        return World(browser, sandbox, app_engine, owner_engine, now or datetime.now(UTC))

    return begin


NOTE = "ZEBRA-NOTE-4417 her mother is ill and the week is short-handed"
MIGRATION = Path(__file__).resolve().parents[2] / "migrations/versions/0018_seal_denial_notes.py"


async def raw_row(owner: AsyncEngine, request_id: UUID) -> dict[str, Any]:
    """The whole stored row, read as the database owner (which sees every row)."""
    async with owner.connect() as connection:
        row = (
            (
                await connection.execute(
                    text("SELECT * FROM time_off_requests WHERE id = :id"), {"id": request_id}
                )
            )
            .mappings()
            .one()
        )
    return dict(row)


def everything_in(row: dict[str, Any]) -> bytes:
    """Every column of the row as bytes, to look for the note's words in."""
    parts: list[bytes] = []
    for value in row.values():
        parts.append(bytes(value) if isinstance(value, bytes | memoryview) else str(value).encode())
    return b"\n".join(parts)


# --- What is stored -------------------------------------------------------------------------------


async def test_a_denial_stores_the_note_sealed_and_nowhere_in_plaintext(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    org = await make_org(app_engine, make_tenant)
    request_id = await put_request(app_engine, org, org.report, SERVICE_NOW.date())

    result = await decide_as(app_engine, org, org.manager, request_id, "deny", f"  {NOTE}  ")

    assert isinstance(result, Decided)
    row = await raw_row(owner_engine, request_id)
    assert "decision_note" not in row
    assert row["note_key_id"]
    assert row["note_wrapped_key"]
    assert row["note_ciphertext"]
    assert b"ZEBRA" not in everything_in(row)
    assert NOTE.encode() not in everything_in(row)
    assert b"mother" not in everything_in(row)
    assert opened_note(await get_request(app_engine, org, request_id)) == NOTE


@pytest.mark.parametrize(
    ("decision", "note"),
    [("approve", None), ("deny", None), ("deny", "   ")],
    ids=["an approval", "a denial with no note", "a denial with a blank note"],
)
async def test_a_decision_with_no_note_leaves_the_note_columns_empty(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    make_tenant: MakeTenant,
    decision: str,
    note: str | None,
) -> None:
    org = await make_org(app_engine, make_tenant)
    request_id = await put_request(app_engine, org, org.report, SERVICE_NOW.date())

    result = await decide_as(app_engine, org, org.manager, request_id, decision, note)

    assert isinstance(result, Decided)
    row = await raw_row(owner_engine, request_id)
    assert (row["note_key_id"], row["note_wrapped_key"], row["note_ciphertext"]) == (None,) * 3


async def test_each_noted_request_has_a_data_key_of_its_own(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    org = await make_org(app_engine, make_tenant)
    first = await put_request(app_engine, org, org.report, SERVICE_NOW.date())
    second = await put_request(app_engine, org, org.peer, SERVICE_NOW.date())
    await decide_as(app_engine, org, org.manager, first, "deny", NOTE)
    await decide_as(app_engine, org, org.coo, second, "deny", NOTE)

    one, two = await raw_row(owner_engine, first), await raw_row(owner_engine, second)

    assert one["note_wrapped_key"] != two["note_wrapped_key"]
    assert one["note_ciphertext"] != two["note_ciphertext"]


async def test_a_note_does_not_open_on_another_request(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    """The request is part of the associated data: a note copied onto another row is unreadable."""
    org = await make_org(app_engine, make_tenant)
    request_id = await put_request(app_engine, org, org.report, SERVICE_NOW.date())
    await decide_as(app_engine, org, org.manager, request_id, "deny", NOTE)
    row = await raw_row(owner_engine, request_id)

    with pytest.raises(DecryptionFailed):
        open_note(
            TEST_KEYS,
            org.tenant.id,
            uuid4(),
            key_id=row["note_key_id"],
            wrapped_key=bytes(row["note_wrapped_key"]),
            ciphertext=bytes(row["note_ciphertext"]),
        )


# --- The checks -----------------------------------------------------------------------------------


async def test_the_checks_refuse_a_sealed_note_on_a_row_that_is_not_denied_and_a_partial_set(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    org = await make_org(app_engine, make_tenant)
    request_id = await put_request(app_engine, org, org.report, SERVICE_NOW.date())
    sealed = sealed_note_columns(org.tenant.id, request_id, NOTE)

    for values in (
        # A sealed note on a pending request.
        sealed,
        # A sealed note on an approval.
        {"status": "approved", "decided_by": org.manager, "decided_at": SERVICE_NOW, **sealed},
        # Two of the three, on a denial.
        {
            "status": "denied",
            "decided_by": org.manager,
            "decided_at": SERVICE_NOW,
            "note_key_id": sealed["note_key_id"],
            "note_ciphertext": sealed["note_ciphertext"],
        },
    ):
        with pytest.raises(IntegrityError):
            async with tenant_session(app_engine, TenantContext(org.tenant.id, None)) as session:
                await session.execute(
                    insert(TimeOffRequest).values(
                        id=uuid4(),
                        tenant_id=org.tenant.id,
                        person_id=org.report,
                        type="pto",
                        start_date=SERVICE_NOW.date(),
                        end_date=SERVICE_NOW.date(),
                        amount_minutes=480,
                        created_via="ui",
                        **{"status": "pending", **values},
                    )
                )


# --- Who reads it ---------------------------------------------------------------------------------


async def pending_request_of_priya(world: World) -> UUID:
    """A pending PTO request of Priya's, on a weekday well after the seeded history."""
    day = world.today + timedelta(days=90)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return await world.put("priya", day)


async def test_the_person_their_manager_and_hr_read_the_note_through_the_routes(
    start: StartWorld,
) -> None:
    """Marcus denies Zara's request through the page's route; the note is returned to him and then
    read by Zara, Marcus, and HR as before (and by no one the request is hidden from)."""
    world = start("marcus", now=far())
    request_id = await pending_request_of_priya(world)

    response = world.post(
        f"/requests/{request_id}/decision", {"decision": "deny", "note": f" {NOTE} "}
    )
    assert response.status_code == 200, response.text
    assert response.json()["decisionNote"] == NOTE

    seen: dict[str, str | None] = {}
    for persona in ("priya", "marcus", "dana"):
        world.switch(persona)
        read = world.get(f"/requests/{request_id}")
        assert read.status_code == 200, (persona, read.text)
        seen[persona] = read.json()["decisionNote"]
    assert seen == {"priya": NOTE, "marcus": NOTE, "dana": NOTE}
    # The lists carry it too.
    world.switch("marcus")
    decided = world.get("/requests", scope="decided").json()["items"]
    assert [item["decisionNote"] for item in decided if item["id"] == str(request_id)] == [NOTE]


async def test_a_list_unwraps_a_key_only_for_the_rows_that_have_a_note(
    start: StartWorld,
) -> None:
    world = start("priya", now=far())
    day = world.today + timedelta(days=10)
    person = world.person("priya")
    decider = world.person("marcus")
    noted = {uuid4() for _ in range(3)}
    ids = [*noted, *(uuid4() for _ in range(197))]
    rows: list[dict[str, Any]] = []
    for request_id in ids:
        rows.append(
            {
                "id": request_id,
                "tenant_id": world.tenant_id,
                "person_id": person,
                "type": "pto",
                "start_date": day,
                "end_date": day,
                "amount_minutes": 480,
                "status": "denied",
                "created_via": "ui",
                "decided_by": decider,
                "decided_at": world.now,
                **sealed_note_columns(
                    world.tenant_id, request_id, NOTE if request_id in noted else None
                ),
            }
        )
    async with tenant_session(world.engine, TenantContext(world.tenant_id, None)) as session:
        await session.execute(insert(TimeOffRequest), rows)
    watched = WatchedKeys()
    world.browser.client.app.state.keys = watched  # type: ignore[attr-defined]

    response = world.get("/requests", scope="mine", **{"from": str(day), "to": str(day)})

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert len(items) == 200
    assert sorted(i["id"] for i in items if i["decisionNote"] == NOTE) == sorted(map(str, noted))
    assert watched.unwraps == 3


async def test_someone_who_cannot_read_the_request_gets_no_note(start: StartWorld) -> None:
    world = start("marcus", now=far())
    request_id = await pending_request_of_priya(world)
    assert (
        world.post(
            f"/requests/{request_id}/decision", {"decision": "deny", "note": NOTE}
        ).status_code
        == 200
    )

    world.switch("mateo")
    response = world.get(f"/requests/{request_id}")

    assert response.status_code == 404
    assert NOTE not in response.text


async def test_a_note_that_does_not_open_just_does_not_show_and_the_page_still_answers(
    start: StartWorld, owner_engine: AsyncEngine, caplog: pytest.LogCaptureFixture
) -> None:
    world = start("marcus", now=far())
    request_id = await pending_request_of_priya(world)
    assert (
        world.post(
            f"/requests/{request_id}/decision", {"decision": "deny", "note": NOTE}
        ).status_code
        == 200
    )
    async with owner_engine.begin() as connection:
        await connection.execute(text("SET LOCAL session_replication_role = replica"))
        await connection.execute(
            text(
                "UPDATE time_off_requests SET note_ciphertext ="
                " set_byte(note_ciphertext, 0, get_byte(note_ciphertext, 0) # 255) WHERE id = :id"
            ),
            {"id": request_id},
        )

    with caplog.at_level(logging.WARNING):
        listed = world.get("/requests", scope="decided")
        one = world.get(f"/requests/{request_id}")

    assert listed.status_code == 200, listed.text
    assert one.status_code == 200, one.text
    [row] = [i for i in listed.json()["items"] if i["id"] == str(request_id)]
    assert row["decisionNote"] is None
    assert one.json()["decisionNote"] is None
    lines = [r.getMessage() for r in caplog.records if "denial note" in r.getMessage()]
    assert lines
    assert all(str(request_id) in line for line in lines)
    assert "ZEBRA" not in caplog.text


# --- The length limit -----------------------------------------------------------------------------


async def test_the_service_refuses_a_note_over_300_characters_and_stores_nothing(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    org = await make_org(app_engine, make_tenant)
    request_id = await put_request(app_engine, org, org.report, SERVICE_NOW.date())

    with pytest.raises(ValueError, match="at most 300"):
        await decide_as(app_engine, org, org.manager, request_id, "deny", "x" * 301)

    assert (await raw_row(owner_engine, request_id))["status"] == "pending"
    assert service.checked_note("x" * 300) == "x" * 300


# --- The migration's data step --------------------------------------------------------------------


def migration_module() -> Any:
    spec = importlib.util.spec_from_file_location("migration_0018", MIGRATION)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_migration_and_the_app_agree_on_where_a_note_lives() -> None:
    module = migration_module()
    assert (module.TABLE, module.COLUMN) == (NOTES_TABLE, NOTE_COLUMN)


# Only the columns the data step reads and writes. A temporary table shadows the real one for this
# transaction (pg_temp comes first in the search path), so nothing real is touched.
SCRATCH = """
    CREATE TEMP TABLE time_off_requests (
        id uuid PRIMARY KEY, tenant_id uuid NOT NULL, decision_note text,
        note_key_id text, note_wrapped_key bytea, note_ciphertext bytea
    ) ON COMMIT DROP
"""


class Loader:
    """A key loader that counts its calls, so a test can see the keyring is not read needlessly."""

    def __init__(self, keys: KeyProvider = TEST_KEYS) -> None:
        self.calls = 0
        self.keys = keys

    def __call__(self) -> KeyProvider:
        self.calls += 1
        return self.keys


async def test_the_data_step_seals_an_existing_note_and_the_downgrade_opens_it(
    owner_engine: AsyncEngine,
) -> None:
    module = migration_module()
    tenant_id, noted, blank, plain = uuid4(), uuid4(), uuid4(), uuid4()
    up, down = Loader(), Loader()

    async with owner_engine.begin() as connection:
        await connection.execute(text(SCRATCH))
        for request_id, note in ((noted, NOTE), (blank, "   "), (plain, None)):
            await connection.execute(
                text(
                    "INSERT INTO time_off_requests (id, tenant_id, decision_note)"
                    " VALUES (:i, :t, :n)"
                ),
                {"i": request_id, "t": tenant_id, "n": note},
            )
        sealed = await connection.run_sync(lambda c: module.seal_existing_notes(c, up))
        rows = {
            r.id: r
            for r in (await connection.execute(text("SELECT * FROM time_off_requests"))).all()
        }

        assert sealed == 1
        assert all(r.decision_note is None for r in rows.values())
        assert rows[noted].note_ciphertext is not None
        assert NOTE.encode() not in bytes(rows[noted].note_ciphertext)
        # The app opens what the migration sealed.
        assert (
            open_note(
                TEST_KEYS,
                tenant_id,
                noted,
                key_id=rows[noted].note_key_id,
                wrapped_key=bytes(rows[noted].note_wrapped_key),
                ciphertext=bytes(rows[noted].note_ciphertext),
            )
            == NOTE
        )
        # A blank note, and no note, both end as no note.
        for other in (blank, plain):
            assert (rows[other].note_key_id, rows[other].note_ciphertext) == (None, None)

        opened = await connection.run_sync(lambda c: module.open_sealed_notes(c, down))
        back = {
            r.id: r.decision_note
            for r in (await connection.execute(text("SELECT * FROM time_off_requests"))).all()
        }
        left: int = (
            await connection.execute(
                text("SELECT count(*) FROM time_off_requests WHERE note_ciphertext IS NOT NULL")
            )
        ).scalar_one()

    assert (up.calls, down.calls, opened) == (1, 1, 1)
    assert back[noted] == NOTE
    assert (back[blank], back[plain], left) == (None, None, 0)


async def test_a_note_the_app_sealed_opens_in_the_downgrade(owner_engine: AsyncEngine) -> None:
    module = migration_module()
    tenant_id, request_id = uuid4(), uuid4()
    sealed = seal_note(TEST_KEYS, tenant_id, request_id, NOTE)

    async with owner_engine.begin() as connection:
        await connection.execute(text(SCRATCH))
        await connection.execute(
            text(
                "INSERT INTO time_off_requests (id, tenant_id, note_key_id, note_wrapped_key,"
                " note_ciphertext) VALUES (:i, :t, :k, :w, :c)"
            ),
            {
                "i": request_id,
                "t": tenant_id,
                "k": sealed.key_id,
                "w": sealed.wrapped_key,
                "c": sealed.ciphertext,
            },
        )
        await connection.run_sync(lambda c: module.open_sealed_notes(c, Loader()))
        note: str = (
            await connection.execute(text("SELECT decision_note FROM time_off_requests"))
        ).scalar_one()

    assert note == NOTE


async def test_the_data_step_reads_no_keyring_when_no_row_has_a_note(
    owner_engine: AsyncEngine,
) -> None:
    module = migration_module()

    def refuse() -> KeyProvider:
        msg = "the keyring must not be read for an empty table"
        raise AssertionError(msg)

    loader: Callable[[], KeyProvider] = refuse
    async with owner_engine.begin() as connection:
        await connection.execute(text(SCRATCH))
        await connection.execute(
            text("INSERT INTO time_off_requests (id, tenant_id) VALUES (:i, :t)"),
            {"i": uuid4(), "t": uuid4()},
        )
        sealed = await connection.run_sync(lambda c: module.seal_existing_notes(c, loader))
        opened = await connection.run_sync(lambda c: module.open_sealed_notes(c, loader))

    assert (sealed, opened) == (0, 0)


@pytest.mark.parametrize(("app_env", "refused"), [("development", True), ("test", False)])
def test_the_data_step_never_seals_real_notes_under_the_test_key(
    monkeypatch: pytest.MonkeyPatch, app_env: str, refused: bool
) -> None:
    import app.core.config
    from app.core.config import Settings

    migration = migration_module()
    settings = Settings(
        app_env=app_env,
        encryption_keyring=SecretStr("test:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="),
        encryption_keyring_file=None,
    )
    monkeypatch.setattr(app.core.config, "get_settings", lambda: settings)

    if refused:
        with pytest.raises(ValueError, match="only APP_ENV=test accepts"):
            migration.settings_key_loader()
    else:
        assert migration.settings_key_loader().uses_test_key
