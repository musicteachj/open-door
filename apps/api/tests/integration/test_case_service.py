"""The case service, as the API's login runs it against real Postgres.

Priya's sandbox from `make_tenant` is the stage: Leo is an employee who opens cases, Rae reports to
Leo (so Leo is the manager of the person whose case is probed), Dana and Hana are HR, and Priya
already has one case. The guard is the scripted one, which answers from the words: "hurt myself"
is a crisis, "harass" is sensitive, "scripted guard failure" is no answer.

Dates are hand-worked where they matter. The service takes "now" from the database, so the tests
that need a fixed day seed rows or call the reply-by helper with a chosen instant.
"""

import asyncio
import base64
import contextlib
import json
import logging
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass, fields
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import event, insert, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.ai.budget import Caps
from app.ai.fixed_texts import CRISIS_TEXT
from app.ai.guard import CaseGuard
from app.ai.scripted import ScriptedTransport
from app.ai.transport import GuardRequest, GuardResult
from app.core.encryption import (
    TEST_KEY_ID,
    Place,
    new_data_key,
    seal,
    wrap_aad,
)
from app.core.problems import ProblemError
from app.db.locks import CASE_PERSON_NS, database_now
from app.db.models import (
    AiSpend,
    AuditEvent,
    Case,
    CaseEvent,
    CaseSummary,
    Holiday,
    Location,
    Person,
)
from app.db.tenancy import TenantContext, set_is_hr, tenant_session
from app.modules.cases import queries, service, texts
from app.modules.cases.schemas import (
    CaseOpened,
    OpenCase,
    QueueItem,
    SummaryFailed,
    SummaryWritten,
)
from app.modules.identity.actor import load_actor
from app.policy import Actor
from tests.integration.conftest import (
    OPAQUE,
    TEST_KEYS,
    MakeTenant,
    SampleTenant,
    audit_events,
    turn_row,
    write_assistant_rows,
)

pytestmark = pytest.mark.integration

WORDS = "My team lead keeps changing my schedule without telling me."
CANARY = "CANARY-zx81-lantern"
BIG_CAPS = Caps(sandbox_usd=Decimal(1000), daily_usd=Decimal(1000))


class WatchedTransport(ScriptedTransport):
    """The scripted guard, counting what it is asked."""

    def __init__(self) -> None:
        super().__init__()
        self.requests: list[GuardRequest] = []

    async def classify(self, request: GuardRequest) -> GuardResult:
        self.requests.append(request)
        return await super().classify(request)


class WatchedKeys:
    """The test keyring, counting how often a data key is unwrapped (so a refusal that comes
    before the decrypt shows as zero)."""

    def __init__(self) -> None:
        self.unwraps = 0

    def wrap(self, data_key: bytes, *, aad: bytes) -> tuple[str, bytes]:
        return TEST_KEYS.wrap(data_key, aad=aad)

    def unwrap(self, key_id: str, wrapped: bytes, *, aad: bytes) -> bytes:
        self.unwraps += 1
        return TEST_KEYS.unwrap(key_id, wrapped, aad=aad)


@dataclass
class Env:
    engine: AsyncEngine
    tenant: SampleTenant
    transport: WatchedTransport
    keys: WatchedKeys
    rae: UUID
    hana: UUID

    @property
    def leo(self) -> UUID:
        return self.tenant.colleague_id

    @property
    def priya(self) -> UUID:
        return self.tenant.employee_id

    @property
    def dana(self) -> UUID:
        return self.tenant.hr_id

    def guard(self, caps: Caps = BIG_CAPS) -> CaseGuard:
        return CaseGuard(self.transport, self.engine, caps)


@asynccontextmanager
async def acting(
    engine: AsyncEngine, tenant_id: UUID, person_id: UUID
) -> AsyncIterator[tuple[AsyncSession, Actor]]:
    """One transaction as `person_id`, set up as the session dependency sets it up."""
    async with tenant_session(engine, TenantContext(tenant_id, person_id)) as db:
        actor = await load_actor(db, tenant_id, person_id)
        assert actor is not None
        await set_is_hr(db, actor.is_hr_admin)
        yield db, actor


@pytest.fixture
async def env(app_engine: AsyncEngine, make_tenant: MakeTenant) -> Env:
    tenant = await make_tenant()
    rae, hana = uuid4(), uuid4()
    async with tenant_session(app_engine, TenantContext(tenant.id, None)) as session:
        template = (
            await session.execute(
                select(Person.department_id, Person.location_id).where(
                    Person.id == tenant.colleague_id
                )
            )
        ).one()
        for person_id, given, manager_id, is_hr in (
            (rae, "Rae", tenant.colleague_id, False),
            (hana, "Hana", None, True),
        ):
            await session.execute(
                insert(Person).values(
                    id=person_id,
                    tenant_id=tenant.id,
                    given_name=given,
                    family_name="Test",
                    title="Associate",
                    department_id=template.department_id,
                    location_id=template.location_id,
                    manager_id=manager_id,
                    work_email=f"{given.lower()}@juniperrow.example",
                    employment_type="salaried",
                    hire_date=date(2024, 3, 4),
                    is_hr_admin=is_hr,
                )
            )
    return Env(app_engine, tenant, WatchedTransport(), WatchedKeys(), rae, hana)


async def send(
    env: Env,
    who: UUID,
    text_: str = WORDS,
    *,
    submission_id: UUID | None = None,
    turn_id: UUID | None = None,
    category: str = "pay",
    guard: CaseGuard | None = None,
) -> CaseOpened:
    # No session is open during the call: the service opens its own, as a route that took the
    # actor from `signed_in_caller` would.
    async with acting(env.engine, env.tenant.id, who) as (_, actor):
        pass
    return await service.open_case(
        env.engine,
        env.keys,
        guard or env.guard(),
        actor,
        OpenCase(submission_id or uuid4(), category, text_, turn_id),
    )


async def problem(coro: Any) -> ProblemError:
    with pytest.raises(ProblemError) as caught:
        await coro
    return caught.value


async def hr_query(env: Env, query: Any) -> list[Any]:
    """A read as Dana with the HR flag, for looking at rows the person cannot see."""
    async with acting(env.engine, env.tenant.id, env.dana) as (db, _):
        return list((await db.execute(query)).all())


async def case_rows(env: Env, person_id: UUID) -> list[Case]:
    async with acting(env.engine, env.tenant.id, env.dana) as (db, _):
        return list(await db.scalars(select(Case).where(Case.person_id == person_id)))


async def events_of(env: Env, case_id: UUID) -> list[CaseEvent]:
    async with acting(env.engine, env.tenant.id, env.dana) as (db, _):
        return list(
            await db.scalars(
                select(CaseEvent)
                .where(CaseEvent.case_id == case_id)
                .order_by(CaseEvent.occurred_at, CaseEvent.id)
            )
        )


async def audit_of(env: Env, action: str) -> list[AuditEvent]:
    return [e for e in await audit_events(env.engine, env.tenant.id) if e.action == action]


async def case_spend(env: Env) -> list[Any]:
    """The sandbox's ledger rows that are not a turn's (the sample tenant has one turn row)."""
    return await hr_query(
        env,
        select(AiSpend.purpose, AiSpend.turn_id, AiSpend.kind).where(AiSpend.purpose != "turn"),
    )


async def seed_case(
    env: Env,
    person_id: UUID,
    *,
    status: str = "new",
    reply_by: date | None = None,
    created_at: datetime | None = None,
    screening: str = "ordinary",
    words: str | None = None,
    category: str = "pay",
) -> UUID:
    """A case written with no person set, as the sandbox seed writes them: it may backdate and set
    any status. With `words` the case holds them sealed, so a test can read them back."""
    case_id = uuid4()
    tenant_id = env.tenant.id
    key_id, wrapped, ciphertext = TEST_KEY_ID, OPAQUE, OPAQUE
    if words is not None:
        data_key = new_data_key()
        key_id, wrapped = TEST_KEYS.wrap(data_key, aad=wrap_aad(tenant_id, "cases", case_id))
        ciphertext = seal(
            data_key, words.encode(), place=Place("cases", "text_ciphertext", tenant_id, case_id)
        )
    created = created_at or datetime.now(UTC)
    async with tenant_session(env.engine, TenantContext(tenant_id, None)) as session:
        await session.execute(
            insert(Case).values(
                id=case_id,
                tenant_id=tenant_id,
                person_id=person_id,
                submission_id=uuid4(),
                category=category,
                status=status,
                status_changed_at=created,
                created_at=created,
                reply_by=reply_by or (created.date() + timedelta(days=2)),
                screening=screening,
                key_id=key_id,
                wrapped_key=wrapped,
                text_ciphertext=ciphertext,
            )
        )
    return case_id


