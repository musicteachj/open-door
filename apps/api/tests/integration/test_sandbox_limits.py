"""The limits on starting sandboxes: per address an hour and a day, and all addresses a UTC day.

Every test uses addresses of its own, so counts left by other tests do not matter, and the rows it
backdates are removed when it ends.
"""

import asyncio
import secrets
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from datetime import timedelta
from typing import Any
from uuid import UUID

import httpx2 as httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.ai.admission import seconds_until_next_utc_day
from app.core.config import Settings
from app.db.locks import database_now
from app.db.tenancy import NO_TENANT, tenant_session
from app.main import build_key_provider, create_app
from app.modules.identity.cookies import SESSION_COOKIE
from app.modules.sandbox import seed, service, texts
from app.modules.sandbox.limits import StartLimitError, StartLimits, address_hash
from app.modules.sandbox.service import create_sandbox
from app.modules.sandbox.turnstile import DUMMY_TOKEN
from tests.integration.conftest import BrowserClient, session_cookie

pytestmark = pytest.mark.integration

BODY = {"persona": "priya", "turnstileToken": DUMMY_TOKEN}
HIGH = 1_000_000


def fresh_address() -> str:
    """An IPv4 address no other test uses (the 198.18.0.0/15 benchmarking range)."""
    return f"198.{18 + secrets.randbelow(2)}.{secrets.randbelow(256)}.{1 + secrets.randbelow(254)}"


def limited(settings: Settings, **limits: int) -> Settings:
    return settings.model_copy(
        update={
            "sandbox_starts_per_hour": HIGH,
            "sandbox_starts_per_day": HIGH,
            "sandbox_starts_daily_total": HIGH,
            **limits,
        }
    )


def key_of(settings: Settings) -> bytes:
    return settings.sandbox_ip_hash_key.get_secret_value().encode()


@contextmanager
def visitor(
    settings: Settings, address: str, created_tenant_ids: list[UUID]
) -> Iterator[BrowserClient]:
    client = BrowserClient(
        create_app(settings),
        base_url="https://testserver",
        client=(address, 50000),
        headers={"Sec-Fetch-Site": "same-origin"},
    )
    with client:
        yield client


def start(client: BrowserClient, created: list[UUID], **extra: Any) -> httpx.Response:
    response = client.post("/api/v1/sandboxes", json={**BODY, **extra})
    if response.status_code == 201:
        created.append(UUID(response.json()["tenant"]["id"]))
    return response


@pytest.fixture
async def backdated(owner_engine: AsyncEngine) -> AsyncIterator[Any]:
    """Add start rows for an address hash, dated in the past. They are removed afterward."""
    ids: list[UUID] = []

    async def add(ip_hash: bytes, ages: list[timedelta]) -> None:
        async with owner_engine.begin() as connection:
            for age in ages:
                row = await connection.execute(
                    text("INSERT INTO sandbox_starts (ip_hash) VALUES (:h) RETURNING id"),
                    {"h": ip_hash},
                )
                new_id: UUID = row.scalar_one()
                ids.append(new_id)
                # The insert trigger stamps now(); an update is not stamped.
                await connection.execute(
                    text(
                        "UPDATE sandbox_starts SET created_at = now() - CAST(:age AS interval)"
                        " WHERE id = :id"
                    ),
                    {"age": age, "id": new_id},
                )

    yield add
    async with owner_engine.begin() as connection:
        await connection.execute(
            text("DELETE FROM sandbox_starts WHERE id = ANY(CAST(:ids AS uuid[]))"), {"ids": ids}
        )


async def rows_for(owner_engine: AsyncEngine, ip_hash: bytes) -> int:
    async with owner_engine.connect() as connection:
        result = await connection.execute(
            text("SELECT count(*) FROM sandbox_starts WHERE ip_hash = :h"), {"h": ip_hash}
        )
        return int(result.scalar_one())


def retry_after(response: httpx.Response) -> int:
    return int(response.headers["retry-after"])


