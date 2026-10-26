"""The time-off service, as the API's login runs it against real Postgres.

Every write takes the person's advisory lock before it reads, re-checks the policy and the status
under that lock, and records its audit event in the same transaction. The dates here are fixed and
hand-worked: today is Wednesday, 2026-10-21 in Denver (NOW is 18:00 UTC, noon there).

The company is small and built here, not seeded: a COO, below them a manager, below them a
report, plus a peer, an Oakland employee, and the tenant's HR partner (Dana, from `make_tenant`).
Nobody has an opening or a request until a test inserts one, so nothing depends on what the seed
writes.
"""

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, tzinfo
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import insert, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app import policy
from app.db.models import (
    AuditEvent,
    Holiday,
    Location,
    Person,
    Tenant,
    TimeOffOpening,
    TimeOffRequest,
)
from app.db.tenancy import TenantContext, tenant_session
from app.domain.timeoff.evaluate import NewRequest
from app.domain.timeoff.model import STATES, State
from app.domain.timeoff.rules import RULES, Rule, sick_grant_rule
from app.modules.identity.actor import load_actor
from app.modules.timeoff import queries, service
from app.modules.timeoff.service import (
    Balances,
    Canceled,
    Created,
    Decided,
    Refused,
    RuleRef,
)
from app.policy import Action, Actor
from tests.integration.conftest import (
    MakeTenant,
    SampleTenant,
    audit_events,
    write_assistant_rows,
)

pytestmark = pytest.mark.integration

# Wednesday, 2026-10-21. Noon in Denver and 11:00 in Oakland.
NOW = datetime(2026, 10, 21, 18, 0, tzinfo=UTC)
TODAY = date(2026, 10, 21)
# 03:00 UTC on the 21st is still the evening of the 20th in Oakland (UTC-7).
LATE_EVENING_UTC = datetime(2026, 10, 21, 3, 0, tzinfo=UTC)
OAKLAND_TODAY = date(2026, 10, 20)
LOCK_NAMESPACE = 4403


@dataclass(frozen=True)
class Org:
    tenant: SampleTenant
    coo: UUID
    manager: UUID
    report: UUID
    peer: UUID
    oakland: UUID

    @property
    def hr(self) -> UUID:
        return self.tenant.hr_id


async def make_org(engine: AsyncEngine, make_tenant: MakeTenant) -> Org:
    tenant = await make_tenant()
    ids = {name: uuid4() for name in ("coo", "manager", "report", "peer", "oakland")}
    async with tenant_session(engine, TenantContext(tenant.id, None)) as session:
        template = (
            await session.execute(
                select(Person.department_id, Person.location_id).where(
                    Person.id == tenant.employee_id
                )
            )
        ).one()
        oakland_location = uuid4()
        await session.execute(
            insert(Location).values(
                id=oakland_location,
                tenant_id=tenant.id,
                code="OAK",
                name="Oakland store",
                city="Oakland",
                state="CA",
                timezone="America/Los_Angeles",
            )
        )

        async def add(name: str, manager_id: UUID | None, location_id: UUID) -> None:
            await session.execute(
                insert(Person).values(
                    id=ids[name],
                    tenant_id=tenant.id,
                    given_name=name.title(),
                    family_name="Test",
                    title="Associate",
                    department_id=template.department_id,
                    location_id=location_id,
                    manager_id=manager_id,
                    work_email=f"{name}@juniperrow.example",
                    employment_type="salaried",
                    hire_date=date(2024, 3, 4),
                )
            )

        await add("coo", None, template.location_id)
        await add("manager", ids["coo"], template.location_id)
        await add("report", ids["manager"], template.location_id)
        await add("peer", ids["coo"], template.location_id)
        await add("oakland", ids["manager"], oakland_location)
    return Org(tenant, **ids)


@asynccontextmanager
async def acting(
    engine: AsyncEngine, tenant_id: UUID, person_id: UUID
) -> AsyncIterator[tuple[AsyncSession, Actor]]:
    """One transaction as `person_id`, with the actor the server would load for them."""
    async with tenant_session(engine, TenantContext(tenant_id, person_id)) as db:
        actor = await load_actor(db, tenant_id, person_id)
        assert actor is not None
        yield db, actor


async def put_opening(
    engine: AsyncEngine, org: Org, person_id: UUID, as_of: date, amount_minutes: int
) -> None:
    async with tenant_session(engine, TenantContext(org.tenant.id, None)) as session:
        await session.execute(
            insert(TimeOffOpening).values(
                tenant_id=org.tenant.id,
                person_id=person_id,
                as_of=as_of,
                amount_minutes=amount_minutes,
            )
        )


async def put_request(
    engine: AsyncEngine,
    org: Org,
    person_id: UUID,
    start: date,
    end: date | None = None,
    *,
    type: str = "pto",
    status: str | None = None,
    amount_minutes: int = 480,
    partial_minutes: int | None = None,
) -> UUID:
    """Insert a request directly, as history or as a setup for a test. It does not go through the
    service, so it is not audited."""
    status = status or ("pending" if type == "pto" else "recorded")
    decided = status in {"approved", "denied"}
    request_id = uuid4()
    async with tenant_session(engine, TenantContext(org.tenant.id, None)) as session:
        await session.execute(
            insert(TimeOffRequest).values(
                id=request_id,
                tenant_id=org.tenant.id,
                person_id=person_id,
                type=type,
                start_date=start,
                end_date=end or start,
                partial_minutes=partial_minutes,
                amount_minutes=amount_minutes,
                status=status,
                created_via="ui",
                decided_by=org.manager if decided else None,
                decided_at=NOW if decided else None,
                canceled_at=NOW if status == "canceled" else None,
            )
        )
    return request_id


async def put_holiday(
    engine: AsyncEngine, org: Org, location_id: UUID, day: date, name: str
) -> None:
    async with tenant_session(engine, TenantContext(org.tenant.id, None)) as session:
        await session.execute(
            insert(Holiday).values(
                id=uuid4(),
                tenant_id=org.tenant.id,
                location_id=location_id,
                holiday_date=day,
                name=name,
            )
        )