async def flagged_turn(
    env: Env, person_id: UUID, category: str | None, *, status: str = "completed"
) -> UUID:
    """A turn of the person's with the given guard category (None for no verdict)."""
    verdict = None if category is None else {"category": category, "kind": None}
    turn_id = uuid4()
    async with tenant_session(env.engine, TenantContext(env.tenant.id, person_id)) as db:
        rows = await write_assistant_rows(db, env.tenant.id, person_id)
        db.add(
            await turn_row(
                db,
                rows.conversation_id,
                turn_id,
                "Something happened at work.",
                status=status,
                guard_verdict=verdict,
            )
        )
    return turn_id


# --- opening a case ---


async def test_open_case_screens_stores_and_audits_in_one_transaction(env: Env) -> None:
    opened = await send(env, env.leo)

    assert (opened.created, opened.screening, opened.crisis_text) == (True, "ordinary", None)
    assert opened.summary_due is True
    # The guard saw the words as the new message, with no previous answer.
    [request] = env.transport.requests
    content = request.messages[0]["content"]
    assert WORDS in content
    assert "previous_answer" not in content
    [row] = await case_rows(env, env.leo)
    assert row.id == opened.case.id
    assert (row.status, row.category, row.screening) == ("new", "pay", "ordinary")
    # Sealed under the case's own key, bound to its place: nothing readable at rest.
    assert WORDS.encode() not in row.text_ciphertext
    # The reply-by date is Denver's, from the instant the database stamped on the case.
    async with acting(env.engine, env.tenant.id, env.leo) as (db, _):
        assert opened.case.reply_by == await queries.reply_by_at(db, env.tenant.id, row.created_at)
    assert opened.case.sent_at == row.created_at
    assert opened.case.reply_by > row.created_at.astimezone(UTC).date()
    [event] = await events_of(env, row.id)
    assert (event.kind, event.actor_person_id) == ("opened", env.leo)
    [audit] = await audit_of(env, "case.opened")
    assert (audit.target_type, audit.target_id, audit.actor_person_id) == ("case", row.id, env.leo)
    assert audit.via == "ui"
    assert audit.after == {"screening": "ordinary", "category": "pay"}
    # The screening was paid for with no turn and no case ID.
    spend = await case_spend(env)
    assert {(r.purpose, r.turn_id) for r in spend} == {("case_screen", None)}
    assert {r.kind for r in spend} == {"reserve", "settle"}


async def test_the_personal_data_check_comes_before_screening_or_storing(env: Env) -> None:
    for words in ("My SSN is 123-45-6789 please fix my pay.", "Card 4242 4242 4242 4242"):
        refused = await problem(send(env, env.leo, words))
        assert (refused.status_code, refused.code) == (422, "case-personal-data")
        assert "4242" not in refused.detail
        assert "123-45" not in refused.detail

    assert env.transport.requests == []
    assert await case_rows(env, env.leo) == []
    assert await case_spend(env) == []
    assert await audit_of(env, "case.opened") == []


async def test_the_guard_is_called_with_no_connection_or_lock_held(
    env: Env, owner_engine: AsyncEngine
) -> None:
    held: dict[str, Any] = {}

    class Looking(WatchedTransport):
        async def classify(self, request: GuardRequest) -> GuardResult:
            held["checked_out"] = env.engine.pool.checkedout()  # type: ignore[attr-defined]
            async with owner_engine.connect() as connection:
                held["locks"] = (
                    await connection.execute(
                        text(
                            "SELECT count(*) FROM pg_locks"
                            " WHERE locktype = 'advisory' AND classid = :ns AND granted"
                        ),
                        {"ns": CASE_PERSON_NS},
                    )
                ).scalar_one()
            return await super().classify(request)

    env.transport = Looking()
    opened = await send(env, env.leo)

    assert opened.created is True
    assert held == {"checked_out": 0, "locks": 0}
    assert len(await case_rows(env, env.leo)) == 1


async def test_hr_opens_a_case_like_anyone_with_no_hr_flag_needed(env: Env) -> None:
    opened = await send(env, env.dana)

    assert opened.created is True
    [row] = await case_rows(env, env.dana)
    assert row.person_id == env.dana


async def test_a_refused_request_is_never_screened(env: Env) -> None:
    for _ in range(5):
        await send(env, env.leo)
    asked = len(env.transport.requests)
    spent = len(await case_spend(env))
    unflagged = await flagged_turn(env, env.rae, "ordinary")

    waiting = await problem(send(env, env.leo))
    turn = await problem(send(env, env.rae, turn_id=unflagged))
    submission = uuid4()
    await send(env, env.rae, submission_id=submission)
    asked_then = len(env.transport.requests)
    repeat = await send(env, env.rae, submission_id=submission)

    assert (waiting.code, turn.code) == ("case-waiting-limit", "case-turn-not-found")
    assert asked_then == asked + 1
    assert len(env.transport.requests) == asked_then
    assert repeat.created is False
    assert len(await case_spend(env)) == spent + 2  # only Rae's one real screening


async def test_a_crisis_verdict_saves_the_case_and_returns_the_crisis_text(env: Env) -> None:
    opened = await send(env, env.leo, "I want to hurt myself and nobody listens.")

    assert opened.screening == "crisis"
    assert opened.crisis_text == CRISIS_TEXT
    assert opened.summary_due is False
    [row] = await case_rows(env, env.leo)
    assert row.screening == "crisis"
    [audit] = await audit_of(env, "case.opened")
    assert audit.after == {"screening": "crisis", "category": "pay"}


async def test_a_sensitive_verdict_is_labeled_and_still_gets_a_summary(env: Env) -> None:
    opened = await send(env, env.leo, "A coworker will harass me again at the next shift.")

    assert (opened.screening, opened.summary_due, opened.crisis_text) == ("sensitive", True, None)


async def test_a_guard_failure_saves_the_case_unscreened(env: Env) -> None:
    opened = await send(env, env.leo, "scripted guard failure: my pay is wrong")

    assert (opened.screening, opened.summary_due, opened.crisis_text) == ("unscreened", False, None)
    [row] = await case_rows(env, env.leo)
    assert row.screening == "unscreened"


async def test_no_budget_saves_the_case_unscreened_and_asks_nothing(env: Env) -> None:
    empty = Caps(sandbox_usd=Decimal("0.0000001"), daily_usd=Decimal(1000))

    opened = await send(env, env.leo, guard=env.guard(empty))

    assert opened.screening == "unscreened"
    assert env.transport.requests == []
    assert (await case_rows(env, env.leo))[0].screening == "unscreened"
    assert await case_spend(env) == []


async def test_a_guard_that_raises_saves_the_case_unscreened(env: Env) -> None:
    class Broken(WatchedTransport):
        async def classify(self, request: GuardRequest) -> GuardResult:
            raise RuntimeError(f"boom {CANARY}")

    env.transport = Broken()

    assert (await send(env, env.leo)).screening == "unscreened"


# --- the same send twice, and the limits ---


async def test_the_same_submission_twice_is_one_case(env: Env) -> None:
    submission = uuid4()
    first = await send(env, env.leo, submission_id=submission)
    second = await send(env, env.leo, submission_id=submission)

    assert second.case.id == first.case.id
    assert (first.created, second.created, second.summary_due) == (True, False, False)
    assert len(await case_rows(env, env.leo)) == 1
    assert len(env.transport.requests) == 1
    assert len(await audit_of(env, "case.opened")) == 1


async def test_a_repeated_crisis_send_shows_the_same_sent_state(env: Env) -> None:
    submission = uuid4()
    words = "I want to hurt myself."
    await send(env, env.leo, words, submission_id=submission)

    again = await send(env, env.leo, words, submission_id=submission)

    assert (again.created, again.crisis_text) == (False, CRISIS_TEXT)


async def test_the_same_submission_with_different_words_is_a_conflict(env: Env) -> None:
    submission = uuid4()
    await send(env, env.leo, submission_id=submission)

    refused = await problem(send(env, env.leo, WORDS + " Again.", submission_id=submission))

    assert (refused.status_code, refused.code) == (409, "case-submission-conflict")
    assert len(await case_rows(env, env.leo)) == 1


async def test_the_same_submission_for_a_different_turn_is_a_conflict(env: Env) -> None:
    first_turn = await flagged_turn(env, env.leo, "sensitive")
    other_turn = await flagged_turn(env, env.leo, "sensitive")
    submission = uuid4()
    await send(env, env.leo, turn_id=first_turn, submission_id=submission)

    for turn in (other_turn, None):
        refused = await problem(send(env, env.leo, turn_id=turn, submission_id=submission))
        assert (refused.status_code, refused.code) == (409, "case-submission-conflict")
    # And a case sent from "My cases" repeated with a turn.
    plain = uuid4()
    await send(env, env.leo, submission_id=plain)
    refused = await problem(send(env, env.leo, turn_id=other_turn, submission_id=plain))
    assert refused.code == "case-submission-conflict"
    assert len(await case_rows(env, env.leo)) == 2