async def test_the_sixth_start_in_an_hour_is_refused(
    database_settings: Settings, created_tenant_ids: list[UUID], owner_engine: AsyncEngine
) -> None:
    settings = limited(database_settings, sandbox_starts_per_hour=5)
    address = fresh_address()
    with visitor(settings, address, created_tenant_ids) as client:
        for _ in range(5):
            assert start(client, created_tenant_ids).status_code == 201
        sixth = start(client, created_tenant_ids)

    assert sixth.status_code == 429
    problem = sixth.json()
    assert problem["type"] == "sandbox-start-limit"
    assert problem["detail"] == texts.START_LIMIT_TEXT.format(wait="about 1 hour")
    # The oldest start in the hour was seconds ago, so the wait is just under an hour.
    assert 3590 <= retry_after(sixth) <= 3600
    assert await rows_for(owner_engine, address_hash(key_of(settings), address)) == 5


async def test_the_twenty_first_start_in_a_day_is_refused(
    database_settings: Settings,
    created_tenant_ids: list[UUID],
    owner_engine: AsyncEngine,
    backdated: Any,
) -> None:
    settings = limited(database_settings, sandbox_starts_per_hour=5, sandbox_starts_per_day=20)
    address = fresh_address()
    ip_hash = address_hash(key_of(settings), address)
    # Twenty starts, none in the last two hours, the oldest 23.5 hours ago.
    ages = [timedelta(hours=2 + i, minutes=30 if i == 0 else 0) for i in range(20)]
    ages[-1] = timedelta(hours=23, minutes=30)
    await backdated(ip_hash, ages)

    with visitor(settings, address, created_tenant_ids) as client:
        refused = start(client, created_tenant_ids)

    assert refused.status_code == 429
    assert refused.json()["type"] == "sandbox-start-limit"
    assert refused.json()["detail"] == texts.START_LIMIT_TEXT.format(wait="30 minutes")
    assert 1790 <= retry_after(refused) <= 1800
    assert await rows_for(owner_engine, ip_hash) == 20


async def test_the_wait_is_the_longest_of_the_limits_that_bind(
    database_settings: Settings, created_tenant_ids: list[UUID], backdated: Any
) -> None:
    settings = limited(database_settings, sandbox_starts_per_hour=5, sandbox_starts_per_day=20)
    address = fresh_address()
    # Five starts in the last ten minutes (the hourly limit binds for another 50 minutes) and
    # twenty in the day, the oldest two hours ago (the daily limit binds for another 22 hours).
    ages = [timedelta(minutes=10)] * 5 + [timedelta(hours=2)] * 15
    await backdated(address_hash(key_of(settings), address), ages)

    with visitor(settings, address, created_tenant_ids) as client:
        refused = start(client, created_tenant_ids)

    assert refused.status_code == 429
    assert 22 * 3600 - 10 <= retry_after(refused) <= 22 * 3600 + 1


async def test_a_count_over_its_limit_waits_for_the_row_that_brings_it_back_under(
    database_settings: Settings, created_tenant_ids: list[UUID], backdated: Any
) -> None:
    # The limit was lowered after four starts: two must leave the hour before one more is allowed,
    # so the wait ends when the second oldest does (30 minutes from now), not the oldest.
    settings = limited(database_settings, sandbox_starts_per_hour=2)
    address = fresh_address()
    ages = [timedelta(minutes=minutes) for minutes in (50, 40, 30, 10)]
    await backdated(address_hash(key_of(settings), address), ages)
    with visitor(settings, address, created_tenant_ids) as client:
        refused = start(client, created_tenant_ids)
    assert refused.status_code == 429
    assert 30 * 60 - 10 <= retry_after(refused) <= 30 * 60 + 1


async def test_a_daily_count_over_its_limit_uses_the_right_row(
    database_settings: Settings, created_tenant_ids: list[UUID], backdated: Any
) -> None:
    settings = limited(database_settings, sandbox_starts_per_day=2)
    address = fresh_address()
    # Three starts a day apart from the edge: hours 20, 10, 5 ago. Two must leave, so the wait
    # ends when the 10-hour-old one does, in 14 hours.
    ages = [timedelta(hours=hours) for hours in (20, 10, 5)]
    await backdated(address_hash(key_of(settings), address), ages)
    with visitor(settings, address, created_tenant_ids) as client:
        refused = start(client, created_tenant_ids)
    assert refused.status_code == 429
    assert 14 * 3600 - 10 <= retry_after(refused) <= 14 * 3600 + 1