async def location_of(engine: AsyncEngine, org: Org, person_id: UUID) -> UUID:
    async with tenant_session(engine, TenantContext(org.tenant.id, None)) as session:
        return (
            await session.execute(select(Person.location_id).where(Person.id == person_id))
        ).scalar_one()


async def put_proposal(db: AsyncSession, org: Org, person_id: UUID) -> UUID:
    """A pending proposal that belongs to `person_id`, inserted in the caller's transaction (the
    database refuses an audit event or a request whose proposal is not the actor's)."""
    proposal_id = uuid4()
    rows = await write_assistant_rows(db, org.tenant.id, person_id)
    await db.execute(
        text(
            "INSERT INTO ai_proposals (id, tenant_id, person_id, conversation_id, turn_id,"
            " action, payload, card, status, expires_at) VALUES (:id, :tenant_id, :person_id,"
            " :conversation_id, :turn_id, 'timeoff.request', CAST(:payload AS jsonb),"
            " CAST(:card AS jsonb), 'pending', now() + interval '15 minutes')"
        ),
        {
            "id": proposal_id,
            "tenant_id": org.tenant.id,
            "person_id": person_id,
            "conversation_id": rows.conversation_id,
            "turn_id": rows.turn_id,
            "payload": json.dumps({"type": "pto"}),
            "card": json.dumps({"title": "Request time off"}),
        },
    )
    return proposal_id


async def get_request(engine: AsyncEngine, org: Org, request_id: UUID) -> TimeOffRequest:
    async with tenant_session(engine, TenantContext(org.tenant.id, None)) as session:
        return (
            await session.execute(select(TimeOffRequest).where(TimeOffRequest.id == request_id))
        ).scalar_one()


async def requests_of(engine: AsyncEngine, org: Org, person_id: UUID) -> list[TimeOffRequest]:
    async with tenant_session(engine, TenantContext(org.tenant.id, None)) as session:
        query = select(TimeOffRequest).where(TimeOffRequest.person_id == person_id)
        return list((await session.execute(query)).scalars())


async def events(engine: AsyncEngine, org: Org, prefix: str = "timeoff.") -> list[AuditEvent]:
    return [e for e in await audit_events(engine, org.tenant.id) if e.action.startswith(prefix)]


def pto(start: date, end: date | None = None, partial: int | None = None) -> NewRequest:
    return NewRequest("pto", start, end or start, partial)


def sick(start: date, end: date | None = None, partial: int | None = None) -> NewRequest:
    return NewRequest("sick", start, end or start, partial)


def created(result: object) -> Created:
    assert isinstance(result, Created), result
    return result


def refused(result: object) -> Refused:
    assert isinstance(result, Refused), result
    return result


async def fund(engine: AsyncEngine, org: Org, person_id: UUID | None = None) -> None:
    """4,800 minutes (10 days) of PTO, as of October 1: a month-end that falls after today earns
    nothing yet, so exactly 4,800 is available."""
    await put_opening(engine, org, person_id or org.report, date(2026, 10, 1), 4800)


# ---------------------------------------------------------------------------------------------
# create