async def test_a_second_tab_for_the_same_turn_gets_the_same_case(env: Env) -> None:
    turn = await flagged_turn(env, env.leo, "sensitive")
    first = await send(env, env.leo, turn_id=turn)

    second = await send(env, env.leo, turn_id=turn, submission_id=uuid4())

    assert (second.case.id, second.created) == (first.case.id, False)
    assert len(await case_rows(env, env.leo)) == 1
    different = await problem(send(env, env.leo, WORDS + "!", turn_id=turn))
    assert different.code == "case-submission-conflict"


async def both_have_read_the_count(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make each send wait, after it counts the waiting cases, for the other to have counted too.
    Without the person's lock both would have counted before either wrote; with it the second send
    waits at the lock, so the first one's wait times out, it writes, and only then does the second
    count."""
    reads = 0
    both = asyncio.Event()
    real = queries.count_waiting

    async def count_then_wait(*args: Any, **kwargs: Any) -> int:
        nonlocal reads
        counted = await real(*args, **kwargs)
        reads += 1
        if reads == 2:
            both.set()
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(both.wait(), timeout=1.5)
        return counted

    monkeypatch.setattr(queries, "count_waiting", count_then_wait)


async def test_two_concurrent_sends_for_one_turn_make_one_case(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    turn = await flagged_turn(env, env.leo, "sensitive")
    await both_have_read_the_count(monkeypatch)

    results = await asyncio.gather(
        send(env, env.leo, turn_id=turn), send(env, env.leo, turn_id=turn)
    )

    assert len({r.case.id for r in results}) == 1
    assert sorted(r.created for r in results) == [False, True]
    assert len(await case_rows(env, env.leo)) == 1


async def test_two_concurrent_sends_past_the_waiting_limit_make_one_case(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    for _ in range(4):
        await send(env, env.leo)
    await both_have_read_the_count(monkeypatch)

    results = await asyncio.gather(send(env, env.leo), send(env, env.leo), return_exceptions=True)

    made = [r for r in results if isinstance(r, CaseOpened)]
    refused = [r for r in results if isinstance(r, ProblemError)]
    assert (len(made), len(refused)) == (1, 1)
    assert refused[0].code == "case-waiting-limit"
    assert len(await case_rows(env, env.leo)) == 5


async def test_a_sixth_waiting_case_is_refused_and_a_closed_one_does_not_count(env: Env) -> None:
    ids = [(await send(env, env.leo)).case.id for _ in range(5)]

    refused = await problem(send(env, env.leo))

    assert (refused.status_code, refused.code) == (409, "case-waiting-limit")
    assert len(await case_rows(env, env.leo)) == 5
    # Another person's cases do not count against Leo, and a closed one stops counting.
    await send(env, env.rae)
    await close_case(env, ids[0])
    await send(env, env.leo)


async def close_case(env: Env, case_id: UUID) -> None:
    async with acting(env.engine, env.tenant.id, env.dana) as (db, actor):
        await service.case_text_for(db, env.keys, actor, case_id)
        await service.change_status(db, actor, case_id, "closed")


@pytest.mark.parametrize(
    ("words", "code"),
    [("", "case-empty-words"), (" \n\t ", "case-empty-words"), ("x" * 4001, "case-words-too-long")],
)
async def test_empty_and_overlong_words_are_refused(env: Env, words: str, code: str) -> None:
    refused = await problem(send(env, env.leo, words))

    assert (refused.status_code, refused.code) == (422, code)
    assert env.transport.requests == []


async def test_exactly_4000_characters_are_accepted(env: Env) -> None:
    assert (await send(env, env.leo, "x" * 4000)).created is True


async def test_an_unknown_category_is_refused(env: Env) -> None:
    refused = await problem(send(env, env.leo, category="gossip"))

    assert refused.code == "case-invalid"


async def test_a_turn_that_is_not_yours_or_not_flagged_or_unknown_is_one_problem(
    env: Env,
) -> None:
    others = await flagged_turn(env, env.rae, "sensitive")
    unflagged = await flagged_turn(env, env.leo, "ordinary")
    no_verdict = await flagged_turn(env, env.leo, None)

    problems = [
        await problem(send(env, env.leo, turn_id=turn))
        for turn in (others, unflagged, no_verdict, uuid4())
    ]

    assert {(p.status_code, p.code, p.detail) for p in problems} == {
        (404, "case-turn-not-found", problems[0].detail)
    }
    assert await case_rows(env, env.leo) == []


async def test_a_flagged_turn_is_sensitive_or_crisis_at_any_status(env: Env) -> None:
    sensitive = await flagged_turn(env, env.leo, "sensitive", status="failed")
    crisis = await flagged_turn(env, env.leo, "crisis", status="crisis")

    assert (await send(env, env.leo, turn_id=sensitive)).created is True
    assert (await send(env, env.leo, turn_id=crisis)).created is True


async def test_a_foreign_key_failure_on_the_turn_is_the_same_problem(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Were the lookup fooled into naming Rae's turn and conversation for Leo, the foreign keys on
    # (turn, person) would still refuse it, and Leo would be told what an unknown turn is told.
    rae_turn = await flagged_turn(env, env.rae, "sensitive")
    async with acting(env.engine, env.tenant.id, env.rae) as (db, _):
        rae_conversation: UUID = (
            await db.execute(
                text("SELECT conversation_id FROM ai_turns WHERE id = :turn"), {"turn": rae_turn}
            )
        ).scalar_one()

    async def fooled(*args: Any, **kwargs: Any) -> UUID:
        return rae_conversation

    monkeypatch.setattr(queries, "own_flagged_turn_conversation", fooled)

    refused = await problem(send(env, env.leo, turn_id=rae_turn))

    assert (refused.status_code, refused.code) == (404, "case-turn-not-found")


# --- the reply-by date from the database's side ---


async def test_the_reply_by_date_uses_both_years_of_denvers_holidays(env: Env) -> None:
    # Dec 30 2026 is a Wednesday. Thu Dec 31 is business day 1; Fri Jan 1 2027 is closed (a holiday
    # of the next year's calendar), the weekend is skipped, and Mon Jan 4 is day 2.
    async with tenant_session(env.engine, TenantContext(env.tenant.id, None)) as session:
        denver = (await session.execute(select(Location.id))).scalar_one()
        session.add(
            Holiday(
                id=uuid4(),
                tenant_id=env.tenant.id,
                location_id=denver,
                holiday_date=date(2027, 1, 1),
                name="New Year's Day",
            )
        )
    sent = datetime(2026, 12, 30, 9, 0, tzinfo=UTC) + timedelta(hours=7)  # 9 AM MST

    async with acting(env.engine, env.tenant.id, env.leo) as (db, _):
        assert await queries.reply_by_at(db, env.tenant.id, sent) == date(2027, 1, 4)
        # 11 PM Thursday Oct 22 2026 in Oakland is Friday in Denver: Tuesday Oct 27, not Monday.
        late = datetime(2026, 10, 23, 6, 0, tzinfo=UTC)
        assert await queries.reply_by_at(db, env.tenant.id, late) == date(2026, 10, 27)


# --- the person's list ---


async def test_my_cases_lists_only_the_actors_own_even_for_hr(env: Env) -> None:
    mine = await send(env, env.leo)
    await send(env, env.rae)
    dana_case = await send(env, env.dana)

    async with acting(env.engine, env.tenant.id, env.leo) as (db, actor):
        leo_list = await service.my_cases(db, actor)
    async with acting(env.engine, env.tenant.id, env.dana) as (db, actor):
        dana_list = await service.my_cases(db, actor)

    assert [c.id for c in leo_list] == [mine.case.id]
    assert [c.id for c in dana_list] == [dana_case.case.id]
    assert {f.name for f in fields(leo_list[0])} == {
        "id",
        "category",
        "status",
        "sent_at",
        "reply_by",
        "status_changed_at",
    }


# --- audited reads ---


async def open_with_summary(env: Env, words: str = WORDS) -> UUID:
    opened = await send(env, env.leo, words)
    async with acting(env.engine, env.tenant.id, env.leo) as (db, _):
        assert await service.record_summary(
            db,
            env.keys,
            opened.case.id,
            SummaryWritten("A neutral summary.", "claude-haiku-5-5", "summary-v1"),
        )
    return opened.case.id


async def test_a_crisis_case_never_shows_or_opens_a_written_summary_even_when_it_is_newest(
    env: Env,
) -> None:
    # A written row, then the label raised to crisis: as if two retries interleaved and the
    # written row were stamped after the crisis one.
    case_id = await open_with_summary(env)
    async with acting(env.engine, env.tenant.id, env.dana) as (db, actor):
        assert await service.record_screening(db, case_id, "crisis", actor=actor)

    async with acting(env.engine, env.tenant.id, env.dana) as (db, actor):
        detail = await service.case_detail(db, actor, case_id)
        read = await service.case_summary_for(db, env.keys, actor, case_id)

    assert detail.summary is not None
    assert (detail.summary.status, detail.summary.reason) == ("failed", "crisis")
    assert (read.status, read.reason, read.text) == ("failed", "crisis", None)
    # The read is audited like any other summary read.
    assert [e.action for e in await audit_events(env.engine, env.tenant.id)].count(
        "case.viewed"
    ) == 1


async def test_hr_reads_the_words_and_the_summary_and_each_read_is_recorded(env: Env) -> None:
    case_id = await open_with_summary(env)

    async with acting(env.engine, env.tenant.id, env.dana) as (db, actor):
        words = await service.case_text_for(db, env.keys, actor, case_id)
        summary = await service.case_summary_for(db, env.keys, actor, case_id)

    assert words == WORDS
    assert (summary.status, summary.text, summary.model) == (
        "written",
        "A neutral summary.",
        "claude-haiku-5-5",
    )
    kinds = [(e.kind, e.actor_person_id) for e in await events_of(env, case_id)]
    # Both reads share one transaction, so one timestamp: their order is not defined.
    assert kinds[:2] == [("opened", env.leo), ("summary_written", None)]
    assert sorted(kinds[2:], key=str) == [("text_read", env.dana), ("viewed", env.dana)]
    [text_read] = await audit_of(env, "case.text.read")
    [viewed] = await audit_of(env, "case.viewed")
    for audit in (text_read, viewed):
        assert (audit.target_type, audit.target_id, audit.actor_person_id, audit.via) == (
            "case",
            case_id,
            env.dana,
            "ui",
        )
        assert (audit.before, audit.after) == (None, None)


async def test_a_read_and_its_events_commit_or_roll_back_together(env: Env) -> None:
    case_id = await open_with_summary(env)

    async def reads_then_fails() -> None:
        async with acting(env.engine, env.tenant.id, env.dana) as (db, actor):
            await service.case_text_for(db, env.keys, actor, case_id)
            await service.case_summary_for(db, env.keys, actor, case_id)
            raise RuntimeError("the request failed after the reads")

    with pytest.raises(RuntimeError):
        await reads_then_fails()

    assert [e.kind for e in await events_of(env, case_id)] == ["opened", "summary_written"]
    assert await audit_of(env, "case.text.read") == []
    assert await audit_of(env, "case.viewed") == []


async def test_a_case_with_no_summary_reads_as_none_and_a_failure_as_failed(env: Env) -> None:
    quiet = (await send(env, env.leo)).case.id
    failed = (await send(env, env.rae)).case.id
    async with acting(env.engine, env.tenant.id, env.rae) as (db, _):
        assert await service.record_summary(db, env.keys, failed, SummaryFailed("timeout"))

    async with acting(env.engine, env.tenant.id, env.dana) as (db, actor):
        none = await service.case_summary_for(db, env.keys, actor, quiet)
        timed_out = await service.case_summary_for(db, env.keys, actor, failed)

    assert (none.status, none.text) == ("none", None)
    assert (timed_out.status, timed_out.reason, timed_out.text) == ("failed", "timeout", None)
    [failure] = await audit_of(env, "case.summary.failed")
    assert (failure.via, failure.actor_person_id, failure.after) == (
        "assistant",
        None,
        {"reason": "timeout"},
    )


async def test_nobody_but_hr_reads_a_case_and_the_refusal_comes_before_any_decrypt(
    env: Env,
) -> None:
    case_id = await open_with_summary(env)
    watched = env.keys
    watched.unwraps = 0  # sealing the summary unwrapped the key once

    for person in (env.leo, env.rae, env.priya):
        async with acting(env.engine, env.tenant.id, person) as (db, actor):
            for read in (service.case_text_for, service.case_summary_for):
                refused = await problem(read(db, watched, actor, case_id))
                assert (refused.status_code, refused.code) == (404, "case-not-found")
    unknown = await problem(read_text(env, env.dana, uuid4()))

    assert unknown.code == "case-not-found"
    assert watched.unwraps == 0
    assert await audit_of(env, "case.text.read") == []
    assert [e.kind for e in await events_of(env, case_id)] == ["opened", "summary_written"]


async def read_text(env: Env, who: UUID, case_id: UUID) -> str:
    async with acting(env.engine, env.tenant.id, who) as (db, actor):
        return await service.case_text_for(db, env.keys, actor, case_id)


async def test_a_manager_of_the_person_gets_the_same_not_found_from_everything(
    env: Env,
) -> None:
    # Leo manages Rae. Rae's case is no more Leo's than a stranger's.
    case_id = (await send(env, env.rae)).case.id

    async with acting(env.engine, env.tenant.id, env.leo) as (db, actor):
        assert actor.report_ids == {env.rae}
        attempts = [
            service.case_detail(db, actor, case_id),
            service.case_text_for(db, env.keys, actor, case_id),
            service.case_summary_for(db, env.keys, actor, case_id),
            service.change_status(db, actor, case_id, "closed"),
            service.queue(db, actor, None, None),
            service.counts(db, actor),
        ]
        problems = [await problem(attempt) for attempt in attempts]
        assert {(p.status_code, p.code, p.detail) for p in problems} == {
            (404, "case-not-found", problems[0].detail)
        }
        assert await service.my_cases(db, actor) == []


async def test_another_sandboxs_hr_cannot_see_the_case(
    env: Env, make_tenant: MakeTenant, app_engine: AsyncEngine
) -> None:
    case_id = (await send(env, env.leo)).case.id
    elsewhere = await make_tenant()

    async with acting(app_engine, elsewhere.id, elsewhere.hr_id) as (db, actor):
        assert actor.is_hr_admin
        attempts = [
            service.case_detail(db, actor, case_id),
            service.case_text_for(db, env.keys, actor, case_id),
            service.case_summary_for(db, env.keys, actor, case_id),
            service.change_status(db, actor, case_id, "closed"),
        ]
        for attempt in attempts:
            assert (await problem(attempt)).code == "case-not-found"
        page = await service.queue(db, actor, None, None)
        assert case_id not in {item.id for item in page.items}


async def test_hr_cannot_read_or_act_on_their_own_case(env: Env) -> None:
    own = (await send(env, env.dana)).case.id

    async with acting(env.engine, env.tenant.id, env.dana) as (db, actor):
        for attempt in (
            service.case_text_for(db, env.keys, actor, own),
            service.case_summary_for(db, env.keys, actor, own),
            service.change_status(db, actor, own, "in_review"),
        ):
            refused = await problem(attempt)
            assert (refused.status_code, refused.code) == (403, "case-own")
        # The metadata is theirs to see: the header only.
        detail = await service.case_detail(db, actor, own)

    assert detail.is_own is True
    assert (detail.summary, detail.timeline, detail.given_name, detail.work_email) == (
        None,
        None,
        None,
        None,
    )
    assert env.keys.unwraps == 0
    assert [e.kind for e in await events_of(env, own)] == ["opened"]


# --- changing the status ---


async def test_the_status_waits_for_this_hr_person_to_read_the_words(env: Env) -> None:
    case_id = (await send(env, env.leo)).case.id

    async with acting(env.engine, env.tenant.id, env.dana) as (db, actor):
        refused = await problem(service.change_status(db, actor, case_id, "in_review"))
    assert (refused.status_code, refused.code) == (409, "words-not-read")

    # Dana reading the words does not open the gate for Hana.
    await read_text(env, env.dana, case_id)
    async with acting(env.engine, env.tenant.id, env.hana) as (db, actor):
        refused = await problem(service.change_status(db, actor, case_id, "in_review"))
    assert refused.code == "words-not-read"
    async with acting(env.engine, env.tenant.id, env.dana) as (db, actor):
        moved = await service.change_status(db, actor, case_id, "in_review")

    assert moved.status == "in_review"
    [change] = [e for e in await events_of(env, case_id) if e.kind == "status_changed"]
    assert (change.actor_person_id, change.from_status, change.to_status) == (
        env.dana,
        "new",
        "in_review",
    )
    [audit] = await audit_of(env, "case.status_changed")
    assert (audit.target_type, audit.target_id, audit.actor_person_id) == (
        "case",
        case_id,
        env.dana,
    )
    assert (audit.before, audit.after) == ({"status": "new"}, {"status": "in_review"})


async def test_the_status_follows_the_triggers_one_way_rules(env: Env) -> None:
    case_id = (await send(env, env.leo)).case.id
    await read_text(env, env.dana, case_id)

    async with acting(env.engine, env.tenant.id, env.dana) as (db, actor):
        for bad in ("new", "bogus"):
            refused = await problem(service.change_status(db, actor, case_id, bad))
            assert (refused.status_code, refused.code) == (409, "case-status-refused")
    async with acting(env.engine, env.tenant.id, env.dana) as (db, actor):
        assert (await service.change_status(db, actor, case_id, "closed")).status == "closed"
    async with acting(env.engine, env.tenant.id, env.dana) as (db, actor):
        for back in ("in_review", "new", "closed"):
            refused = await problem(service.change_status(db, actor, case_id, back))
            assert refused.code == "case-status-refused"

    assert [e.to_status for e in await events_of(env, case_id) if e.kind == "status_changed"] == [
        "closed"
    ]
    assert len(await audit_of(env, "case.status_changed")) == 1


async def test_an_update_that_touches_no_row_changes_nothing_and_is_not_recorded(
    env: Env,
) -> None:
    case_id = (await send(env, env.leo)).case.id
    await read_text(env, env.dana, case_id)

    async def update_that_row_level_security_filters_out() -> None:
        async with acting(env.engine, env.tenant.id, env.dana) as (db, actor):

            @event.listens_for(db.sync_session, "do_orm_execute")
            def lose_the_flag(state: Any) -> None:
                # Just before the update: the policy now hides the row from the statement.
                if state.is_update:
                    state.session.connection().exec_driver_sql(
                        "SELECT set_config('app.is_hr', 'false', true)"
                    )

            await service.change_status(db, actor, case_id, "in_review")

    refused = await problem(update_that_row_level_security_filters_out())

    assert (refused.status_code, refused.code) == (404, "case-not-found")
    assert [e.kind for e in await events_of(env, case_id)] == ["opened", "text_read"]
    assert await audit_of(env, "case.status_changed") == []
    [row] = await case_rows(env, env.leo)
    assert row.status == "new"


async def test_a_status_change_without_the_hr_flag_is_not_found_and_not_recorded(
    env: Env,
) -> None:
    case_id = (await send(env, env.leo)).case.id
    await read_text(env, env.dana, case_id)

    async with tenant_session(env.engine, TenantContext(env.tenant.id, env.dana)) as db:
        actor = await load_actor(db, env.tenant.id, env.dana)
        assert actor is not None
        refused = await problem(service.change_status(db, actor, case_id, "in_review"))

    assert refused.code == "case-not-found"
    assert await audit_of(env, "case.status_changed") == []


async def test_the_person_and_coworkers_cannot_change_a_status(env: Env) -> None:
    case_id = (await send(env, env.rae)).case.id

    for person in (env.rae, env.leo, env.priya):
        async with acting(env.engine, env.tenant.id, person) as (db, actor):
            refused = await problem(service.change_status(db, actor, case_id, "closed"))
            assert (refused.status_code, refused.code) == (404, "case-not-found")


# --- the summary ---


async def test_a_second_summary_from_the_person_is_refused_and_hrs_retry_is_added(env: Env) -> None:
    case_id = await open_with_summary(env)

    async with acting(env.engine, env.tenant.id, env.leo) as (db, _):
        again = await service.record_summary(
            db, env.keys, case_id, SummaryWritten("Another.", "claude-haiku-5-5", "summary-v1")
        )
        # The transaction is still usable after the refusal.
        assert (await db.execute(text("SELECT 1"))).scalar_one() == 1
    async with acting(env.engine, env.tenant.id, env.dana) as (db, actor):
        retry = await service.record_summary(
            db,
            env.keys,
            case_id,
            SummaryWritten("The retry.", "claude-haiku-5-5", "summary-v1"),
            actor=actor,
        )
        newest = await service.case_summary_for(db, env.keys, actor, case_id)

    assert (again, retry) == (False, True)
    assert newest.text == "The retry."
    rows = await hr_query(env, select(CaseSummary.status).where(CaseSummary.case_id == case_id))
    assert len(rows) == 2
    [events] = [[e for e in await events_of(env, case_id) if e.kind == "summary_written"]]
    assert [e.actor_person_id for e in events] == [None, env.dana]


async def test_a_written_summary_for_a_crisis_is_recorded_as_a_failed_crisis_one(env: Env) -> None:
    case_id = await seed_case(env, env.leo, screening="crisis")
    async with acting(env.engine, env.tenant.id, env.dana) as (db, actor):
        noted = await service.record_summary(
            db, env.keys, case_id, SummaryFailed("crisis"), actor=actor
        )
    async with acting(env.engine, env.tenant.id, env.dana) as (db, actor):
        late = await service.record_summary(
            db,
            env.keys,
            case_id,
            SummaryWritten("A late one.", "claude-haiku-5-5", "summary-v1"),
            actor=actor,
        )
    assert (noted, late) == (True, True)
    rows = await hr_query(
        env,
        select(CaseSummary.status, CaseSummary.reason, CaseSummary.ciphertext).where(
            CaseSummary.case_id == case_id
        ),
    )
    # The billed call is recorded, but its text is nowhere.
    assert [(r.status, r.reason, r.ciphertext) for r in rows] == [
        ("failed", "crisis", None),
        ("failed", "crisis", None),
    ]
    kinds = [e.kind for e in await events_of(env, case_id)]
    assert kinds.count("summary_failed") == 2
    assert "summary_written" not in kinds
    audited = [
        e.after
        for e in await audit_events(env.engine, env.tenant.id)
        if e.action.startswith("case.summary.")
    ]
    assert audited == [{"reason": "crisis"}, {"reason": "crisis"}]


async def test_a_summary_after_the_first_ten_minutes_is_refused_for_the_person(env: Env) -> None:
    old = await seed_case(env, env.leo, created_at=datetime.now(UTC) - timedelta(hours=1))

    async with acting(env.engine, env.tenant.id, env.leo) as (db, _):
        recorded = await service.record_summary(db, env.keys, old, SummaryFailed("timeout"))

    assert recorded is False
    assert await events_of(env, old) == []


async def test_hr_cannot_add_a_summary_to_their_own_case(env: Env) -> None:
    own = (await send(env, env.dana)).case.id

    async with acting(env.engine, env.tenant.id, env.dana) as (db, actor):
        refused = await problem(
            service.record_summary(
                db,
                env.keys,
                own,
                SummaryWritten("Mine.", "claude-haiku-5-5", "summary-v1"),
                actor=actor,
            )
        )

    assert (refused.status_code, refused.code) == (403, "case-own")
    assert [e.kind for e in await events_of(env, own)] == ["opened"]


async def test_a_retry_by_someone_who_may_not_act_on_the_case_is_refused(env: Env) -> None:
    case_id = (await send(env, env.rae)).case.id

    # Leo manages Rae but is not HR: naming himself as the retrying actor does not make it HR's.
    async with (
        acting(env.engine, env.tenant.id, env.rae) as (db, _),
        acting(env.engine, env.tenant.id, env.leo) as (_, leo),
    ):
        refused = await problem(
            service.record_summary(db, env.keys, case_id, SummaryFailed("timeout"), actor=leo)
        )

    assert (refused.status_code, refused.code) == (404, "case-not-found")
    assert [e.kind for e in await events_of(env, case_id)] == ["opened"]


async def test_a_summary_for_a_case_the_person_cannot_see_is_not_found(env: Env) -> None:
    case_id = (await send(env, env.leo)).case.id

    async with acting(env.engine, env.tenant.id, env.rae) as (db, _):
        refused = await problem(
            service.record_summary(db, env.keys, case_id, SummaryFailed("timeout"))
        )

    assert refused.code == "case-not-found"


# --- HR's queue and counts ---


def names(items: tuple[QueueItem, ...] | list[QueueItem]) -> list[str]:
    return [item.given_name for item in items]


async def test_the_queue_orders_new_cases_by_reply_date_then_the_rest_oldest_first(
    env: Env,
) -> None:
    day = datetime(2026, 10, 20, 15, tzinfo=UTC)
    # New: ordered by reply-by, then sent time. Open but not new: oldest first.
    a = await seed_case(env, env.leo, reply_by=date(2026, 10, 30), created_at=day)
    b = await seed_case(env, env.rae, reply_by=date(2026, 10, 28), created_at=day + timedelta(1))
    c = await seed_case(env, env.hana, reply_by=date(2026, 10, 28), created_at=day)
    d = await seed_case(env, env.leo, status="in_review", created_at=day - timedelta(days=3))
    f = await seed_case(env, env.rae, status="in_review", created_at=day - timedelta(days=1))
    e = await seed_case(env, env.hana, status="closed", created_at=day - timedelta(days=5))

    async with acting(env.engine, env.tenant.id, env.dana) as (db, actor):
        everything = await service.queue(db, actor, None, None)
        open_ = await service.queue(db, actor, "open", None)
        new = await service.queue(db, actor, "new", None)
        closed = await service.queue(db, actor, "closed", None)

    sample = {a: "a", b: "b", c: "c", d: "d", e: "e", f: "f"}
    assert [sample.get(i.id) for i in open_.items if i.id in sample] == ["c", "b", "a", "d", "f"]
    assert [sample.get(i.id) for i in new.items if i.id in sample] == ["c", "b", "a"]
    assert [sample.get(i.id) for i in closed.items if i.id in sample] == ["e"]
    # The first the page shows is the new ones, whatever their sent date, then the rest.
    assert [i.status for i in everything.items][:1] == ["new"]
    assert {f.name for f in fields(QueueItem)}.isdisjoint({"text", "words", "summary"})


async def test_the_queue_carries_the_persons_facts_the_crisis_fact_and_hrs_own_case(
    env: Env,
) -> None:
    crisis = await seed_case(env, env.leo, screening="crisis", category="safety")
    own = await seed_case(env, env.dana)

    async with acting(env.engine, env.tenant.id, env.dana) as (db, actor):
        page = await service.queue(db, actor, "open", None)

    by_id = {item.id: item for item in page.items}
    item = by_id[crisis]
    assert (item.given_name, item.family_name, item.title, item.location_name) == (
        "Leo",
        "Marsh",
        "Associate",
        "Denver HQ",
    )
    assert (item.category, item.status, item.crisis, item.is_own) == ("safety", "new", True, False)
    assert (item.sent_at is None, item.reply_by is None) == (False, False)
    assert (by_id[own].is_own, by_id[own].crisis) == (True, None)


async def test_hrs_own_case_hides_its_screening_in_the_queue_and_the_detail(env: Env) -> None:
    # A crisis verdict on Dana's own words, and on Leo's.
    own = (await send(env, env.dana, "I want to hurt myself.")).case.id
    others = (await send(env, env.leo, "I want to hurt myself too.")).case.id

    async with acting(env.engine, env.tenant.id, env.dana) as (db, actor):
        page = await service.queue(db, actor, "open", None)
        own_detail = await service.case_detail(db, actor, own)
        other_detail = await service.case_detail(db, actor, others)

    by_id = {item.id: item for item in page.items}
    # Like the opener's own view, HR's own case carries neither the verdict nor the crisis fact.
    assert (by_id[own].is_own, by_id[own].crisis) == (True, None)
    assert (own_detail.is_own, own_detail.screening) == (True, None)
    # Someone else's case still shows them to HR.
    assert (by_id[others].is_own, by_id[others].crisis) == (False, True)
    assert (other_detail.is_own, other_detail.screening) == (False, "crisis")


async def test_the_queue_pages_with_a_cursor(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(queries, "PAGE_SIZE", 2)
    day = datetime(2026, 10, 20, 15, tzinfo=UTC)
    seeded = [
        await seed_case(env, env.leo, reply_by=date(2026, 10, 21 + i), created_at=day)
        for i in range(3)
    ]
    seeded += [
        await seed_case(env, env.rae, status="in_review", created_at=day - timedelta(days=i))
        for i in (2, 1)
    ]
    # Priya's sample case (new, reply-by two days from now) sorts after these 2026 dates only if
    # it is later: close it off by looking at the filter instead.
    walked: list[UUID] = []
    cursor = None
    async with acting(env.engine, env.tenant.id, env.dana) as (db, actor):
        while True:
            page = await service.queue(db, actor, "open", cursor)
            walked += [i.id for i in page.items if i.id in seeded]
            if page.next_cursor is None:
                break
            assert len(page.items) == 2
            cursor = page.next_cursor
        # new by reply date, then in review oldest first.
        assert walked == [seeded[0], seeded[1], seeded[2], seeded[3], seeded[4]]
        bad = await problem(service.queue(db, actor, "open", "not a cursor"))
        forged = await problem(
            service.queue(db, actor, "open", base64.urlsafe_b64encode(b'[0,"x"]').decode())
        )
        wrong_type = await problem(
            service.queue(
                db,
                actor,
                "open",
                base64.urlsafe_b64encode(
                    b'[0, "2026-01-01", "2026-01-01T00:00:00+00:00", 5]'
                ).decode(),
            )
        )
    assert (bad.status_code, bad.code) == (422, "case-invalid-cursor")
    assert forged.code == "case-invalid-cursor"
    assert (wrong_type.status_code, wrong_type.code) == (422, "case-invalid-cursor")
    async with acting(env.engine, env.tenant.id, env.dana) as (db, actor):
        unknown = await problem(service.queue(db, actor, "soon", None))
    assert (unknown.status_code, unknown.code) == (422, "case-invalid")
    assert unknown.detail == texts.INVALID_FILTER_TEXT
    assert unknown.detail != texts.INVALID_CATEGORY_TEXT


async def test_cases_tied_on_reply_date_and_sent_time_page_once_each_in_id_order(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(queries, "PAGE_SIZE", 2)
    sent = datetime(2026, 10, 20, 15, tzinfo=UTC)
    # Three new cases with the same reply-by date and sent time: only the id breaks the tie. They
    # sort before everything else in the sandbox (earlier reply-by), so a page break falls inside
    # the tie.
    tied = [
        await seed_case(env, env.leo, reply_by=date(2026, 10, 22), created_at=sent)
        for _ in range(3)
    ]

    walked: list[UUID] = []
    cursor = None
    async with acting(env.engine, env.tenant.id, env.dana) as (db, actor):
        while True:
            page = await service.queue(db, actor, "new", cursor)
            walked += [i.id for i in page.items if i.id in tied]
            if page.next_cursor is None:
                break
            cursor = page.next_cursor

    assert walked == sorted(tied)


async def test_only_hr_gets_the_queue_and_the_counts(env: Env) -> None:
    for person in (env.leo, env.rae, env.priya):
        async with acting(env.engine, env.tenant.id, person) as (db, actor):
            for call in (service.queue(db, actor, None, None), service.counts(db, actor)):
                assert (await problem(call)).code == "case-not-found"


async def test_counts_are_new_cases_and_the_new_ones_due_today_or_late(env: Env) -> None:
    async with acting(env.engine, env.tenant.id, env.dana) as (db, actor):
        now = await database_now(db)
        # The sandbox's Denver location is in America/Denver.
        today = now.astimezone(ZoneInfo("America/Denver")).date()
        before = await service.counts(db, actor)
    yesterday, tomorrow = today - timedelta(days=1), today + timedelta(days=1)
    for reply in (yesterday, today, tomorrow):
        await seed_case(env, env.leo, reply_by=reply)
    # An in-review case is not "new", and HR's own case cannot be acted on by them.
    await seed_case(env, env.leo, status="in_review", reply_by=yesterday)
    await seed_case(env, env.dana, reply_by=yesterday)

    async with acting(env.engine, env.tenant.id, env.dana) as (db, actor):
        after = await service.counts(db, actor)

    assert (after.new - before.new, after.reply_due - before.reply_due) == (3, 2)


# --- the detail ---


async def test_the_timeline_puts_opened_first_when_events_share_a_moment(env: Env) -> None:
    # `opened` and a failed summary written in one transaction have the same timestamp. The failed
    # summary's ID sorts first here, to show the order does not follow IDs. Both IDs are fresh each
    # run (a small one and a large one), so rows left by an interrupted run can't collide.
    case_id = await seed_case(env, env.leo)
    low = UUID(int=secrets.randbits(64))
    high = UUID(int=(1 << 127) | secrets.randbits(64))
    async with acting(env.engine, env.tenant.id, env.leo) as (db, _):
        for event_id, kind in ((low, "summary_failed"), (high, "opened")):
            await db.execute(
                insert(CaseEvent).values(
                    id=event_id,
                    tenant_id=env.tenant.id,
                    case_id=case_id,
                    actor_person_id=None,
                    kind=kind,
                )
            )
    async with acting(env.engine, env.tenant.id, env.dana) as (db, _):
        rows = await queries.timeline(db, env.tenant.id, case_id)
    kinds = [row.kind for row in rows]
    assert kinds.index("opened") < kinds.index("summary_failed")


async def test_the_detail_shows_metadata_the_summary_state_and_the_timeline(env: Env) -> None:
    case_id = await open_with_summary(env)
    await read_text(env, env.dana, case_id)

    async with acting(env.engine, env.tenant.id, env.dana) as (db, actor):
        detail = await service.case_detail(db, actor, case_id)
        events_before = len(await events_of(env, case_id))

    assert (detail.given_name, detail.family_name, detail.work_email) == (
        "Leo",
        "Marsh",
        "leo@juniperrow.example",
    )
    assert (detail.department_name, detail.location_name) == ("People", "Denver HQ")
    assert detail.summary is not None
    assert detail.summary.status == "written"
    assert detail.timeline is not None
    assert [t.kind for t in detail.timeline] == ["opened", "summary_written", "text_read"]
    assert (detail.timeline[2].actor_given_name, detail.timeline[0].actor_given_name) == (
        "Dana",
        "Leo",
    )
    assert (detail.screening, detail.is_own) == ("ordinary", False)
    # Reading the metadata is not an audited read.
    assert events_before == 3
    assert await audit_of(env, "case.viewed") == []
    assert not any(isinstance(v, str) and WORDS in v for v in asdict(detail).values())


# --- nothing of the words travels ---


async def test_the_words_never_reach_a_log_a_problem_or_an_audit_row(
    env: Env, caplog: pytest.LogCaptureFixture
) -> None:
    words = f"The {CANARY} situation at the shop."
    caplog.set_level(logging.DEBUG)
    seen: list[str] = []

    submission = uuid4()
    opened = await send(env, env.leo, words, submission_id=submission)
    case_id = opened.case.id
    async with acting(env.engine, env.tenant.id, env.leo) as (db, _):
        await service.record_summary(
            db, env.keys, case_id, SummaryWritten(f"About {CANARY}.", "claude-haiku-5-5", "v1")
        )
    # Repeats and refusals that carry the words in their input.
    seen += [repr(opened), repr(OpenCase(submission, "pay", words))]
    conflict = await problem(send(env, env.leo, words + " more", submission_id=submission))
    seen += [str(conflict), repr(conflict), conflict.detail, repr(conflict.extra)]
    ssn = await problem(send(env, env.leo, f"{words} 123-45-6789"))
    seen += [str(ssn), ssn.detail]
    async with acting(env.engine, env.tenant.id, env.dana) as (db, actor):
        got = await service.case_text_for(db, env.keys, actor, case_id)
        summary = await service.case_summary_for(db, env.keys, actor, case_id)
        seen += [repr(summary), repr(await service.case_detail(db, actor, case_id))]
    assert CANARY in got
    assert summary.text is not None
    assert CANARY in summary.text
    async with acting(env.engine, env.tenant.id, env.dana) as (db, actor):
        seen.append(repr(await service.change_status(db, actor, case_id, "in_review")))
        refused = await problem(service.change_status(db, actor, case_id, "new"))
        seen += [str(refused), refused.detail]
    async with acting(env.engine, env.tenant.id, env.dana) as (db, actor):
        seen.append(repr(await service.queue(db, actor, None, None)))

    assert CANARY not in caplog.text
    assert not [s for s in seen if CANARY in s]
    audit = [
        json.dumps([e.action, e.target_type, str(e.target_id), e.before, e.after], default=str)
        for e in await audit_events(env.engine, env.tenant.id)
    ]
    assert not [row for row in audit if CANARY in row]
    timeline = [
        (e.kind, e.from_status, e.to_status, str(e.actor_person_id))
        for e in await events_of(env, case_id)
    ]
    assert CANARY not in json.dumps(timeline)
    ledger = await hr_query(env, select(AiSpend.purpose, AiSpend.kind, AiSpend.amount_usd))
    assert CANARY not in json.dumps([[str(c) for c in row] for row in ledger])
    # At rest too: neither the words nor the summary is in the clear.
    [row] = await case_rows(env, env.leo)
    assert CANARY.encode() not in row.text_ciphertext
    stored = await hr_query(env, select(CaseSummary.ciphertext))
    assert all(CANARY.encode() not in (r.ciphertext or b"") for r in stored)


# --- two retries in flight on one unscreened case ---

CRISIS_WORDS = "I want to hurt myself."


class Writes:
    """A summarizer that writes a neutral summary and counts its calls."""

    def __init__(self) -> None:
        self.calls = 0

    async def summarize(self, request: Any) -> Any:
        from app.ai.case_summary import SummaryAnswer
        from app.ai.pricing import Usage

        self.calls += 1
        return SummaryAnswer(
            "The person wrote about pay.", "scripted", "scripted-1", Usage(1, 1, 0, 0)
        )


async def retry_job(env: Env, case_id: UUID, words: str, writes: Writes) -> Any:
    """A retry's background job, built as the route builds it (HR's, screening first)."""
    from app.modules.cases.summary_task import SummaryJob

    async with acting(env.engine, env.tenant.id, env.dana) as (_, actor):
        pass
    return SummaryJob(
        guard=env.guard(),
        keys=env.keys,
        summarizer=writes,
        ctx=TenantContext(env.tenant.id, env.dana),
        case_id=case_id,
        category="pay",
        words=words,
        actor=actor,
        screen_first=True,
    )


async def screening_and_summaries(env: Env, case_id: UUID) -> tuple[str, list[tuple[str, Any]]]:
    async with acting(env.engine, env.tenant.id, env.dana) as (db, _):
        screening = (
            await db.execute(select(Case.screening).where(Case.id == case_id))
        ).scalar_one()
        rows = (
            await db.execute(
                select(CaseSummary.status, CaseSummary.reason)
                .where(CaseSummary.case_id == case_id)
                .order_by(CaseSummary.created_at, CaseSummary.id)
            )
        ).all()
    return screening, [(r.status, r.reason) for r in rows]


async def test_a_crisis_job_first_then_an_ordinary_job_leaves_no_written_summary(env: Env) -> None:
    from app.modules.cases.summary_task import run_summary_job

    case_id = await seed_case(env, env.leo, screening="unscreened", words=WORDS)
    writes = Writes()
    crisis = await retry_job(env, case_id, CRISIS_WORDS, writes)
    ordinary = await retry_job(env, case_id, WORDS, writes)

    await run_summary_job(crisis)
    await run_summary_job(ordinary)

    screening, summaries = await screening_and_summaries(env, case_id)
    assert screening == "crisis"
    # The ordinary job called the model before it found the case was already a crisis.
    assert writes.calls == 1
    # Each job recorded the crisis note; neither a summary.
    assert summaries == [("failed", "crisis"), ("failed", "crisis")]


@pytest.mark.parametrize(
    ("first_words", "first_label"), [(WORDS, "ordinary"), ("They harass me.", "sensitive")]
)
async def test_a_crisis_job_after_another_verdict_raises_the_label_to_crisis(
    env: Env, first_words: str, first_label: str
) -> None:
    from app.modules.cases.summary_task import run_summary_job

    case_id = await seed_case(env, env.leo, screening="unscreened", words=WORDS)
    writes = Writes()
    first = await retry_job(env, case_id, first_words, writes)
    crisis = await retry_job(env, case_id, CRISIS_WORDS, writes)

    await run_summary_job(first)
    await run_summary_job(crisis)

    screening, summaries = await screening_and_summaries(env, case_id)
    # The crisis job raises the label (ordinary or sensitive to crisis, once): no written summary
    # of its own, and a "failed, crisis" note HR's detail shows.
    assert screening == "crisis"
    assert summaries == [("written", None), ("failed", "crisis")]
    assert writes.calls == 1
    screened = [
        e.after
        for e in await audit_events(env.engine, env.tenant.id)
        if e.action == "case.screened"
    ]
    assert screened == [{"screening": first_label}, {"screening": "crisis"}]
    async with acting(env.engine, env.tenant.id, env.dana) as (db, actor):
        queue = await service.queue(db, actor, None, None)
        detail = await service.case_detail(db, actor, case_id)
    assert [i.crisis for i in queue.items if i.id == case_id] == [True]
    assert detail.summary is not None
    assert (detail.screening, detail.summary.status, detail.summary.reason) == (
        "crisis",
        "failed",
        "crisis",
    )


async def test_a_non_crisis_job_that_loses_to_another_verdict_records_the_conflict(
    env: Env, caplog: pytest.LogCaptureFixture
) -> None:
    from app.modules.cases.summary_task import run_summary_job

    case_id = await seed_case(env, env.leo, screening="unscreened", words=WORDS)
    writes = Writes()
    sensitive = await retry_job(env, case_id, "They harass me.", writes)
    ordinary = await retry_job(env, case_id, WORDS, writes)

    await run_summary_job(sensitive)
    with caplog.at_level(logging.WARNING):
        await run_summary_job(ordinary)

    screening, summaries = await screening_and_summaries(env, case_id)
    # The other job's verdict stands; this AI action is recorded, not dropped.
    assert (screening, summaries) == (
        "sensitive",
        [("written", None), ("failed", "screening-conflict")],
    )
    assert str(case_id) in caplog.text
    assert WORDS not in caplog.text
    kinds = [e.kind for e in await events_of(env, case_id)]
    assert kinds.count("summary_failed") == 1
    failed = [
        e.after
        for e in await audit_events(env.engine, env.tenant.id)
        if e.action == "case.summary.failed"
    ]
    assert failed == [{"reason": "screening-conflict"}]
    async with acting(env.engine, env.tenant.id, env.dana) as (db, actor):
        detail = await service.case_detail(db, actor, case_id)
    assert detail.summary is not None
    assert (detail.summary.status, detail.summary.reason) == ("failed", "screening-conflict")


async def test_a_refused_write_back_on_a_still_unscreened_case_records_unscreened(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.modules.cases.summary_task import run_summary_job

    async def refused(*args: Any, **kwargs: Any) -> bool:
        return False

    monkeypatch.setattr(service, "record_screening", refused)
    case_id = await seed_case(env, env.leo, screening="unscreened", words=WORDS)
    job = await retry_job(env, case_id, WORDS, Writes())

    await run_summary_job(job)

    screening, summaries = await screening_and_summaries(env, case_id)
    assert (screening, summaries) == ("unscreened", [("failed", "unscreened")])


async def test_a_retry_is_refused_for_a_crisis_case(env: Env) -> None:
    case_id = await seed_case(env, env.leo, screening="crisis", words=WORDS)
    async with acting(env.engine, env.tenant.id, env.dana) as (db, actor):
        await service.record_summary(db, env.keys, case_id, SummaryFailed("timeout"), actor=actor)

    refused = await problem(plan(env, case_id))

    assert (refused.status_code, refused.code) == (409, "summary-retry-refused")


async def test_a_retry_uses_the_screening_as_it_is_under_the_lock(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    case_id = await failed_unscreened_case(env)
    real_lock = queries.lock_case

    async def lock_after_another_retry_screened(*args: Any) -> Any:
        # Between the read and the lock, another request screens the case as a crisis.
        async with acting(env.engine, env.tenant.id, env.dana) as (other, actor):
            assert await service.record_screening(other, case_id, "crisis", actor=actor)
        return await real_lock(*args)

    monkeypatch.setattr(queries, "lock_case", lock_after_another_retry_screened)

    refused = await problem(plan(env, case_id))

    assert (refused.status_code, refused.code) == (409, "summary-retry-refused")


async def test_my_cases_reads_only_the_views_columns_and_honors_a_limit(env: Env) -> None:
    for _ in range(3):
        await seed_case(env, env.leo, words=WORDS)
    async with acting(env.engine, env.tenant.id, env.leo) as (db, actor):
        statements: list[str] = []
        sync = db.sync_session.get_bind()
        event.listen(sync, "before_cursor_execute", lambda *a: statements.append(a[2]))
        everything = await service.my_cases(db, actor)
        two = await service.my_cases(db, actor, limit=2)

    assert (len(everything), len(two)) == (3, 2)
    selects = [q for q in statements if "FROM cases" in q]
    assert selects
    assert all("text_ciphertext" not in q for q in selects)
    assert "LIMIT" in selects[-1]


async def failed_unscreened_case(env: Env) -> UUID:
    """An unscreened case with the opener's fixed `unscreened` note: HR may retry it at once."""
    case_id = await seed_case(env, env.leo, screening="unscreened", words=WORDS)
    async with acting(env.engine, env.tenant.id, env.leo) as (db, _):
        assert await service.record_summary(db, env.keys, case_id, SummaryFailed("unscreened"))
    return case_id