async def test_a_start_older_than_a_day_does_not_count(
    database_settings: Settings, created_tenant_ids: list[UUID], backdated: Any
) -> None:
    settings = limited(database_settings, sandbox_starts_per_day=1)
    address = fresh_address()
    await backdated(address_hash(key_of(settings), address), [timedelta(hours=24, minutes=1)])
    with visitor(settings, address, created_tenant_ids) as client:
        assert start(client, created_tenant_ids).status_code == 201


async def test_the_start_that_exceeds_the_days_total_is_refused(
    database_settings: Settings, created_tenant_ids: list[UUID], owner_engine: AsyncEngine
) -> None:
    async with owner_engine.connect() as connection:
        so_far: int = (
            await connection.execute(
                text(
                    "SELECT count(*) FROM sandbox_starts WHERE created_at >="
                    " (date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC')"
                )
            )
        ).scalar_one()
    settings = limited(database_settings, sandbox_starts_daily_total=int(so_far) + 2)
    with visitor(settings, fresh_address(), created_tenant_ids) as one:
        assert start(one, created_tenant_ids).status_code == 201
    with visitor(settings, fresh_address(), created_tenant_ids) as two:
        assert start(two, created_tenant_ids).status_code == 201
    with visitor(settings, fresh_address(), created_tenant_ids) as three:
        refused = start(three, created_tenant_ids)

    assert refused.status_code == 429
    assert refused.json()["type"] == "sandbox-day-limit"
    assert refused.json()["detail"] == texts.DAY_LIMIT_TEXT
    async with tenant_session(owner_engine, NO_TENANT) as db:
        now = await database_now(db)
    assert abs(retry_after(refused) - seconds_until_next_utc_day(now)) <= 5


async def test_two_ipv6_addresses_in_one_64_count_as_one(
    database_settings: Settings, created_tenant_ids: list[UUID]
) -> None:
    settings = limited(database_settings, sandbox_starts_per_hour=1)
    block = f"2001:db8:{secrets.randbelow(65536):x}:{secrets.randbelow(65536):x}"
    with visitor(settings, f"{block}::1", created_tenant_ids) as first:
        assert start(first, created_tenant_ids).status_code == 201
    with visitor(settings, f"{block}:aaaa:bbbb:cccc:dddd", created_tenant_ids) as second:
        assert start(second, created_tenant_ids).status_code == 429
    other = f"2001:db8:{secrets.randbelow(65536):x}:ffff::1"
    with visitor(settings, other, created_tenant_ids) as third:
        assert start(third, created_tenant_ids).status_code == 201


async def test_two_ipv4_addresses_do_not_share_a_count(
    database_settings: Settings, created_tenant_ids: list[UUID]
) -> None:
    settings = limited(database_settings, sandbox_starts_per_hour=1)
    with visitor(settings, fresh_address(), created_tenant_ids) as first:
        assert start(first, created_tenant_ids).status_code == 201
    with visitor(settings, fresh_address(), created_tenant_ids) as second:
        assert start(second, created_tenant_ids).status_code == 201


async def test_the_stored_value_is_the_keyed_hash_never_the_address(
    database_settings: Settings, created_tenant_ids: list[UUID], owner_engine: AsyncEngine
) -> None:
    address = fresh_address()
    other_key = database_settings.model_copy(
        update={"sandbox_ip_hash_key": database_settings.sandbox_ip_hash_key.__class__("z" * 40)}
    )
    for settings in (limited(database_settings), limited(other_key)):
        with visitor(settings, address, created_tenant_ids) as client:
            assert start(client, created_tenant_ids).status_code == 201

    first = address_hash(key_of(database_settings), address)
    second = address_hash(key_of(other_key), address)
    assert first != second
    assert await rows_for(owner_engine, first) == 1
    assert await rows_for(owner_engine, second) == 1
    async with owner_engine.connect() as connection:
        stored: Any = (
            (
                await connection.execute(
                    text("SELECT ip_hash FROM sandbox_starts WHERE ip_hash = ANY(:both)"),
                    {"both": [first, second]},
                )
            )
            .scalars()
            .all()
        )
    assert all(len(value) == 32 and address.encode() not in bytes(value) for value in stored)