async def test_a_pto_request_is_pending_with_its_audit_event(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    org = await make_org(app_engine, make_tenant)
    # 3,000 as of January 1, plus nine month-ends (January to September) at 600 = 8,400 earned.
    await put_opening(app_engine, org, org.report, date(2026, 1, 1), 3000)

    async with acting(app_engine, org.tenant.id, org.report) as (db, actor):
        # Monday and Tuesday, 2026-11-09 and 2026-11-10: 2 days at 480 = 960 minutes.
        result = created(
            await service.create(
                db, actor, pto(date(2026, 11, 9), date(2026, 11, 10)), NOW, via="ui"
            )
        )

    row = await get_request(app_engine, org, result.request_id)
    assert (row.type, row.status, row.amount_minutes) == ("pto", "pending", 960)
    assert (row.start_date, row.end_date) == (date(2026, 11, 9), date(2026, 11, 10))
    assert (row.created_via, row.proposal_id, row.decided_by, row.decision_note) == (
        "ui",
        None,
        None,
        None,
    )
    (event,) = await events(app_engine, org)
    assert (event.action, event.via, event.actor_person_id) == (
        "timeoff.requested",
        "ui",
        org.report,
    )
    assert (event.target_type, event.target_id, event.proposal_id) == (
        "time_off_request",
        result.request_id,
        None,
    )
    assert event.before is None
    assert event.after == {
        "status": "pending",
        "type": "pto",
        "startDate": "2026-11-09",
        "endDate": "2026-11-10",
    }


async def test_a_sick_day_is_recorded_with_its_audit_event(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    org = await make_org(app_engine, make_tenant)

    async with acting(app_engine, org.tenant.id, org.report) as (db, actor):
        # Monday 2026-10-19, two days back, 4 hours: inside the 30-day window.
        result = created(
            await service.create(db, actor, sick(date(2026, 10, 19), partial=240), NOW, via="ui")
        )

    row = await get_request(app_engine, org, result.request_id)
    assert (row.type, row.status, row.amount_minutes, row.partial_minutes) == (
        "sick",
        "recorded",
        240,
        240,
    )
    (event,) = await events(app_engine, org)
    assert event.action == "timeoff.recorded"
    assert event.after == {
        "status": "recorded",
        "type": "sick",
        "startDate": "2026-10-19",
        "endDate": "2026-10-19",
    }


async def test_a_request_made_by_the_assistant_stores_and_audits_its_proposal(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    org = await make_org(app_engine, make_tenant)
    await fund(app_engine, org)

    async with acting(app_engine, org.tenant.id, org.report) as (db, actor):
        proposal_id = await put_proposal(db, org, org.report)
        result = created(
            await service.create(
                db, actor, pto(date(2026, 11, 9)), NOW, via="assistant", proposal_id=proposal_id
            )
        )

    row = await get_request(app_engine, org, result.request_id)
    assert (row.created_via, row.proposal_id) == ("assistant", proposal_id)
    (event,) = await events(app_engine, org)
    assert (event.via, event.proposal_id, event.action) == (
        "assistant",
        proposal_id,
        "timeoff.requested",
    )


@pytest.mark.parametrize(
    ("via", "with_proposal"),
    [("assistant", False), ("ui", True), ("system", False)],
)
async def test_a_proposal_goes_with_the_assistant_and_only_with_it(
    app_engine: AsyncEngine, make_tenant: MakeTenant, via: Any, with_proposal: bool
) -> None:
    org = await make_org(app_engine, make_tenant)
    await fund(app_engine, org)

    async with acting(app_engine, org.tenant.id, org.report) as (db, actor):
        with pytest.raises(ValueError, match=r"proposal|via"):
            await service.create(
                db,
                actor,
                pto(date(2026, 11, 9)),
                NOW,
                via=via,
                proposal_id=uuid4() if with_proposal else None,
            )


async def test_a_request_for_exactly_all_available_pto_succeeds(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    org = await make_org(app_engine, make_tenant)
    await fund(app_engine, org)

    async with acting(app_engine, org.tenant.id, org.report) as (db, actor):
        # Monday 2026-11-02 to Friday 2026-11-13: ten weekdays, 10 x 480 = 4,800 = all of it. If
        # the request counted against itself, it would need 9,600 and be refused.
        result = created(
            await service.create(
                db, actor, pto(date(2026, 11, 2), date(2026, 11, 13)), NOW, via="ui"
            )
        )

    assert (await get_request(app_engine, org, result.request_id)).amount_minutes == 4800
    assert [draw.available_after_minutes for draw in result.evaluation.draws] == [0]


async def test_a_request_the_engine_refuses_is_refused_with_its_code_and_writes_nothing(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    org = await make_org(app_engine, make_tenant)
    await fund(app_engine, org)

    async with acting(app_engine, org.tenant.id, org.report) as (db, actor):
        # Eleven weekdays is 5,280 minutes, more than the 4,800 available.
        result = refused(
            await service.create(
                db, actor, pto(date(2026, 11, 2), date(2026, 11, 16)), NOW, via="ui"
            )
        )
        # Saturday only: no scheduled day.
        weekend = refused(await service.create(db, actor, pto(date(2026, 11, 7)), NOW, via="ui"))

    assert result.code == "not-enough"
    assert result.evaluation is not None
    assert result.evaluation.problems == ("not-enough",)
    assert weekend.code == "no-scheduled-days"
    assert await requests_of(app_engine, org, org.report) == []
    assert await events(app_engine, org) == []


async def test_check_answers_for_the_actor_and_writes_nothing(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    org = await make_org(app_engine, make_tenant)
    await fund(app_engine, org)

    async with acting(app_engine, org.tenant.id, org.report) as (db, actor):
        fits = await service.check(db, actor, pto(date(2026, 11, 9)), NOW)
        past = await service.check(db, actor, pto(date(2026, 10, 20)), NOW)

    assert (fits.ok, fits.amount_minutes) == (True, 480)
    assert past.problems == ("out-of-range",)
    assert await requests_of(app_engine, org, org.report) == []
    assert await events(app_engine, org) == []


def deny_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the policy rule for requesting time off deny everyone."""
    monkeypatch.setattr(
        policy, "RULES", {Action.TIMEOFF_REQUEST: lambda actor, target, today: False}
    )


async def test_create_asks_the_policy_first_and_a_denial_is_not_allowed(
    app_engine: AsyncEngine, make_tenant: MakeTenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    org = await make_org(app_engine, make_tenant)
    await fund(app_engine, org)
    deny_requests(monkeypatch)

    async with acting(app_engine, org.tenant.id, org.report) as (db, actor):
        result = await service.create(db, actor, pto(date(2026, 11, 9)), NOW, via="ui")

    assert refused(result).code == "not-allowed"
    assert await requests_of(app_engine, org, org.report) == []
    assert await events(app_engine, org) == []


async def test_check_asks_the_policy_and_a_denial_raises_permission_error(
    app_engine: AsyncEngine, make_tenant: MakeTenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    org = await make_org(app_engine, make_tenant)
    await fund(app_engine, org)
    deny_requests(monkeypatch)

    async with acting(app_engine, org.tenant.id, org.report) as (db, actor):
        with pytest.raises(PermissionError):
            await service.check(db, actor, pto(date(2026, 11, 9)), NOW)


# ---------------------------------------------------------------------------------------------
# the lock


async def two_creates_that_each_fit_but_not_together(
    engine: AsyncEngine, org: Org, monkeypatch: pytest.MonkeyPatch
) -> list[Created | Refused]:
    """Run two creates for the report at once, each reading, then waiting a moment for the other.

    Without the lock both would have read before either wrote, so both would pass the balance
    check. With it the second create waits at the lock, so the first one's wait times out, it
    writes and commits, and only then does the second read: it sees the first request and is
    refused.
    """
    reads = 0
    both_have_read = asyncio.Event()
    real_load_requests = queries.load_requests

    async def load_then_wait(*args: Any, **kwargs: Any) -> Any:
        nonlocal reads
        loaded = await real_load_requests(*args, **kwargs)
        reads += 1
        if reads == 2:
            both_have_read.set()
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(both_have_read.wait(), timeout=1.5)
        return loaded

    monkeypatch.setattr(queries, "load_requests", load_then_wait)

    async def make(new: NewRequest) -> Created | Refused:
        async with acting(engine, org.tenant.id, org.report) as (db, actor):
            return await service.create(db, actor, new, NOW, via="ui")

    # Each is 6 weekdays, 6 x 480 = 2,880 of the 4,800 available. Together 5,760: too much.
    first = make(pto(date(2026, 11, 2), date(2026, 11, 9)))
    second = make(pto(date(2026, 11, 17), date(2026, 11, 24)))
    return list(await asyncio.gather(first, second))


async def test_two_requests_that_each_fit_but_not_together_cannot_both_succeed(
    app_engine: AsyncEngine, make_tenant: MakeTenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    org = await make_org(app_engine, make_tenant)
    await fund(app_engine, org)

    results = await two_creates_that_each_fit_but_not_together(app_engine, org, monkeypatch)

    made = [r for r in results if isinstance(r, Created)]
    turned_away = [r for r in results if isinstance(r, Refused)]
    assert (len(made), len(turned_away)) == (1, 1)
    assert turned_away[0].code == "not-enough"
    assert len(await requests_of(app_engine, org, org.report)) == 1


async def test_the_lock_is_the_per_person_advisory_lock_and_ends_with_the_transaction(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    org = await make_org(app_engine, make_tenant)
    await fund(app_engine, org)
    held = text(
        "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND classid = :ns AND granted"
    )

    async with acting(app_engine, org.tenant.id, org.report) as (db, actor):
        created(await service.create(db, actor, pto(date(2026, 11, 9)), NOW, via="ui"))
        async with owner_engine.connect() as connection:
            during: int = (await connection.execute(held, {"ns": LOCK_NAMESPACE})).scalar_one()
    async with owner_engine.connect() as connection:
        after: int = (await connection.execute(held, {"ns": LOCK_NAMESPACE})).scalar_one()

    assert (during, after) == (1, 0)


async def one_waiting_at_the_lock(owner_engine: AsyncEngine) -> None:
    """Wait until some session is blocked on a time-off lock."""
    waiting = text(
        "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND classid = :ns"
        " AND NOT granted"
    )
    for _ in range(100):
        async with owner_engine.connect() as connection:
            if (await connection.execute(waiting, {"ns": LOCK_NAMESPACE})).scalar_one():
                return
        await asyncio.sleep(0.05)
    pytest.fail("No session was waiting for the time-off lock")


async def test_a_decision_made_after_a_cancel_sees_the_cancel_and_writes_nothing(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    org = await make_org(app_engine, make_tenant)
    await fund(app_engine, org)
    request_id = await put_request(app_engine, org, org.report, date(2026, 11, 9))

    # The report cancels and holds the lock, uncommitted. The manager's decision starts, finds the
    # request still pending, and waits at the lock. When the cancel commits, the decision re-reads.
    async with acting(app_engine, org.tenant.id, org.report) as (report_db, report):
        canceled = await service.cancel(report_db, report, request_id, NOW, via="ui")
        assert isinstance(canceled, Canceled)

        async def decide() -> Decided | Refused:
            async with acting(app_engine, org.tenant.id, org.manager) as (db, manager):
                return await service.decide(db, manager, request_id, "approve", None, NOW, via="ui")

        deciding = asyncio.create_task(decide())
        await one_waiting_at_the_lock(owner_engine)
        assert not deciding.done()
    result = await deciding

    assert refused(result).code == "status-changed"
    row = await get_request(app_engine, org, request_id)
    assert (row.status, row.decided_by, row.decided_at) == ("canceled", None, None)
    assert [e.action for e in await events(app_engine, org)] == ["timeoff.canceled"]


# ---------------------------------------------------------------------------------------------
# decide


async def decide_as(
    engine: AsyncEngine,
    org: Org,
    person_id: UUID,
    request_id: UUID,
    decision: Any = "approve",
    note: str | None = None,
) -> Decided | Refused:
    async with acting(engine, org.tenant.id, person_id) as (db, actor):
        return await service.decide(db, actor, request_id, decision, note, NOW, via="ui")


async def test_the_direct_manager_approves_and_it_is_audited(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    org = await make_org(app_engine, make_tenant)
    request_id = await put_request(app_engine, org, org.report, date(2026, 11, 9))

    result = await decide_as(app_engine, org, org.manager, request_id)

    assert isinstance(result, Decided)
    row = await get_request(app_engine, org, request_id)
    assert (row.status, row.decided_by, row.decided_at, row.decision_note) == (
        "approved",
        org.manager,
        NOW,
        None,
    )
    (event,) = await events(app_engine, org)
    assert (event.action, event.via, event.actor_person_id) == (
        "timeoff.approved",
        "ui",
        org.manager,
    )
    assert (event.target_type, event.target_id) == ("time_off_request", request_id)
    shape = {"type": "pto", "startDate": "2026-11-09", "endDate": "2026-11-09"}
    assert event.before == {"status": "pending", **shape}
    assert event.after == {"status": "approved", **shape}


async def test_a_denial_keeps_its_note_on_the_request_and_never_in_the_log(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    org = await make_org(app_engine, make_tenant)
    request_id = await put_request(app_engine, org, org.report, date(2026, 11, 9))
    note = "Coverage is thin that week, sorry"

    result = await decide_as(app_engine, org, org.manager, request_id, "deny", note)

    assert isinstance(result, Decided)
    row = await get_request(app_engine, org, request_id)
    assert (row.status, row.decision_note) == ("denied", note)
    (event,) = await events(app_engine, org)
    assert event.action == "timeoff.denied"
    assert event.after is not None
    assert event.after["status"] == "denied"
    assert note not in json.dumps([event.before, event.after])
    assert not {"note", "decisionNote", "decision_note"} & set(event.after)


async def test_a_note_on_an_approval_or_over_300_characters_is_a_programming_error(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    org = await make_org(app_engine, make_tenant)
    request_id = await put_request(app_engine, org, org.report, date(2026, 11, 9))

    with pytest.raises(ValueError, match="note"):
        await decide_as(app_engine, org, org.manager, request_id, "approve", "Enjoy")
    with pytest.raises(ValueError, match="note"):
        await decide_as(app_engine, org, org.manager, request_id, "deny", "x" * 301)
    with pytest.raises(ValueError, match="decision"):
        await decide_as(app_engine, org, org.manager, request_id, "maybe")
    assert (await get_request(app_engine, org, request_id)).status == "pending"
    # Exactly 300 is fine.
    result = await decide_as(app_engine, org, org.manager, request_id, "deny", "x" * 300)
    assert isinstance(result, Decided)


@pytest.mark.parametrize("who", ["hr", "coo", "report"])
async def test_hr_a_skip_level_manager_and_the_person_may_read_but_not_decide(
    app_engine: AsyncEngine, make_tenant: MakeTenant, who: str
) -> None:
    org = await make_org(app_engine, make_tenant)
    request_id = await put_request(app_engine, org, org.report, date(2026, 11, 9))

    result = await decide_as(app_engine, org, getattr(org, who), request_id)

    assert refused(result).code == "not-allowed"
    assert (await get_request(app_engine, org, request_id)).status == "pending"
    assert await events(app_engine, org) == []


async def test_a_sick_record_is_not_decided_by_anyone(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    org = await make_org(app_engine, make_tenant)
    request_id = await put_request(app_engine, org, org.report, date(2026, 10, 19), type="sick")

    result = await decide_as(app_engine, org, org.manager, request_id)

    assert refused(result).code == "not-allowed"
    assert (await get_request(app_engine, org, request_id)).status == "recorded"


async def test_a_request_that_is_no_longer_pending_is_status_changed(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    org = await make_org(app_engine, make_tenant)
    canceled = await put_request(app_engine, org, org.report, date(2026, 11, 9), status="canceled")
    approved = await put_request(app_engine, org, org.report, date(2026, 11, 16), status="approved")

    assert refused(await decide_as(app_engine, org, org.manager, canceled)).code == "status-changed"
    assert (
        refused(await decide_as(app_engine, org, org.manager, approved, "deny")).code
        == "status-changed"
    )
    assert (await get_request(app_engine, org, approved)).status == "approved"


async def test_someone_who_cannot_read_the_request_gets_not_found(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    org = await make_org(app_engine, make_tenant)
    other_tenant = await make_tenant()
    request_id = await put_request(app_engine, org, org.report, date(2026, 11, 9))

    # A peer with no line to the report, a stranger in another tenant, and an ID that doesn't
    # exist all look the same: not found, never "not allowed".
    peer = await decide_as(app_engine, org, org.peer, request_id)
    async with acting(app_engine, other_tenant.id, other_tenant.hr_id) as (db, stranger):
        outsider = await service.decide(db, stranger, request_id, "approve", None, NOW, via="ui")
    missing = await decide_as(app_engine, org, org.manager, uuid4())

    assert [refused(r).code for r in (peer, outsider, missing)] == ["not-found"] * 3
    assert (await get_request(app_engine, org, request_id)).status == "pending"


async def test_a_decision_made_by_the_assistant_audits_its_proposal(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    org = await make_org(app_engine, make_tenant)
    request_id = await put_request(app_engine, org, org.report, date(2026, 11, 9))

    # The proposal belongs to the actor, who is the manager.
    async with acting(app_engine, org.tenant.id, org.manager) as (db, manager):
        proposal_id = await put_proposal(db, org, org.manager)
        result = await service.decide(
            db, manager, request_id, "approve", None, NOW, via="assistant", proposal_id=proposal_id
        )

    assert isinstance(result, Decided)
    (event,) = await events(app_engine, org)
    assert (event.action, event.via, event.proposal_id) == (
        "timeoff.approved",
        "assistant",
        proposal_id,
    )


async def test_a_decision_from_the_ui_cannot_carry_a_proposal(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    org = await make_org(app_engine, make_tenant)
    request_id = await put_request(app_engine, org, org.report, date(2026, 11, 9))

    async with acting(app_engine, org.tenant.id, org.manager) as (db, manager):
        with pytest.raises(ValueError, match="proposal"):
            await service.decide(
                db, manager, request_id, "approve", None, NOW, via="ui", proposal_id=uuid4()
            )
    assert (await get_request(app_engine, org, request_id)).status == "pending"


class NoOffsetZone(tzinfo):
    """A zone that reports no offset, which makes a datetime naive even though it has a tzinfo."""

    def utcoffset(self, dt: datetime | None) -> None:
        return None

    def dst(self, dt: datetime | None) -> None:
        return None

    def tzname(self, dt: datetime | None) -> None:
        return None


@pytest.mark.parametrize(
    "naive",
    [datetime(2026, 10, 21, 18, 0), datetime(2026, 10, 21, 18, 0, tzinfo=NoOffsetZone())],  # noqa: DTZ001
    ids=["no-tzinfo", "no-offset"],
)
async def test_a_decision_needs_a_timezone_aware_now(
    app_engine: AsyncEngine, make_tenant: MakeTenant, naive: datetime
) -> None:
    org = await make_org(app_engine, make_tenant)
    request_id = await put_request(app_engine, org, org.report, date(2026, 11, 9))

    async with acting(app_engine, org.tenant.id, org.manager) as (db, manager):
        with pytest.raises(ValueError, match="timezone-aware"):
            await service.decide(db, manager, request_id, "approve", None, naive, via="ui")
    assert (await get_request(app_engine, org, request_id)).status == "pending"


# ---------------------------------------------------------------------------------------------
# cancel


async def cancel_as(
    engine: AsyncEngine,
    org: Org,
    person_id: UUID,
    request_id: UUID,
    now: datetime = NOW,
) -> Canceled | Refused:
    async with acting(engine, org.tenant.id, person_id) as (db, actor):
        return await service.cancel(db, actor, request_id, now, via="ui")


async def test_a_pending_request_can_be_canceled_at_any_time_and_it_is_audited(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    org = await make_org(app_engine, make_tenant)
    # Pending, and already past its first day: a pending request is canceled whenever.
    request_id = await put_request(app_engine, org, org.report, date(2026, 10, 19))

    result = await cancel_as(app_engine, org, org.report, request_id)

    assert isinstance(result, Canceled)
    row = await get_request(app_engine, org, request_id)
    assert (row.status, row.canceled_at) == ("canceled", NOW)
    (event,) = await events(app_engine, org)
    assert (event.action, event.actor_person_id) == ("timeoff.canceled", org.report)
    shape = {"type": "pto", "startDate": "2026-10-19", "endDate": "2026-10-19"}
    assert (event.before, event.after) == (
        {"status": "pending", **shape},
        {"status": "canceled", **shape},
    )


@pytest.mark.parametrize(("type_", "status"), [("pto", "approved"), ("sick", "recorded")])
@pytest.mark.parametrize(
    ("first_day", "outcome"),
    [
        (date(2026, 10, 22), "canceled"),  # the day before its first day: yes
        (date(2026, 10, 21), "already-started"),  # on its first day: no
        (date(2026, 10, 20), "already-started"),
    ],
)
async def test_an_approved_or_recorded_request_cancels_only_before_its_first_day(
    app_engine: AsyncEngine,
    make_tenant: MakeTenant,
    type_: str,
    status: str,
    first_day: date,
    outcome: str,
) -> None:
    org = await make_org(app_engine, make_tenant)
    request_id = await put_request(
        app_engine, org, org.report, first_day, type=type_, status=status
    )

    result = await cancel_as(app_engine, org, org.report, request_id)

    row = await get_request(app_engine, org, request_id)
    if outcome == "canceled":
        assert isinstance(result, Canceled)
        assert row.status == "canceled"
    else:
        assert refused(result).code == outcome
        assert row.status == status
        assert await events(app_engine, org) == []


async def test_cancel_uses_the_persons_own_today(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    org = await make_org(app_engine, make_tenant)
    # At 03:00 UTC on the 21st it is still the evening of the 20th in Oakland, so a request that
    # starts on the 21st starts tomorrow there, and can still be canceled.
    request_id = await put_request(
        app_engine, org, org.oakland, date(2026, 10, 21), status="approved"
    )

    result = await cancel_as(app_engine, org, org.oakland, request_id, LATE_EVENING_UTC)

    assert isinstance(result, Canceled)


async def test_a_denied_or_canceled_request_cannot_be_canceled(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    org = await make_org(app_engine, make_tenant)
    denied = await put_request(app_engine, org, org.report, date(2026, 11, 9), status="denied")
    canceled = await put_request(app_engine, org, org.report, date(2026, 11, 16), status="canceled")

    assert refused(await cancel_as(app_engine, org, org.report, denied)).code == "status-changed"
    assert refused(await cancel_as(app_engine, org, org.report, canceled)).code == "status-changed"


async def test_only_the_person_cancels_and_others_may_or_may_not_see_it(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    org = await make_org(app_engine, make_tenant)
    request_id = await put_request(app_engine, org, org.report, date(2026, 11, 9))

    by_manager = await cancel_as(app_engine, org, org.manager, request_id)
    by_hr = await cancel_as(app_engine, org, org.hr, request_id)
    by_peer = await cancel_as(app_engine, org, org.peer, request_id)
    by_nobody = await cancel_as(app_engine, org, org.report, uuid4())

    assert [refused(r).code for r in (by_manager, by_hr, by_peer, by_nobody)] == [
        "not-allowed",
        "not-allowed",
        "not-found",
        "not-found",
    ]
    assert (await get_request(app_engine, org, request_id)).status == "pending"


async def test_a_cancel_made_by_the_assistant_audits_its_proposal(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    org = await make_org(app_engine, make_tenant)
    request_id = await put_request(app_engine, org, org.report, date(2026, 11, 9))

    # The proposal belongs to the actor, who is the person canceling their own request.
    async with acting(app_engine, org.tenant.id, org.report) as (db, report):
        proposal_id = await put_proposal(db, org, org.report)
        result = await service.cancel(
            db, report, request_id, NOW, via="assistant", proposal_id=proposal_id
        )

    assert isinstance(result, Canceled)
    (event,) = await events(app_engine, org)
    assert (event.action, event.via, event.proposal_id) == (
        "timeoff.canceled",
        "assistant",
        proposal_id,
    )


async def test_a_cancel_from_the_ui_cannot_carry_a_proposal(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    org = await make_org(app_engine, make_tenant)
    request_id = await put_request(app_engine, org, org.report, date(2026, 11, 9))

    async with acting(app_engine, org.tenant.id, org.report) as (db, report):
        with pytest.raises(ValueError, match="proposal"):
            await service.cancel(db, report, request_id, NOW, via="ui", proposal_id=uuid4())
    assert (await get_request(app_engine, org, request_id)).status == "pending"


# ---------------------------------------------------------------------------------------------
# the exclusion constraint


async def test_the_exclusion_constraint_becomes_overlaps_and_the_transaction_survives(
    app_engine: AsyncEngine, make_tenant: MakeTenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    org = await make_org(app_engine, make_tenant)
    await fund(app_engine, org)
    real_load_requests = queries.load_requests

    async def load_then_let_a_rival_in(*args: Any, **kwargs: Any) -> Any:
        # The engine reads the person's requests, and then, before the insert, another request for
        # the same days is committed by another transaction (one that took no lock, as a path that
        # bypassed the service would). The engine's overlap check never saw it.
        loaded = await real_load_requests(*args, **kwargs)
        await put_request(app_engine, org, org.report, date(2026, 11, 9), date(2026, 11, 10))
        return loaded

    monkeypatch.setattr(queries, "load_requests", load_then_let_a_rival_in)

    async with acting(app_engine, org.tenant.id, org.report) as (db, actor):
        result = await service.create(
            db, actor, pto(date(2026, 11, 10), date(2026, 11, 11)), NOW, via="ui"
        )
        # The caller's transaction is still usable: it can read, and write an audit event.
        still_usable: int = (await db.execute(text("SELECT 1"))).scalar_one()
        monkeypatch.setattr(queries, "load_requests", real_load_requests)
        later = await service.create(db, actor, pto(date(2026, 11, 16)), NOW, via="ui")

    assert refused(result).code == "overlaps"
    assert still_usable == 1
    assert isinstance(later, Created)
    assert len(await requests_of(app_engine, org, org.report)) == 2
    assert [e.action for e in await events(app_engine, org)] == ["timeoff.requested"]


# ---------------------------------------------------------------------------------------------
# balances


async def test_a_manager_reads_a_reports_balances_and_they_match_the_hand_worked_figure(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    org = await make_org(app_engine, make_tenant)
    # The report is salaried and works Monday to Friday in Denver. Today is 2026-10-21.
    # Opening: 3,000 minutes as of 2026-01-01.
    await put_opening(app_engine, org, org.report, date(2026, 1, 1), 3000)
    # Earned: the last day of January through September is nine month-ends, 9 x 600 = 5,400, so
    # 3,000 + 5,400 = 8,400. The most the balance ever reaches (before any PTO) is 8,400, well
    # under the 10,800 ceiling, so no month is cut short.
    # Taken: approved Monday to Wednesday, March 2 to 4: 3 x 480 = 1,440.
    await put_request(
        app_engine, org, org.report, date(2026, 3, 2), date(2026, 3, 4),
        status="approved", amount_minutes=1440,
    )  # fmt: skip
    # Booked: approved Friday, October 23, after today: 480.
    await put_request(app_engine, org, org.report, date(2026, 10, 23), status="approved")
    # Pending: Monday and Tuesday, November 2 and 3: 2 x 480 = 960.
    await put_request(
        app_engine, org, org.report, date(2026, 11, 2), date(2026, 11, 3), amount_minutes=960
    )
    # Available: 8,400 - 1,440 - 480 - 960 = 5,520. The next earning is the October month-end,
    # 600 minutes on 2026-10-31.

    async with acting(app_engine, org.tenant.id, org.manager) as (db, manager):
        result = await service.balances(db, manager, org.report, NOW)

    assert isinstance(result, Balances)
    assert result.today == TODAY
    pto_balance = result.pto
    assert (
        pto_balance.earned_minutes,
        pto_balance.taken_minutes,
        pto_balance.booked_minutes,
        pto_balance.pending_minutes,
        pto_balance.available_minutes,
        pto_balance.ceiling_minutes,
    ) == (8400, 1440, 480, 960, 5520, 10800)
    assert (pto_balance.next_earning, pto_balance.next_earning_minutes) == (date(2026, 10, 31), 600)
    # Sick leave: Colorado grants 48 hours, 2,880 minutes, and none is used.
    assert [(y.year, y.granted_minutes, y.available_minutes) for y in result.sick] == [
        (2026, 2880, 2880)
    ]
    assert {r.section_id for r in result.rules} >= {"4.1", "CO-4.3"}
    assert all(r.deep_link == f"/handbook/{r.section_id}" and r.title for r in result.rules)


async def test_people_read_their_own_and_hr_reads_anyones(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    org = await make_org(app_engine, make_tenant)
    await fund(app_engine, org)

    async with acting(app_engine, org.tenant.id, org.report) as (db, actor):
        mine = await service.balances(db, actor, org.report, NOW)
    async with acting(app_engine, org.tenant.id, org.hr) as (db, hr):
        hrs = await service.balances(db, hr, org.report, NOW)
    async with acting(app_engine, org.tenant.id, org.coo) as (db, coo):
        skip = await service.balances(db, coo, org.report, NOW)

    assert isinstance(mine, Balances)
    assert mine == hrs == skip
    assert mine.pto.available_minutes == 4800


async def test_balances_for_someone_the_actor_cannot_read_is_not_found(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    org = await make_org(app_engine, make_tenant)
    other_tenant = await make_tenant()

    async with acting(app_engine, org.tenant.id, org.peer) as (db, peer):
        by_peer = await service.balances(db, peer, org.report, NOW)
        unknown = await service.balances(db, peer, uuid4(), NOW)
    async with acting(app_engine, org.tenant.id, org.hr) as (db, hr):
        hr_unknown = await service.balances(db, hr, uuid4(), NOW)
        hr_other_tenant = await service.balances(db, hr, other_tenant.employee_id, NOW)

    assert [refused(r).code for r in (by_peer, unknown, hr_unknown, hr_other_tenant)] == [
        "not-found"
    ] * 4


async def test_a_holiday_in_a_past_year_is_skipped_in_what_was_taken(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    org = await make_org(app_engine, make_tenant)
    await put_opening(app_engine, org, org.report, date(2025, 1, 1), 0)
    await put_holiday(
        app_engine, org, await location_of(app_engine, org, org.report),
        date(2025, 12, 25), "Christmas Day",
    )  # fmt: skip
    # Approved Monday 2025-12-22 to Friday 2025-12-26. Thursday the 25th is a holiday, so four
    # days count, 4 x 480 = 1,920 taken. (Five days would be 2,400.) The stored amount is
    # deliberately not the answer: the engine counts again from the dates and the holidays.
    await put_request(
        app_engine, org, org.report, date(2025, 12, 22), date(2025, 12, 26),
        status="approved", amount_minutes=2400,
    )  # fmt: skip

    async with acting(app_engine, org.tenant.id, org.report) as (db, actor):
        result = await service.balances(db, actor, org.report, NOW)

    assert isinstance(result, Balances)
    assert result.pto.taken_minutes == 1920


async def test_a_request_across_new_year_skips_a_holiday_in_the_next_year(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    org = await make_org(app_engine, make_tenant)
    await fund(app_engine, org)
    await put_holiday(
        app_engine, org, await location_of(app_engine, org, org.report),
        date(2027, 1, 1), "New Year's Day",
    )  # fmt: skip

    async with acting(app_engine, org.tenant.id, org.report) as (db, actor):
        # Wednesday 2026-12-30 to Monday 2027-01-04. Today is in 2026, the holiday in 2027.
        # Counted: Wed 30, Thu 31, Mon 4 = 3 x 480 = 1,440. Skipped: Fri Jan 1 (the holiday), and
        # the weekend of Jan 2 and 3 (not scheduled).
        result = created(
            await service.create(
                db, actor, pto(date(2026, 12, 30), date(2027, 1, 4)), NOW, via="ui"
            )
        )

    assert result.evaluation.amount_minutes == 1440
    assert (date(2027, 1, 1), "New Year's Day") in [
        (skipped.day, skipped.reason) for skipped in result.evaluation.skipped
    ]
    assert (await get_request(app_engine, org, result.request_id)).amount_minutes == 1440


async def test_another_locations_holiday_does_not_apply(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    org = await make_org(app_engine, make_tenant)
    await fund(app_engine, org)
    # Oakland's holiday falls on Wednesday 2026-11-11; the report works in Denver.
    await put_holiday(
        app_engine, org, await location_of(app_engine, org, org.oakland),
        date(2026, 11, 11), "Oakland Day",
    )  # fmt: skip

    async with acting(app_engine, org.tenant.id, org.report) as (db, actor):
        # Monday to Wednesday, November 9 to 11: three Denver workdays, 3 x 480 = 1,440.
        evaluation = await service.check(db, actor, pto(date(2026, 11, 9), date(2026, 11, 11)), NOW)

    assert evaluation.amount_minutes == 1440
    assert evaluation.skipped == ()


# ---------------------------------------------------------------------------------------------
# today


async def test_today_is_the_persons_location_not_utc(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    org = await make_org(app_engine, make_tenant)
    await put_opening(app_engine, org, org.oakland, date(2026, 1, 1), 4800)

    async with acting(app_engine, org.tenant.id, org.oakland) as (db, actor):
        # At 03:00 UTC on the 21st it is 8 pm on Tuesday the 20th in Oakland. PTO starting on the
        # 20th starts today there. One starting on Monday the 19th started yesterday.
        starts_today = await service.check(db, actor, pto(date(2026, 10, 20)), LATE_EVENING_UTC)
        yesterday = await service.check(db, actor, pto(date(2026, 10, 19)), LATE_EVENING_UTC)
        balance = await service.balances(db, actor, org.oakland, LATE_EVENING_UTC)

    assert "out-of-range" not in starts_today.problems
    assert yesterday.problems == ("out-of-range",)
    assert isinstance(balance, Balances)
    assert balance.today == OAKLAND_TODAY


async def test_a_managers_view_of_a_report_uses_the_reports_today(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    org = await make_org(app_engine, make_tenant)
    await put_opening(app_engine, org, org.oakland, date(2026, 1, 1), 4800)

    async with acting(app_engine, org.tenant.id, org.manager) as (db, manager):
        result = await service.balances(db, manager, org.oakland, LATE_EVENING_UTC)

    assert isinstance(result, Balances)
    assert result.today == OAKLAND_TODAY


# ---------------------------------------------------------------------------------------------
# the rules and the handbook


async def pinned_version(engine: AsyncEngine, tenant_id: UUID) -> UUID:
    async with tenant_session(engine, TenantContext(tenant_id, None)) as session:
        version_id = (
            await session.execute(select(Tenant.handbook_version_id).where(Tenant.id == tenant_id))
        ).scalar_one()
    assert version_id is not None
    return version_id


async def test_every_rule_the_engine_can_cite_resolves_in_the_pinned_handbook(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    version_id = await pinned_version(app_engine, tenant.id)
    states = cast(tuple[State, ...], STATES)
    every_rule: list[Rule] = [*RULES.values(), *(sick_grant_rule(state) for state in states)]

    async with tenant_session(app_engine, TenantContext(tenant.id, None)) as db:
        refs = await service.resolve_rules(db, every_rule, version_id)

    assert [(r.section_id, r.rule) for r in refs] == [
        (r.section_id, r.rule) for r in dict.fromkeys(every_rule)
    ]
    assert all(isinstance(r, RuleRef) and r.title for r in refs)
    by_rule = {r.rule: r for r in refs}
    assert by_rule["pto-earning"].title == "Paid time off"
    assert by_rule["pto-earning"].deep_link == "/handbook/4.1"
    assert by_rule["sick-grant"].section_id in {"4.3", "CA-4.3", "CO-4.3"}
    # The four states give three sections, and a state's section is its own addendum.
    assert {sick_grant_rule(state).section_id for state in states} == {"4.3", "CA-4.3", "CO-4.3"}


async def test_a_rule_that_names_a_section_the_version_lacks_raises(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    version_id = await pinned_version(app_engine, tenant.id)

    async with tenant_session(app_engine, TenantContext(tenant.id, None)) as db:
        with pytest.raises(LookupError, match=r"9\.9"):
            await service.resolve_rules(
                db, [Rule("4.1", "pto-earning"), Rule("9.9", "x")], version_id
            )


# ---------------------------------------------------------------------------------------------
# what the service loads


async def test_stored_requests_are_loaded_as_engine_requests(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    org = await make_org(app_engine, make_tenant)
    await put_request(app_engine, org, org.report, date(2026, 11, 9))
    await put_request(app_engine, org, org.report, date(2026, 11, 12), status="canceled")
    await put_request(app_engine, org, org.peer, date(2026, 11, 9))

    async with acting(app_engine, org.tenant.id, org.report) as (db, _):
        loaded = await queries.load_requests(db, org.tenant.id, org.report)

    # Every status of this person's, and nobody else's.
    assert sorted((r.type, r.status, r.start, r.end) for r in loaded) == [
        ("pto", "canceled", date(2026, 11, 12), date(2026, 11, 12)),
        ("pto", "pending", date(2026, 11, 9), date(2026, 11, 9)),
    ]


async def test_the_person_the_engine_sees_comes_from_their_row_and_location(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    org = await make_org(app_engine, make_tenant)
    await put_opening(app_engine, org, org.oakland, date(2026, 1, 1), 1200)

    async with acting(app_engine, org.tenant.id, org.oakland) as (db, _):
        facts = await queries.load_facts(db, org.tenant.id, org.oakland)
        nobody = await queries.load_facts(db, org.tenant.id, uuid4())

    assert nobody is None
    assert facts is not None
    assert (facts.person.state, facts.person.employment_type) == ("CA", "salaried")
    assert (facts.person.hire_date, sorted(facts.person.schedule.weekdays)) == (
        date(2024, 3, 4),
        [1, 2, 3, 4, 5],
    )
    assert (facts.opening.as_of, facts.opening.amount_minutes) == (date(2026, 1, 1), 1200)
    assert facts.timezone == "America/Los_Angeles"
    # The Oakland store has no holidays in this small company; Denver's New Year's Day isn't its.
    assert facts.holidays == {}


async def test_a_missing_opening_is_zero_from_the_anchor_date(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    org = await make_org(app_engine, make_tenant)

    async with acting(app_engine, org.tenant.id, org.report) as (db, _):
        facts = await queries.load_facts(db, org.tenant.id, org.report)
        anchor = (await db.execute(select(Tenant.anchor_date))).scalar_one()

    assert facts is not None
    assert (facts.opening.as_of, facts.opening.amount_minutes) == (anchor, 0)


async def test_a_stored_request_is_loaded_only_for_the_tenant_asked_for(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    org = await make_org(app_engine, make_tenant)
    request_id = await put_request(app_engine, org, org.report, date(2026, 11, 9))

    # Row-level security already limits the session to its tenant. The query names the tenant too,
    # so a wrong one finds nothing even in the right session.
    async with acting(app_engine, org.tenant.id, org.manager) as (db, _):
        mine = await queries.load_stored_request(db, org.tenant.id, request_id)
        other = await queries.load_stored_request(db, uuid4(), request_id)

    assert mine is not None
    assert (mine.person_id, mine.status) == (org.report, "pending")
    assert other is None