async def plan(env: Env, case_id: UUID) -> Any:
    async with acting(env.engine, env.tenant.id, env.dana) as (db, actor):
        return await service.plan_summary_retry(db, env.keys, actor, case_id)


async def test_a_second_retry_while_one_is_in_flight_is_refused(env: Env) -> None:
    case_id = await failed_unscreened_case(env)

    await plan(env, case_id)
    refused = await problem(plan(env, case_id))

    assert (refused.status_code, refused.code) == (409, "summary-retry-refused")


async def test_a_retry_is_allowed_again_once_the_job_has_recorded_its_result(env: Env) -> None:
    case_id = await failed_unscreened_case(env)
    await plan(env, case_id)
    async with acting(env.engine, env.tenant.id, env.dana) as (db, actor):
        assert await service.record_summary(
            db, env.keys, case_id, SummaryFailed("timeout"), actor=actor
        )

    again = await plan(env, case_id)

    assert again.case_id == case_id


async def test_a_retry_is_allowed_again_after_the_window_if_the_job_never_recorded(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    case_id = await failed_unscreened_case(env)
    await plan(env, case_id)
    monkeypatch.setattr(service, "IN_FLIGHT_WINDOW", timedelta(0))

    again = await plan(env, case_id)

    assert again.case_id == case_id


async def test_the_window_covers_the_summary_and_screening_time_limits_with_a_margin() -> None:
    from app.ai.case_summary import SUMMARY_TIMEOUT_SECONDS
    from app.ai.transport import GUARD_TIMEOUT_SECONDS

    needed = SUMMARY_TIMEOUT_SECONDS + GUARD_TIMEOUT_SECONDS
    assert timedelta(seconds=needed) < service.IN_FLIGHT_WINDOW
    assert timedelta(seconds=needed * 2) >= service.IN_FLIGHT_WINDOW


async def test_a_retry_started_while_another_is_open_waits_for_it_and_is_then_refused(
    env: Env,
) -> None:
    case_id = await failed_unscreened_case(env)

    async with acting(env.engine, env.tenant.id, env.dana) as (db, actor):
        await service.plan_summary_retry(db, env.keys, actor, case_id)
        second = asyncio.create_task(plan(env, case_id))
        await asyncio.sleep(0.5)
        # The first request has not committed, and holds the case: the second is waiting for it.
        assert second.done() is False

    refused = await problem(second)
    assert (refused.status_code, refused.code) == (409, "summary-retry-refused")


async def test_two_jobs_that_find_the_same_verdict_both_write(env: Env) -> None:
    from app.modules.cases.summary_task import run_summary_job

    case_id = await seed_case(env, env.leo, screening="unscreened", words=WORDS)
    writes = Writes()
    first = await retry_job(env, case_id, WORDS, writes)
    second = await retry_job(env, case_id, WORDS, writes)

    await run_summary_job(first)
    await run_summary_job(second)

    screening, summaries = await screening_and_summaries(env, case_id)
    assert (screening, summaries) == ("ordinary", [("written", None), ("written", None)])


async def test_a_written_summary_for_a_crisis_case_is_recorded_as_a_failed_crisis_note(
    env: Env,
) -> None:
    case_id = await seed_case(env, env.leo, screening="crisis")

    async with acting(env.engine, env.tenant.id, env.dana) as (db, actor):
        written = await service.record_summary(
            db,
            env.keys,
            case_id,
            SummaryWritten("A neutral summary.", "claude-haiku-5-5", "summary-v1"),
            actor=actor,
        )
        failed = await service.record_summary(
            db, env.keys, case_id, SummaryFailed("crisis"), actor=actor
        )

    assert (written, failed) == (True, True)
    _, summaries = await screening_and_summaries(env, case_id)
    assert summaries == [("failed", "crisis"), ("failed", "crisis")]


async def test_a_second_screening_write_loses_the_race_and_says_so(env: Env) -> None:
    case_id = await seed_case(env, env.leo, screening="unscreened", words=WORDS)

    async with acting(env.engine, env.tenant.id, env.dana) as (db, actor):
        first = await service.record_screening(db, case_id, "crisis", actor=actor)
    async with acting(env.engine, env.tenant.id, env.dana) as (db, actor):
        second = await service.record_screening(db, case_id, "ordinary", actor=actor)
        current = await service.screening_of(db, case_id)

    assert (first, second, current) == (True, False, "crisis")


async def test_a_written_summary_waits_for_a_crisis_another_retry_has_not_committed(
    env: Env,
) -> None:
    case_id = await seed_case(env, env.leo, screening="ordinary", words=WORDS)
    written = SummaryWritten("A neutral summary.", "claude-haiku-5-5", "summary-v1")
    async with acting(env.engine, env.tenant.id, env.dana) as (first, first_actor):
        # The label is raised to crisis but not committed: the case's row is locked.
        assert await service.record_screening(first, case_id, "crisis", actor=first_actor)

        async def late_writer() -> bool:
            async with acting(env.engine, env.tenant.id, env.dana) as (second, second_actor):
                return await service.record_summary(
                    second, env.keys, case_id, written, actor=second_actor
                )

        task = asyncio.create_task(late_writer())
        await asyncio.sleep(0.5)
        assert not task.done()  # it is waiting for the case's row, not past the check
    # It saw the crisis only after the first session committed, so it recorded a failed one.
    assert await asyncio.wait_for(task, 5) is True
    rows = await hr_query(
        env, select(CaseSummary.status, CaseSummary.reason).where(CaseSummary.case_id == case_id)
    )
    assert [(r.status, r.reason) for r in rows] == [("failed", "crisis")]