async def test_two_starts_at_once_with_one_left_let_exactly_one_through(
    database_settings: Settings,
    created_tenant_ids: list[UUID],
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    backdated: Any,
) -> None:
    settings = limited(database_settings, sandbox_starts_per_hour=5)
    limits = StartLimits(per_hour=5, per_day=HIGH, daily_total=HIGH)
    ip_hash = address_hash(key_of(settings), fresh_address())
    await backdated(ip_hash, [timedelta(minutes=10)] * 4)
    keys = build_key_provider(settings)

    results = await asyncio.gather(
        *(create_sandbox(app_engine, "priya", None, keys, ip_hash, limits) for _ in range(2)),
        return_exceptions=True,
    )

    made = [result for result in results if not isinstance(result, BaseException)]
    refused = [result for result in results if isinstance(result, StartLimitError)]
    assert len(made) == 1
    assert len(refused) == 1
    created_tenant_ids.append(made[0].tenant_id)
    assert await rows_for(owner_engine, ip_hash) == 5


async def test_a_seed_that_fails_after_the_reservation_still_counts(
    database_settings: Settings,
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Deliberately conservative: the start is recorded in its own transaction before the seed.
    async def failing_seed(*_: Any) -> None:
        raise RuntimeError("seed failed")

    monkeypatch.setattr("app.modules.sandbox.service.insert_company", failing_seed)
    limits = StartLimits(per_hour=5, per_day=HIGH, daily_total=HIGH)
    ip_hash = address_hash(key_of(database_settings), fresh_address())

    with pytest.raises(RuntimeError, match="seed failed"):
        await create_sandbox(
            app_engine, "priya", None, build_key_provider(database_settings), ip_hash, limits
        )

    assert await rows_for(owner_engine, ip_hash) == 1


async def test_the_global_lock_is_not_held_while_the_company_is_seeded(
    database_settings: Settings,
    created_tenant_ids: list[UUID],
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    in_seed = asyncio.Event()
    release = asyncio.Event()
    real_insert_company = seed.insert_company

    async def slow_seed(*args: Any) -> None:
        in_seed.set()
        await release.wait()
        await real_insert_company(*args)

    monkeypatch.setattr(service, "insert_company", slow_seed)
    limits = StartLimits(per_hour=5, per_day=HIGH, daily_total=HIGH)
    first_hash = address_hash(key_of(database_settings), fresh_address())
    second_hash = address_hash(key_of(database_settings), fresh_address())
    keys = build_key_provider(database_settings)

    first = asyncio.create_task(create_sandbox(app_engine, "priya", None, keys, first_hash, limits))
    try:
        await asyncio.wait_for(in_seed.wait(), 10)
        # The first start is mid-seed. Another start's reservation must not wait for it.
        await asyncio.wait_for(service.reserve_start(app_engine, second_hash, limits), 3)
        assert await rows_for(owner_engine, second_hash) == 1
    finally:
        release.set()
        created = await first
    created_tenant_ids.append(created.tenant_id)
    assert await rows_for(owner_engine, first_hash) == 1


async def test_a_pile_up_on_the_reservation_lock_answers_busy_not_a_long_wait(
    database_settings: Settings,
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sqlalchemy.exc import DBAPIError

    from app.db.errors import has_sqlstate
    from app.db.locks import SANDBOX_STARTS_NS

    monkeypatch.setattr(service, "RESERVE_LOCK_TIMEOUT", "200ms")
    limits = StartLimits(per_hour=5, per_day=HIGH, daily_total=HIGH)
    ip_hash = address_hash(key_of(database_settings), fresh_address())
    async with owner_engine.connect() as holder:
        await holder.execute(text(f"SELECT pg_advisory_xact_lock({SANDBOX_STARTS_NS}, 0)"))
        with pytest.raises(DBAPIError) as caught:
            await asyncio.wait_for(service.reserve_start(app_engine, ip_hash, limits), 5)
        await holder.rollback()
    assert has_sqlstate(caught.value, "55P03")
    assert await rows_for(owner_engine, ip_hash) == 0


async def test_a_refused_start_adds_no_row_and_leaves_the_old_session_alive(
    database_settings: Settings, created_tenant_ids: list[UUID], owner_engine: AsyncEngine
) -> None:
    settings = limited(database_settings, sandbox_starts_per_hour=1)
    address = fresh_address()
    with visitor(settings, address, created_tenant_ids) as client:
        first = start(client, created_tenant_ids)
        assert first.status_code == 201
        token = client.cookies[SESSION_COOKIE]

        refused = start(client, created_tenant_ids)

        assert refused.status_code == 429
        assert client.get("/api/v1/me", headers=session_cookie(token)).status_code == 200
    assert await rows_for(owner_engine, address_hash(key_of(settings), address)) == 1


async def test_a_start_refused_by_the_count_under_the_lock_keeps_the_old_session(
    database_settings: Settings,
    created_tenant_ids: list[UUID],
    owner_engine: AsyncEngine,
    backdated: Any,
) -> None:
    settings = limited(database_settings, sandbox_starts_per_hour=1)
    address = fresh_address()
    with visitor(settings, address, created_tenant_ids) as client:
        first = start(client, created_tenant_ids)
        assert first.status_code == 201
        token = client.cookies[SESSION_COOKIE]
        # Another start from this address lands after the page loaded: the count under the lock
        # is the one that refuses.
        await backdated(address_hash(key_of(settings), address), [timedelta(minutes=1)])

        refused = start(client, created_tenant_ids)

        assert refused.status_code == 429
        assert client.get("/api/v1/me", headers=session_cookie(token)).status_code == 200


async def test_a_start_that_times_out_on_the_lock_keeps_the_old_session(
    database_settings: Settings,
    created_tenant_ids: list[UUID],
    owner_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.db.locks import SANDBOX_STARTS_NS

    settings = limited(database_settings)
    address = fresh_address()
    with visitor(settings, address, created_tenant_ids) as client:
        first = start(client, created_tenant_ids)
        assert first.status_code == 201
        token = client.cookies[SESSION_COOKIE]
        monkeypatch.setattr(service, "RESERVE_LOCK_TIMEOUT", "200ms")
        async with owner_engine.connect() as holder:
            await holder.execute(text(f"SELECT pg_advisory_xact_lock({SANDBOX_STARTS_NS}, 0)"))
            busy = start(client, created_tenant_ids)
            await holder.rollback()

        assert busy.status_code == 503
        assert client.get("/api/v1/me", headers=session_cookie(token)).status_code == 200
    assert await rows_for(owner_engine, address_hash(key_of(settings), address)) == 1


async def test_only_a_trusted_proxy_forwarded_address_is_used(
    database_settings: Settings, created_tenant_ids: list[UUID], owner_engine: AsyncEngine
) -> None:
    settings = limited(database_settings)
    forged = fresh_address()
    peer = fresh_address()
    trusted_peer = "10.77.0.9"
    app = create_app(settings)
    wrapped = ProxyHeadersMiddleware(app, trusted_hosts=["10.77.0.0/16"])  # type: ignore[arg-type]
    async with app.router.lifespan_context(app):
        for client_address, expected in ((peer, peer), (trusted_peer, forged)):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(
                    app=wrapped,  # type: ignore[arg-type]
                    client=(client_address, 40000),
                ),
                base_url="https://testserver",
                headers={"Sec-Fetch-Site": "same-origin", "X-Forwarded-For": forged},
            ) as client:
                response = await client.post("/api/v1/sandboxes", json=BODY)
                assert response.status_code == 201, response.text
                created_tenant_ids.append(UUID(response.json()["tenant"]["id"]))
            counted = address_hash(key_of(settings), expected)
            assert await rows_for(owner_engine, counted) >= 1
    # The forged header from the untrusted peer counted for the peer, not for the forged address:
    # only the trusted proxy's request counted for `forged`.
    assert await rows_for(owner_engine, address_hash(key_of(settings), forged)) == 1
    assert await rows_for(owner_engine, address_hash(key_of(settings), trusted_peer)) == 0
