"""The time-off routes over HTTP: sessions, CSRF, who may see and do what, the engine's refusals as
problems, the Approvals queue with team coverage, the date picker's marks, and the summary.

Each test starts a real sandbox (the 145-person seed) as a persona. Marcus Bell manages Priya Raman,
Leo, and three department leads (Zara Bautista is the apparel lead, whose pending request waits in
his queue); the apparel associates report to Zara, so Marcus is their skip-level manager. Dana is
HR. The routes read the clock through a dependency, so a test holds "now" still: by default at the
moment it starts, and far in the future where it needs a window the seeded history never touches.
Rows a test needs as history are inserted directly, as the API's own login.
"""

import json
import logging
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4, uuid5

import pytest
from sqlalchemy import event, insert, select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api import deps
from app.db.models import Person, TimeOffRequest
from app.db.tenancy import TenantContext, tenant_session
from app.domain.holidays import holidays_for
from app.domain.timeoff.labels import label
from app.domain.timeoff.today import today_at
from app.modules.identity.actor import load_actor
from app.modules.identity.cookies import CSRF_COOKIE, SESSION_COOKIE
from app.modules.identity.sessions import start_session
from app.modules.timeoff import queries, routes
from app.modules.timeoff.coverage import CoverageRequest, team_coverage
from app.modules.timeoff.texts import REFUSAL_TEXTS
from app.policy import Action
from app.policy import can as can_policy
from tests.integration.conftest import (
    Browser,
    MakeTenant,
    OpenBrowser,
    audit_events,
)

pytestmark = pytest.mark.integration

BASE = "/api/v1/time-off"
OAKLAND = "America/Los_Angeles"
MON_TO_FRI = [1, 2, 3, 4, 5]


def monday_on_or_after(day: date) -> date:
    return day + timedelta(days=(7 - day.weekday()) % 7)


def oakland_holidays(*years: int) -> dict[date, str]:
    return {h.holiday_date: h.name for year in years for h in holidays_for("oak", year)}


class World:
    """One sandbox, one browser, and a held clock."""

    def __init__(
        self,
        browser: Browser,
        sandbox: dict[str, Any],
        engine: AsyncEngine,
        owner: AsyncEngine,
        now: datetime,
    ) -> None:
        self.browser = browser
        self.tenant_id = UUID(sandbox["tenant"]["id"])
        self.engine = engine
        self.owner = owner
        self.now = now
        self.hold(now)

    # -- the clock
    def hold(self, now: datetime) -> None:
        self.now = now
        self.browser.client.app.dependency_overrides[deps.utc_now] = lambda: now  # type: ignore[attr-defined]

    @property
    def today(self) -> date:
        """Today in Oakland, where Marcus, Priya, and the apparel team are."""
        return today_at(OAKLAND, self.now)

    # -- who
    def person(self, key: str) -> UUID:
        return uuid5(self.tenant_id, f"person:{key}")

    def switch(self, persona: str) -> None:
        response = self.browser.client.put(
            "/api/v1/session/persona", json={"persona": persona}, headers=self.browser.csrf
        )
        assert response.status_code == 200, response.text

    # -- HTTP
    def get(self, path: str, **params: Any) -> Any:
        return self.browser.client.get(BASE + path, params=params)

    def post(self, path: str, body: object = None) -> Any:
        return self.browser.client.post(BASE + path, json=body, headers=self.browser.csrf)

    # -- rows, written directly
    async def put(
        self,
        key: str | UUID,
        start: date,
        end: date | None = None,
        *,
        type: str = "pto",
        status: str | None = None,
        amount_minutes: int = 480,
        partial_minutes: int | None = None,
        created_at: datetime | None = None,
        note: str | None = None,
    ) -> UUID:
        person_id = key if isinstance(key, UUID) else self.person(key)
        status = status or ("pending" if type == "pto" else "recorded")
        decided = status in {"approved", "denied"}
        decider = (
            self.person("dana") if person_id == self.person("marcus") else self.person("marcus")
        )
        request_id = uuid4()
        values: dict[str, Any] = {
            "id": request_id,
            "tenant_id": self.tenant_id,
            "person_id": person_id,
            "type": type,
            "start_date": start,
            "end_date": end or start,
            "partial_minutes": partial_minutes,
            "amount_minutes": amount_minutes,
            "status": status,
            "created_via": "ui",
            "decided_by": decider if decided else None,
            "decided_at": self.now if decided else None,
            "decision_note": note if status == "denied" else None,
            "canceled_at": self.now if status == "canceled" else None,
        }
        if created_at is not None:
            values["created_at"] = created_at
        async with tenant_session(self.engine, TenantContext(self.tenant_id, None)) as session:
            await session.execute(insert(TimeOffRequest).values(**values))
        return request_id

    async def put_many_sick_days(self, key: str, first: date, count: int) -> None:
        person_id = self.person(key)
        rows = [
            {
                "tenant_id": self.tenant_id,
                "person_id": person_id,
                "type": "sick",
                "start_date": first + timedelta(days=offset),
                "end_date": first + timedelta(days=offset),
                "amount_minutes": 480,
                "status": "recorded",
                "created_via": "ui",
            }
            for offset in range(count)
        ]
        async with tenant_session(self.engine, TenantContext(self.tenant_id, None)) as session:
            await session.execute(insert(TimeOffRequest), rows)

    async def set_weekdays(self, key: str, weekdays: list[int]) -> None:
        async with self.owner.begin() as connection:
            await connection.execute(
                text("UPDATE people SET scheduled_weekdays = :days WHERE id = :id"),
                {"days": weekdays, "id": self.person(key)},
            )

    async def clear_manager(self, key: str) -> None:
        """Leave the person with no manager, as the CEO is."""
        async with self.owner.begin() as connection:
            await connection.execute(
                text("UPDATE people SET manager_id = NULL WHERE id = :id"), {"id": self.person(key)}
            )

    async def fund(self, key: str, minutes: int = 9600) -> None:
        """Give the person an opening big enough to request from (20 days by default)."""
        async with self.owner.begin() as connection:
            await connection.execute(
                text("UPDATE time_off_openings SET amount_minutes = :m WHERE person_id = :id"),
                {"m": minutes, "id": self.person(key)},
            )

    async def name_of(self, key: str) -> str:
        async with tenant_session(self.engine, TenantContext(self.tenant_id, None)) as session:
            row = (
                await session.execute(
                    select(Person.given_name, Person.family_name).where(
                        Person.id == self.person(key)
                    )
                )
            ).one()
        return f"{row.given_name} {row.family_name}"

    async def timeoff_events(self) -> list[Any]:
        return [
            e
            for e in await audit_events(self.engine, self.tenant_id)
            if e.action.startswith("timeoff.")
        ]

    def workday(self, days_ahead: int) -> date:
        """The first Monday to Friday on or after today plus `days_ahead` that Oakland works."""
        holidays = oakland_holidays(self.today.year, self.today.year + 1, self.today.year + 2)
        day = self.today + timedelta(days=days_ahead)
        while day.isoweekday() > 5 or day in holidays:
            day += timedelta(days=1)
        return day


StartWorld = Callable[..., World]


@pytest.fixture
def start(
    open_browser: OpenBrowser, app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> StartWorld:
    def begin(persona: str = "priya", *, now: datetime | None = None) -> World:
        browser = open_browser()
        sandbox = browser.start_sandbox(persona)
        return World(browser, sandbox, app_engine, owner_engine, now or datetime.now(UTC))

    return begin


def far(days: int = 400) -> datetime:
    """A moment well after the seeded history, so a test can write rows around "today" freely."""
    return datetime.now(UTC) + timedelta(days=days)


def problem_of(response: Any, status_code: int) -> dict[str, Any]:
    assert response.status_code == status_code, response.text
    assert response.headers["content-type"] == "application/problem+json"
    body: dict[str, Any] = response.json()
    return body


# ---------------------------------------------------------------------------------------------
# The session and CSRF

ALL_ROUTES = [
    ("get", "/balances", None),
    ("get", "/requests", None),
    ("get", f"/requests/{uuid4()}", None),
    ("get", "/calendar?from=2026-01-01&to=2026-01-31", None),
    ("post", "/check", {"type": "pto", "startDate": "2030-01-07", "endDate": "2030-01-07"}),
    ("post", "/requests", {"type": "pto", "startDate": "2030-01-07", "endDate": "2030-01-07"}),
    ("post", f"/requests/{uuid4()}/decision", {"decision": "approve"}),
    ("post", f"/requests/{uuid4()}/cancel", None),
    ("get", "/summary", None),
]
WRITES = [route for route in ALL_ROUTES if route[0] == "post"]


@pytest.mark.parametrize(("method", "path", "body"), ALL_ROUTES)
def test_every_route_needs_a_session(
    browser: Browser, method: str, path: str, body: object
) -> None:
    response = browser.client.request(method, BASE + path, json=body)

    assert problem_of(response, 401)["title"] == "Unauthorized"


@pytest.mark.parametrize(("method", "path", "body"), WRITES)
async def test_a_write_without_the_csrf_header_is_forbidden_and_writes_nothing(
    start: StartWorld, method: str, path: str, body: object
) -> None:
    world = start("priya")

    response = world.browser.client.post(BASE + path, json=body)

    assert problem_of(response, 403)["detail"] == "The CSRF token is missing or wrong."
    assert await world.timeoff_events() == []


# ---------------------------------------------------------------------------------------------
# Balances


def test_balances_give_every_figure_as_minutes_and_a_label_with_its_rules(
    start: StartWorld,
) -> None:
    world = start("priya")

    response = world.get("/balances")

    assert response.status_code == 200, response.text
    body = response.json()
    pto = body["pto"]
    assert body["personId"] == str(world.person("priya"))
    for figure in ("earned", "taken", "booked", "pending", "available", "ceiling", "nextEarning"):
        minutes = pto[f"{figure}Minutes"]
        assert isinstance(minutes, int)
        assert pto[f"{figure}Label"] == label(minutes)
    # The ledger adds up to the figure.
    assert (
        pto["earnedMinutes"] - pto["takenMinutes"] - pto["bookedMinutes"] - pto["pendingMinutes"]
        == pto["availableMinutes"]
    )
    # Priya works in California, so the sick year is the California grant: 40 hours.
    [year] = body["sick"]
    assert (year["year"], year["grantedMinutes"], year["grantedLabel"]) == (
        world.today.year,
        2400,
        "40 hours (5 days)",
    )
    for key in ("used", "booked", "available"):
        assert year[f"{key}Label"] == label(year[f"{key}Minutes"])
    assert {rule["rule"] for rule in body["rules"]} >= {"pto-earning", "sick-grant"}
    for rule in body["rules"]:
        assert set(rule) == {"sectionId", "rule", "title", "deepLink"}
        assert rule["title"]
        assert rule["deepLink"] == f"/handbook/{rule['sectionId']}"


def test_a_manager_and_hr_read_a_persons_balances_and_the_person_may_not_be_read_by_a_peer(
    start: StartWorld,
) -> None:
    world = start("marcus")
    priya = world.person("priya")
    assert world.get("/balances", person=str(priya)).status_code == 200
    assert world.get("/balances", person=str(priya)).json()["personId"] == str(priya)
    world.switch("dana")
    assert world.get("/balances", person=str(world.person("leo"))).status_code == 200
    world.switch("priya")

    peer = world.get("/balances", person=str(world.person("leo")))
    mateo = world.get("/balances", person=str(world.person("mateo")))

    assert problem_of(peer, 404)["type"] == "not-found"
    assert problem_of(mateo, 404)["type"] == "not-found"


def test_a_person_who_does_not_exist_and_one_in_another_sandbox_look_the_same(
    start: StartWorld,
) -> None:
    mine = start("priya")
    other = start("priya")
    hidden = mine.get("/balances", person=str(mine.person("leo")))
    missing = mine.get("/balances", person=str(uuid4()))
    elsewhere = mine.get("/balances", person=str(other.person("priya")))

    for response in (missing, elsewhere):
        assert problem_of(response, 404)["type"] == "not-found"
        assert problem_of(response, 404)["detail"] == REFUSAL_TEXTS["not-found"]
    assert hidden.json()["type"] == missing.json()["type"]
    assert hidden.json()["detail"] == missing.json()["detail"]


# ---------------------------------------------------------------------------------------------
# The request list


async def test_mine_defaults_to_30_days_back_and_120_ahead_of_the_callers_today(
    start: StartWorld,
) -> None:
    world = start("priya", now=far())
    today = world.today
    ids = {
        "before": await world.put("priya", today - timedelta(days=31), type="sick"),
        "first": await world.put("priya", today - timedelta(days=30), type="sick"),
        "last": await world.put("priya", today + timedelta(days=120), type="sick"),
        "after": await world.put("priya", today + timedelta(days=121), type="sick"),
    }

    body = world.get("/requests").json()

    assert {item["id"] for item in body["items"]} == {str(ids["first"]), str(ids["last"])}
    assert (body["fromDate"], body["toDate"]) == (
        (today - timedelta(days=30)).isoformat(),
        (today + timedelta(days=120)).isoformat(),
    )


async def test_the_window_is_the_callers_own_today_not_utc(start: StartWorld) -> None:
    # 03:00 UTC on a day is still the evening before in Oakland.
    moment = (far() + timedelta(days=1)).replace(hour=3, minute=0, second=0, microsecond=0)
    world = start("priya", now=moment)

    body = world.get("/requests").json()

    assert body["fromDate"] == (moment.date() - timedelta(days=1) - timedelta(days=30)).isoformat()


async def test_a_request_that_overlaps_the_window_is_in_it(start: StartWorld) -> None:
    world = start("priya", now=far())
    today = world.today
    spanning = await world.put(
        "leo", today - timedelta(days=33), today - timedelta(days=29), type="sick"
    )
    world.switch("marcus")

    items = world.get("/requests", scope="team").json()["items"]

    assert str(spanning) in {item["id"] for item in items}


async def test_the_window_can_be_chosen_and_must_not_run_backwards(start: StartWorld) -> None:
    world = start("priya", now=far())
    day = world.today + timedelta(days=200)
    inside = await world.put("priya", day, type="sick")

    chosen = world.get("/requests", **{"from": day.isoformat(), "to": day.isoformat()})
    only_to = world.get("/requests", to=(world.today + timedelta(days=210)).isoformat())
    to_before_default_from = world.get(
        "/requests", to=(world.today - timedelta(days=60)).isoformat()
    )
    backwards = world.get("/requests", **{"from": "2030-02-01", "to": "2030-01-01"})
    only_from = world.get("/requests", **{"from": (world.today + timedelta(days=500)).isoformat()})

    assert [item["id"] for item in chosen.json()["items"]] == [str(inside)]
    assert [item["id"] for item in only_to.json()["items"]] == [str(inside)]
    assert problem_of(to_before_default_from, 422)["status"] == 422
    assert problem_of(backwards, 422)["status"] == 422
    assert problem_of(only_from, 422)["status"] == 422


async def test_no_more_than_200_rows_come_back_earliest_first(start: StartWorld) -> None:
    world = start("priya", now=far())
    first = world.today + timedelta(days=1)
    await world.put_many_sick_days("priya", first, 205)

    body = world.get(
        "/requests",
        **{"from": first.isoformat(), "to": (first + timedelta(days=400)).isoformat()},
    ).json()

    assert len(body["items"]) == 200
    days = [item["startDate"] for item in body["items"]]
    assert days == sorted(days)
    assert days[0] == first.isoformat()
    assert days[-1] == (first + timedelta(days=199)).isoformat()


async def test_team_is_everyone_below_the_caller_and_not_the_caller(start: StartWorld) -> None:
    world = start("marcus", now=far())
    day = world.today + timedelta(days=10)
    direct = await world.put("priya", day, type="sick")
    indirect = await world.put("oak-apparel-1", day, type="sick")
    own = await world.put("marcus", day, type="sick")
    elsewhere = await world.put("mateo", day, type="sick")

    ids = {item["id"] for item in world.get("/requests", scope="team").json()["items"]}

    assert {str(direct), str(indirect)} <= ids
    assert str(own) not in ids
    assert str(elsewhere) not in ids
    # Someone with no reports has an empty team.
    world.switch("priya")
    assert world.get("/requests", scope="team").json()["items"] == []


async def test_mine_is_only_the_callers_own(start: StartWorld) -> None:
    world = start("marcus", now=far())
    day = world.today + timedelta(days=10)
    own = await world.put("marcus", day, type="sick")
    await world.put("priya", day, type="sick")

    items = world.get("/requests").json()["items"]

    assert [item["id"] for item in items] == [str(own)]


async def test_waiting_is_pending_pto_from_direct_reports_only_oldest_sent_first(
    start: StartWorld,
) -> None:
    world = start("marcus", now=far())
    today = world.today
    when = world.now
    newer = await world.put(
        "priya", today + timedelta(days=20), created_at=when - timedelta(days=1)
    )
    # Far ahead, beyond the default window: it still needs a decision.
    older = await world.put("leo", today + timedelta(days=300), created_at=when - timedelta(days=3))
    excluded = {
        "indirect": await world.put("oak-apparel-1", today + timedelta(days=20)),
        "approved": await world.put("oak-home-lead", today + timedelta(days=20), status="approved"),
        "denied": await world.put("oak-front-end", today + timedelta(days=20), status="denied"),
        "sick": await world.put("priya", today + timedelta(days=40), type="sick"),
        "own": await world.put("marcus", today + timedelta(days=20)),
    }

    ids = [item["id"] for item in world.get("/requests", scope="waiting").json()["items"]]

    assert str(excluded["own"]) not in ids
    assert set(ids) == {str(newer), str(older), str(await seeded_zara_request(world))}
    assert ids.index(str(older)) < ids.index(str(newer))
    # The seeded one was sent two days before the anchor, which is before both of these.
    assert ids[0] == str(await seeded_zara_request(world))
    assert not (set(ids) & {str(value) for value in excluded.values()})


async def seeded_zara_request(world: World) -> UUID:
    async with tenant_session(world.engine, TenantContext(world.tenant_id, None)) as session:
        return (
            await session.execute(
                select(TimeOffRequest.id).where(
                    TimeOffRequest.person_id == world.person("oak-apparel-lead"),
                    TimeOffRequest.status == "pending",
                )
            )
        ).scalar_one()


def test_someone_with_no_reports_has_nothing_waiting(start: StartWorld) -> None:
    world = start("priya")

    assert world.get("/requests", scope="waiting").json()["items"] == []


def test_an_unknown_scope_is_a_422(start: StartWorld) -> None:
    assert problem_of(start("priya").get("/requests", scope="everyone"), 422)["status"] == 422


async def test_every_row_passes_the_read_policy_a_second_time(
    start: StartWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = start("marcus", now=far())
    day = world.today + timedelta(days=10)
    kept = await world.put("priya", day, type="sick")
    dropped = await world.put("leo", day, type="sick")
    real_can = can_policy
    leo = world.person("leo")

    def can(actor: Any, action: Action, target: Any, **kwargs: Any) -> bool:
        return target.person_id != leo and real_can(actor, action, target, **kwargs)

    monkeypatch.setattr(routes, "can", can)

    ids = {item["id"] for item in world.get("/requests", scope="team").json()["items"]}

    assert str(kept) in ids
    assert str(dropped) not in ids


async def test_a_row_carries_its_people_dates_amount_label_and_decision(start: StartWorld) -> None:
    world = start("priya", now=far())
    day = world.today + timedelta(days=10)
    approved = await world.put(
        "priya", day, status="approved", amount_minutes=240, partial_minutes=240
    )
    denied = await world.put(
        "priya", day + timedelta(days=7), status="denied", note="Peak week, sorry."
    )
    pending = await world.put("priya", day + timedelta(days=14))
    canceled = await world.put("priya", day + timedelta(days=21), status="canceled")

    items = {
        item["id"]: item
        for item in world.get(
            "/requests", **{"from": day.isoformat(), "to": (day + timedelta(days=30)).isoformat()}
        ).json()["items"]
    }

    row = items[str(approved)]
    assert row["person"] == {
        "id": str(world.person("priya")),
        "name": "Priya Raman",
        "title": "Visual Merchandiser",
    }
    assert (row["type"], row["status"], row["partialMinutes"]) == ("pto", "approved", 240)
    assert (row["amountMinutes"], row["amountLabel"]) == (240, "4 hours (half a day)")
    assert row["decidedBy"] == {"name": "Marcus Bell"}
    assert row["decidedAt"] is not None
    assert row["createdVia"] == "ui"
    assert row["createdAt"]
    assert row["canceledAt"] is None
    assert row["coverage"] is None
    assert row["availableAfterMinutes"] is None
    assert items[str(denied)]["decisionNote"] == "Peak week, sorry."
    assert items[str(pending)]["decidedBy"] is None
    assert items[str(pending)]["amountLabel"] == "8 hours (1 day)"
    assert items[str(canceled)]["canceledAt"] is not None


async def test_a_denials_note_is_shown_to_the_person_their_manager_and_hr(
    start: StartWorld,
) -> None:
    world = start("priya", now=far())
    day = world.today + timedelta(days=10)
    denied = await world.put("priya", day, status="denied", note="Not that week.")

    def note(persona: str) -> str | None:
        world.switch(persona)
        response = world.get(f"/requests/{denied}")
        assert response.status_code == 200, response.text
        return str(response.json()["decisionNote"])

    assert [note("priya"), note("marcus"), note("dana")] == ["Not that week."] * 3


# ---------------------------------------------------------------------------------------------
# One request


async def test_a_request_is_read_by_its_person_manager_skip_level_and_hr_and_by_no_one_else(
    start: StartWorld,
) -> None:
    world = start("priya", now=far())
    day = world.today + timedelta(days=10)
    priyas = await world.put("priya", day)
    associates = await world.put("oak-apparel-1", day)

    def status_of(persona: str, request_id: UUID) -> int:
        world.switch(persona)
        return int(world.get(f"/requests/{request_id}").status_code)

    assert status_of("priya", priyas) == 200
    assert status_of("marcus", priyas) == 200
    assert status_of("dana", priyas) == 200
    # Marcus is the skip-level manager of an apparel associate.
    assert status_of("marcus", associates) == 200
    assert status_of("mateo", priyas) == 404
    # Priya has no standing over the apparel team.
    assert status_of("priya", associates) == 404


async def test_a_request_the_caller_may_not_read_is_a_404_never_a_403(start: StartWorld) -> None:
    world = start("priya", now=far())
    leos = await world.put("leo", world.today + timedelta(days=10))
    other = start("priya")
    foreign = await other.put("priya", other.today + timedelta(days=10))

    hidden = problem_of(world.get(f"/requests/{leos}"), 404)
    missing = problem_of(world.get(f"/requests/{uuid4()}"), 404)
    elsewhere = problem_of(world.get(f"/requests/{foreign}"), 404)

    assert hidden["type"] == missing["type"] == elsewhere["type"] == "not-found"
    assert (
        hidden["detail"] == missing["detail"] == elsewhere["detail"] == REFUSAL_TEXTS["not-found"]
    )


# ---------------------------------------------------------------------------------------------
# Team coverage


# A Monday to Sunday week next year, in March: no company holiday, and wherever "today" is.
def coverage_week() -> date:
    return monday_on_or_after(date(datetime.now(UTC).year + 1, 3, 1))


async def coverage_world(start: StartWorld) -> tuple[World, UUID, date]:
    """Marcus, with Zara's pending request for the week's Monday to Sunday, and colleagues off."""
    world = start("marcus")
    week = coverage_week()
    await world.set_weekdays("oak-apparel-lead", MON_TO_FRI)
    zara = await world.put("oak-apparel-lead", week, week + timedelta(days=6))

    def day(n: int) -> date:
        return week + timedelta(days=n)

    # Priya, approved Tuesday and Wednesday: off on two of the days.
    await world.put("priya", day(1), day(2), status="approved", amount_minutes=960)
    # Leo, a recorded sick day on Friday.
    await world.put("leo", day(4), type="sick")
    # Not coverage: waiting, denied and canceled requests, a Saturday (not one of Zara's days), an
    # indirect report, the manager, and a person outside the team.
    await world.put("oak-home-lead", day(0))
    await world.put("oak-front-end", day(0), status="denied")
    await world.put("oak-front-end", day(1), status="canceled")
    await world.put("oak-front-end", day(5), status="approved")
    await world.put("oak-apparel-1", day(0), status="approved")
    await world.put("marcus", day(2), status="approved")
    await world.put("mateo", day(3), status="approved")
    return world, zara, week


async def test_coverage_lists_other_direct_reports_off_on_the_requests_days(
    start: StartWorld,
) -> None:
    world, zara, week = await coverage_world(start)
    expected = [
        {
            "person": {"id": str(world.person("leo")), "name": await world.name_of("leo")},
            "days": [
                {
                    "date": (week + timedelta(days=4)).isoformat(),
                    "type": "sick",
                    "partialMinutes": None,
                }
            ],
        },
        {
            "person": {"id": str(world.person("priya")), "name": "Priya Raman"},
            "days": [
                {
                    "date": (week + timedelta(days=1)).isoformat(),
                    "type": "pto",
                    "partialMinutes": None,
                },
                {
                    "date": (week + timedelta(days=2)).isoformat(),
                    "type": "pto",
                    "partialMinutes": None,
                },
            ],
        },
    ]

    detail = world.get(f"/requests/{zara}").json()
    waiting = [
        item
        for item in world.get("/requests", scope="waiting").json()["items"]
        if item["id"] == str(zara)
    ]

    assert detail["coverage"] == expected
    assert [item["coverage"] for item in waiting] == [expected]


async def test_a_waiting_request_does_not_count_as_time_off(start: StartWorld) -> None:
    world, zara, _week = await coverage_world(start)

    coverage = world.get(f"/requests/{zara}").json()["coverage"]

    # Home's waiting Monday and Front End's denied and canceled days aren't in it.
    names = {entry["person"]["name"] for entry in coverage}
    assert names == {"Priya Raman", await world.name_of("leo")}


async def test_a_colleague_with_both_kinds_of_time_off_is_one_entry_with_typed_days(
    start: StartWorld,
) -> None:
    world = start("marcus")
    week = coverage_week()
    await world.set_weekdays("oak-apparel-lead", MON_TO_FRI)
    zara = await world.put("oak-apparel-lead", week, week + timedelta(days=4))
    await world.put("priya", week + timedelta(days=3), type="sick")
    await world.put("priya", week + timedelta(days=1), status="approved")

    [entry] = world.get(f"/requests/{zara}").json()["coverage"]

    # Tuesday is PTO and Thursday is sick time: one line for Priya, in date order.
    assert entry["person"]["name"] == "Priya Raman"
    assert entry["days"] == [
        {"date": (week + timedelta(days=1)).isoformat(), "type": "pto", "partialMinutes": None},
        {"date": (week + timedelta(days=3)).isoformat(), "type": "sick", "partialMinutes": None},
    ]


async def test_people_who_are_not_the_managers_direct_reports_are_never_in_coverage(
    start: StartWorld,
) -> None:
    world = start("marcus")
    week = coverage_week()
    await world.set_weekdays("oak-apparel-lead", MON_TO_FRI)
    zara = await world.put("oak-apparel-lead", week, week + timedelta(days=4))
    # Off on every one of the days: Zara's own report (Marcus's skip-level), Marcus's manager's
    # other report on another team, and the HR partner.
    for key in ("oak-apparel-1", "mateo", "dana", "marcus"):
        await world.put(key, week, week + timedelta(days=4), status="approved")

    assert world.get(f"/requests/{zara}").json()["coverage"] == []


async def test_available_after_is_only_for_a_request_that_is_still_waiting(
    start: StartWorld,
) -> None:
    world = start("marcus", now=far())
    day = world.today + timedelta(days=10)
    waiting = await world.put("priya", day)
    closed = {
        status: await world.put("leo", day + timedelta(days=7 * n), status=status)
        for n, status in enumerate(("approved", "denied", "canceled"), start=1)
    }

    pending = world.get(f"/requests/{waiting}").json()
    assert pending["availableAfterMinutes"] is not None
    for status, request_id in closed.items():
        body = world.get(f"/requests/{request_id}").json()
        assert body["availableAfterMinutes"] is None, status
        assert body["availableAfterLabel"] is None, status
        # Coverage stays for the direct manager, whatever the status.
        assert body["coverage"] == [], status


async def test_a_holiday_is_not_one_of_the_requests_days(start: StartWorld) -> None:
    world = start("marcus")
    year = datetime.now(UTC).year + 1
    thanksgiving = next(
        h.holiday_date for h in holidays_for("oak", year) if h.name.startswith("Thanksgiving")
    )
    monday = thanksgiving - timedelta(days=3)
    await world.set_weekdays("oak-apparel-lead", MON_TO_FRI)
    zara = await world.put("oak-apparel-lead", monday, monday + timedelta(days=4))
    await world.put("priya", thanksgiving, status="approved")
    await world.put("leo", thanksgiving + timedelta(days=1), type="sick")

    coverage = world.get(f"/requests/{zara}").json()["coverage"]

    # Priya is off on Thanksgiving, which the company is closed for anyway: not one of Zara's days.
    assert [(entry["person"]["name"], entry["days"]) for entry in coverage] == [
        (
            await world.name_of("leo"),
            [
                {
                    "date": (thanksgiving + timedelta(days=1)).isoformat(),
                    "type": "sick",
                    "partialMinutes": None,
                }
            ],
        )
    ]


async def test_nobody_off_is_an_empty_list_and_the_seeded_request_has_no_coverage(
    start: StartWorld,
) -> None:
    world = start("marcus")
    zara = await seeded_zara_request(world)

    assert world.get(f"/requests/{zara}").json()["coverage"] == []
    [row] = world.get("/requests", scope="waiting").json()["items"]
    assert row["coverage"] == []


async def test_only_the_direct_manager_gets_coverage(start: StartWorld) -> None:
    world, zara, week = await coverage_world(start)
    associates = await world.put("oak-apparel-1", week + timedelta(days=14))

    skip_level = world.get(f"/requests/{associates}").json()
    assert skip_level["coverage"] is None
    assert skip_level["availableAfterMinutes"] is None
    world.switch("dana")
    for request_id in (zara, associates):
        body = world.get(f"/requests/{request_id}").json()
        assert body["coverage"] is None
        assert body["availableAfterMinutes"] is None
    world.switch("priya")
    own = world.get(f"/requests/{await world.put('priya', week + timedelta(days=21))}").json()
    assert (own["coverage"], own["availableAfterMinutes"]) == (None, None)
    # The team list carries none either.
    world.switch("marcus")
    for item in world.get(
        "/requests",
        scope="team",
        **{"from": week.isoformat(), "to": (week + timedelta(days=30)).isoformat()},
    ).json()["items"]:
        assert item["coverage"] is None


async def test_coverage_is_never_in_an_audit_event(start: StartWorld) -> None:
    world, zara, _week = await coverage_world(start)

    assert world.post(f"/requests/{zara}/decision", {"decision": "approve"}).status_code == 200

    [decided] = await world.timeoff_events()
    assert "coverage" not in json.dumps([decided.before, decided.after]).lower()


async def test_coverage_for_requests_of_one_person_shares_the_facts_queries(
    start: StartWorld,
) -> None:
    world = start("marcus")
    week = coverage_week()
    first = await world.put("oak-apparel-lead", week)
    second = await world.put("oak-apparel-lead", week + timedelta(days=7))
    third = await world.put("priya", week + timedelta(days=14))

    async def statements(ids: list[tuple[str, UUID, date]]) -> int:
        counted: list[str] = []

        def count(conn: Any, cursor: Any, statement: str, *rest: Any) -> None:
            counted.append(statement)

        async with tenant_session(
            world.engine, TenantContext(world.tenant_id, world.person("marcus"))
        ) as db:
            actor = await load_actor(db, world.tenant_id, world.person("marcus"))
            assert actor is not None
            event.listen(world.engine.sync_engine, "before_cursor_execute", count)
            try:
                await team_coverage(
                    db,
                    actor,
                    [CoverageRequest(rid, world.person(key), day, day) for key, rid, day in ids],
                )
            finally:
                event.remove(world.engine.sync_engine, "before_cursor_execute", count)
        return len(counted)

    one = await statements([("oak-apparel-lead", first, week)])
    same_person_twice = await statements(
        [("oak-apparel-lead", first, week), ("oak-apparel-lead", second, week + timedelta(days=7))]
    )
    two_people = await statements(
        [("oak-apparel-lead", first, week), ("priya", third, week + timedelta(days=14))]
    )

    assert same_person_twice == one
    assert two_people > one


async def test_a_waiting_queue_reads_each_requesters_facts_once(
    start: StartWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = start("marcus")
    week = coverage_week()
    await world.put("oak-apparel-lead", week)
    await world.put("oak-apparel-lead", week + timedelta(days=7))
    await world.put("priya", week + timedelta(days=14))
    loads: list[UUID] = []
    real = queries.load_facts

    async def counting(db: Any, tenant_id: UUID, person_id: UUID) -> Any:
        loads.append(person_id)
        return await real(db, tenant_id, person_id)

    monkeypatch.setattr(queries, "load_facts", counting)

    response = world.get("/requests", scope="waiting")

    assert response.status_code == 200, response.text
    # Zara's two requests (the seeded one is hers too) and Priya's: two people, one read each.
    assert len(loads) == len(set(loads)) == 2


async def test_one_request_is_read_once_per_get(
    start: StartWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = start("marcus")
    request_id = await world.put("priya", coverage_week())
    reads: list[UUID] = []
    real = queries.load_stored_request

    async def counting(db: Any, tenant_id: UUID, rid: UUID) -> Any:
        reads.append(rid)
        return await real(db, tenant_id, rid)

    monkeypatch.setattr(queries, "load_stored_request", counting)

    assert world.get(f"/requests/{request_id}").status_code == 200

    assert reads == [request_id]


# ---------------------------------------------------------------------------------------------
# Available after


async def test_a_direct_managers_view_carries_the_available_pto_as_it_stands(
    start: StartWorld,
) -> None:
    world = start("marcus")
    zara = await seeded_zara_request(world)
    balance = world.get("/balances", person=str(world.person("oak-apparel-lead"))).json()

    detail = world.get(f"/requests/{zara}").json()
    [row] = world.get("/requests", scope="waiting").json()["items"]

    available = balance["pto"]["availableMinutes"]
    for body in (detail, row):
        assert body["availableAfterMinutes"] == available
        assert body["availableAfterLabel"] == label(available)
    # The pending request is already counted against it, and approving changes nothing.
    assert balance["pto"]["pendingMinutes"] > 0
    assert world.post(f"/requests/{zara}/decision", {"decision": "approve"}).status_code == 200
    after = world.get("/balances", person=str(world.person("oak-apparel-lead"))).json()
    assert after["pto"]["availableMinutes"] == available


# ---------------------------------------------------------------------------------------------
# Deciding


async def test_the_direct_manager_approves_and_it_is_audited_via_the_ui(start: StartWorld) -> None:
    world = start("marcus")
    zara = await seeded_zara_request(world)

    response = world.post(f"/requests/{zara}/decision", {"decision": "approve"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["status"], body["decidedBy"], body["decisionNote"]) == (
        "approved",
        {"name": "Marcus Bell"},
        None,
    )
    assert body["decidedAt"] is not None
    [event_row] = await world.timeoff_events()
    assert (event_row.action, event_row.via, event_row.target_id, event_row.proposal_id) == (
        "timeoff.approved",
        "ui",
        zara,
        None,
    )
    assert event_row.actor_person_id == world.person("marcus")
    assert (event_row.before or {})["status"] == "pending"
    assert (event_row.after or {})["status"] == "approved"
    assert world.get("/summary").json()["waitingCount"] == 0


async def test_a_denial_keeps_its_note_for_the_person_and_never_in_the_log(
    start: StartWorld,
) -> None:
    world = start("marcus")
    zara = await seeded_zara_request(world)

    response = world.post(
        f"/requests/{zara}/decision", {"decision": "deny", "note": "  Busy week.  "}
    )

    assert response.status_code == 200
    assert (response.json()["status"], response.json()["decisionNote"]) == ("denied", "Busy week.")
    [event_row] = await world.timeoff_events()
    assert event_row.action == "timeoff.denied"
    assert "Busy week" not in json.dumps([event_row.before, event_row.after])


async def test_a_blank_note_on_a_denial_is_no_note(start: StartWorld) -> None:
    world = start("marcus")
    zara = await seeded_zara_request(world)

    response = world.post(f"/requests/{zara}/decision", {"decision": "deny", "note": "   "})

    assert response.json()["decisionNote"] is None


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({"decision": "approve", "note": "Enjoy"}, id="a note on an approval"),
        pytest.param({"decision": "deny", "note": "x" * 301}, id="a note over 300 characters"),
        pytest.param({"decision": "deny", "note": "a\x00b"}, id="a NUL in the note"),
        pytest.param({"decision": "maybe"}, id="an unknown decision"),
        pytest.param({}, id="no decision"),
    ],
)
async def test_a_bad_decision_body_is_a_422_and_changes_nothing(
    start: StartWorld, body: dict[str, object]
) -> None:
    world = start("marcus")
    zara = await seeded_zara_request(world)

    response = world.post(f"/requests/{zara}/decision", body)

    assert problem_of(response, 422)["errors"]
    assert await world.timeoff_events() == []
    assert world.get(f"/requests/{zara}").json()["status"] == "pending"


async def test_a_note_of_exactly_300_characters_is_kept(start: StartWorld) -> None:
    world = start("marcus")
    zara = await seeded_zara_request(world)

    response = world.post(f"/requests/{zara}/decision", {"decision": "deny", "note": "n" * 300})

    assert response.status_code == 200
    assert response.json()["decisionNote"] == "n" * 300


async def test_deciding_a_request_that_is_no_longer_pending_is_a_409_with_its_status(
    start: StartWorld,
) -> None:
    world = start("marcus")
    zara = await seeded_zara_request(world)
    assert world.post(f"/requests/{zara}/decision", {"decision": "approve"}).status_code == 200

    again = problem_of(world.post(f"/requests/{zara}/decision", {"decision": "deny"}), 409)

    assert again["type"] == "status-changed"
    assert again["currentStatus"] == "approved"
    assert again["detail"] == REFUSAL_TEXTS["status-changed"]
    assert again["status"] == 409


async def test_hr_and_a_skip_level_manager_cannot_decide_and_are_told_so_with_a_403(
    start: StartWorld,
) -> None:
    world = start("marcus", now=far())
    day = world.today + timedelta(days=10)
    associates = await world.put("oak-apparel-1", day)
    zara = await seeded_zara_request(world)

    skip_level = problem_of(
        world.post(f"/requests/{associates}/decision", {"decision": "approve"}), 403
    )
    world.switch("dana")
    hr = problem_of(world.post(f"/requests/{zara}/decision", {"decision": "approve"}), 403)

    for problem in (skip_level, hr):
        assert problem["type"] == "not-allowed"
        assert problem["detail"] == REFUSAL_TEXTS["not-allowed"]
    assert await world.timeoff_events() == []
    assert world.get(f"/requests/{zara}").json()["status"] == "pending"


async def test_a_person_cannot_decide_their_own_request_and_sick_time_is_not_decided(
    start: StartWorld,
) -> None:
    world = start("priya", now=far())
    day = world.today + timedelta(days=10)
    own = await world.put("priya", day)
    sick = await world.put("priya", day + timedelta(days=7), type="sick")

    mine = problem_of(world.post(f"/requests/{own}/decision", {"decision": "approve"}), 403)
    world.switch("marcus")
    recorded = problem_of(world.post(f"/requests/{sick}/decision", {"decision": "approve"}), 403)

    assert mine["type"] == recorded["type"] == "not-allowed"


async def test_deciding_a_request_that_cannot_be_read_is_a_404_never_a_403(
    start: StartWorld,
) -> None:
    world = start("mateo")
    zara = await seeded_zara_request(world)
    other = start("marcus")
    foreign = await seeded_zara_request(other)

    unreadable = problem_of(world.post(f"/requests/{zara}/decision", {"decision": "approve"}), 404)
    missing = problem_of(world.post(f"/requests/{uuid4()}/decision", {"decision": "approve"}), 404)
    elsewhere = problem_of(
        world.post(f"/requests/{foreign}/decision", {"decision": "approve"}), 404
    )

    assert unreadable["type"] == missing["type"] == elsewhere["type"] == "not-found"
    assert await world.timeoff_events() == []
    assert other.get(f"/requests/{foreign}").json()["status"] == "pending"


async def test_a_pending_request_can_be_approved_after_its_days_have_passed(
    start: StartWorld,
) -> None:
    world = start("marcus", now=far())
    past = world.today - timedelta(days=10)
    late = await world.put("priya", past, past + timedelta(days=1))

    response = world.post(f"/requests/{late}/decision", {"decision": "approve"})

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "approved"
    [event_row] = await world.timeoff_events()
    assert (event_row.action, event_row.target_id, event_row.via) == (
        "timeoff.approved",
        late,
        "ui",
    )


async def test_a_pending_request_can_be_denied_with_a_note_after_its_days_have_passed(
    start: StartWorld,
) -> None:
    world = start("marcus", now=far())
    past = world.today - timedelta(days=10)
    late = await world.put("priya", past)

    response = world.post(
        f"/requests/{late}/decision", {"decision": "deny", "note": "Too late to cover."}
    )

    assert response.status_code == 200, response.text
    assert (response.json()["status"], response.json()["decisionNote"]) == (
        "denied",
        "Too late to cover.",
    )
    [event_row] = await world.timeoff_events()
    assert event_row.action == "timeoff.denied"


# ---------------------------------------------------------------------------------------------
# Canceling


async def test_a_person_cancels_their_own_pending_request_and_it_is_audited(
    start: StartWorld,
) -> None:
    world = start("priya", now=far())
    pending = await world.put("priya", world.today + timedelta(days=10))

    response = world.post(f"/requests/{pending}/cancel")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "canceled"
    assert response.json()["canceledAt"] is not None
    [event_row] = await world.timeoff_events()
    assert (event_row.action, event_row.via, event_row.target_id) == (
        "timeoff.canceled",
        "ui",
        pending,
    )
    assert (event_row.before or {})["status"] == "pending"
    assert (event_row.after or {})["status"] == "canceled"


async def test_an_approved_request_cancels_before_its_first_day_and_not_on_it(
    start: StartWorld,
) -> None:
    world = start("priya", now=far())
    future = await world.put("priya", world.today + timedelta(days=1), status="approved")
    started = await world.put(
        "priya", world.today - timedelta(days=1), world.today, status="approved"
    )

    ok = world.post(f"/requests/{future}/cancel")
    late = problem_of(world.post(f"/requests/{started}/cancel"), 409)

    assert ok.status_code == 200
    assert late["type"] == "already-started"
    assert late["currentStatus"] == "approved"
    assert late["detail"] == REFUSAL_TEXTS["already-started"]


@pytest.mark.parametrize("status", ["denied", "canceled"])
async def test_a_closed_request_cannot_be_canceled(start: StartWorld, status: str) -> None:
    world = start("priya", now=far())
    closed = await world.put("priya", world.today + timedelta(days=10), status=status)

    problem = problem_of(world.post(f"/requests/{closed}/cancel"), 409)

    assert (problem["type"], problem["currentStatus"]) == ("status-changed", status)


async def test_a_manager_or_hr_cannot_cancel_a_persons_request_and_a_peer_gets_a_404(
    start: StartWorld,
) -> None:
    world = start("marcus", now=far())
    pending = await world.put("priya", world.today + timedelta(days=10))

    by_manager = problem_of(world.post(f"/requests/{pending}/cancel"), 403)
    world.switch("dana")
    by_hr = problem_of(world.post(f"/requests/{pending}/cancel"), 403)
    world.switch("mateo")
    by_peer = problem_of(world.post(f"/requests/{pending}/cancel"), 404)

    assert by_manager["type"] == by_hr["type"] == "not-allowed"
    assert by_peer["type"] == "not-found"
    assert await world.timeoff_events() == []
    world.switch("priya")
    assert world.get(f"/requests/{pending}").json()["status"] == "pending"


async def test_canceling_a_request_in_another_sandbox_is_a_404(start: StartWorld) -> None:
    world = start("priya")
    other = start("priya", now=far())
    foreign = await other.put("priya", other.today + timedelta(days=10))

    assert problem_of(world.post(f"/requests/{foreign}/cancel"), 404)["type"] == "not-found"
    assert other.get(f"/requests/{foreign}").json()["status"] == "pending"


# ---------------------------------------------------------------------------------------------
# Making a request


async def test_a_pto_request_is_pending_with_its_label_and_audit_event(start: StartWorld) -> None:
    world = start("priya")
    await world.fund("priya")
    day = world.workday(30)
    before = world.get("/summary").json()

    response = world.post(
        "/requests", {"type": "pto", "startDate": day.isoformat(), "endDate": day.isoformat()}
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["status"], body["type"], body["createdVia"]) == ("pending", "pto", "ui")
    assert (body["amountMinutes"], body["amountLabel"]) == (480, "8 hours (1 day)")
    assert body["person"]["name"] == "Priya Raman"
    assert body["decidedBy"] is None
    [event_row] = await world.timeoff_events()
    assert (event_row.action, event_row.via, event_row.actor_person_id) == (
        "timeoff.requested",
        "ui",
        world.person("priya"),
    )
    assert event_row.after == {
        "status": "pending",
        "type": "pto",
        "startDate": day.isoformat(),
        "endDate": day.isoformat(),
    }
    after = world.get("/summary").json()
    assert after["pendingCount"] == before["pendingCount"] + 1
    assert after["ptoAvailableMinutes"] == before["ptoAvailableMinutes"] - 480


async def test_a_sick_day_is_recorded_not_pending(start: StartWorld) -> None:
    world = start("priya")
    day = world.workday(40)

    response = world.post(
        "/requests",
        {
            "type": "sick",
            "startDate": day.isoformat(),
            "endDate": day.isoformat(),
            "partialMinutes": 180,
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["status"], body["amountMinutes"], body["amountLabel"]) == (
        "recorded",
        180,
        "3 hours",
    )
    assert body["partialMinutes"] == 180
    [event_row] = await world.timeoff_events()
    assert event_row.action == "timeoff.recorded"


async def test_a_half_day_is_four_hours(start: StartWorld) -> None:
    world = start("priya")
    await world.fund("priya")
    day = world.workday(30)

    response = world.post(
        "/requests",
        {
            "type": "pto",
            "startDate": day.isoformat(),
            "endDate": day.isoformat(),
            "partialMinutes": 240,
        },
    )

    assert response.json()["amountLabel"] == "4 hours (half a day)"


def last_workday_before_today(world: World) -> date:
    """The latest day before today that Priya works (Monday to Friday, not a closed day), so a
    request for it is out of range and nothing else, whatever weekday today is."""
    day = world.today - timedelta(days=1)
    while day.isoweekday() > 5 or day in {h.holiday_date for h in holidays_for("oak", day.year)}:
        day -= timedelta(days=1)
    return day


def refusal_cases(world: World) -> list[tuple[str, dict[str, Any]]]:
    saturday = world.workday(30) + timedelta(days=(6 - world.workday(30).weekday()) % 7 or 7)
    monday = world.workday(30)
    return [
        (
            "no-scheduled-days",
            {"type": "pto", "startDate": saturday.isoformat(), "endDate": saturday.isoformat()},
        ),
        (
            "too-long",
            {
                "type": "pto",
                "startDate": monday.isoformat(),
                "endDate": (monday + timedelta(days=31)).isoformat(),
            },
        ),
        (
            "out-of-range",
            {
                "type": "pto",
                "startDate": last_workday_before_today(world).isoformat(),
                "endDate": last_workday_before_today(world).isoformat(),
            },
        ),
        (
            "bad-partial",
            {
                "type": "pto",
                "startDate": monday.isoformat(),
                "endDate": monday.isoformat(),
                "partialMinutes": 120,
            },
        ),
        (
            # Thirty-one days of sick time is more than the 40 hours granted.
            "not-enough",
            {
                "type": "sick",
                "startDate": world.today.isoformat(),
                "endDate": (world.today + timedelta(days=30)).isoformat(),
            },
        ),
    ]


REFUSAL_CODES = ["no-scheduled-days", "too-long", "out-of-range", "bad-partial", "not-enough"]


@pytest.mark.parametrize("code", REFUSAL_CODES)
@pytest.mark.parametrize("day", range(7))
async def test_each_refusal_is_the_one_asked_for_whatever_weekday_today_is(
    start: StartWorld, code: str, day: int
) -> None:
    # Seven consecutive days hold the clock on every weekday. A date that is out of range but not a
    # workday would be refused as "no-scheduled-days" first.
    world = start("priya", now=far() + timedelta(days=day))
    await world.fund("priya")

    response = world.post("/requests", dict(refusal_cases(world))[code])

    assert problem_of(response, 422)["type"] == code


@pytest.mark.parametrize("code", REFUSAL_CODES)
@pytest.mark.parametrize("route", ["/requests", "/check"])
async def test_every_engine_refusal_is_a_422_with_its_code_and_text_and_writes_nothing(
    start: StartWorld, code: str, route: str
) -> None:
    world = start("priya")
    await world.fund("priya")
    body = dict(refusal_cases(world))[code]

    response = world.post(route, body)

    if route == "/check":
        # A preview answers 200 with the problem in it.
        assert response.status_code == 200, response.text
        assert code in [problem["code"] for problem in response.json()["problems"]]
        assert {"code": code, "text": REFUSAL_TEXTS[code]} in response.json()["problems"]
        assert response.json()["ok"] is False
    else:
        problem = problem_of(response, 422)
        assert problem["type"] == code
        assert problem["detail"] == REFUSAL_TEXTS[code]
    assert await world.timeoff_events() == []
    assert [
        i
        for i in world.get("/requests", scope="mine").json()["items"]
        if i["status"] == "recorded" and i["startDate"] == body["startDate"]
    ] == []


async def test_a_request_over_days_already_booked_is_refused_as_overlaps(start: StartWorld) -> None:
    world = start("priya")
    await world.fund("priya")
    day = world.workday(30)
    payload = {"type": "pto", "startDate": day.isoformat(), "endDate": day.isoformat()}
    assert world.post("/requests", payload).status_code == 201

    problem = problem_of(world.post("/requests", payload), 422)

    assert problem["type"] == "overlaps"
    assert problem["detail"] == REFUSAL_TEXTS["overlaps"]
    assert len(await world.timeoff_events()) == 1


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(
            {"type": "pto", "startDate": "2030-01-08", "endDate": "2030-01-07"}, id="ends first"
        ),
        pytest.param(
            {"type": "vacation", "startDate": "2030-01-07", "endDate": "2030-01-07"}, id="type"
        ),
        pytest.param({"type": "pto", "startDate": "2030-01-07"}, id="no end"),
        pytest.param({"type": "pto", "startDate": "soon", "endDate": "2030-01-07"}, id="a date"),
        pytest.param(
            {
                "type": "pto",
                "startDate": "2030-01-07",
                "endDate": "2030-01-07",
                "partialMinutes": "half",
            },
            id="a partial",
        ),
    ],
)
@pytest.mark.parametrize("route", ["/requests", "/check"])
async def test_a_malformed_request_is_a_422_from_the_schema(
    start: StartWorld, route: str, body: dict[str, object]
) -> None:
    world = start("priya")

    problem = problem_of(world.post(route, body), 422)

    assert problem["errors"]
    assert await world.timeoff_events() == []


async def test_pto_for_someone_with_no_manager_is_refused_as_no_approver(
    start: StartWorld,
) -> None:
    world = start("priya")
    await world.fund("priya")
    await world.clear_manager("priya")
    day = world.workday(30)
    body = {"type": "pto", "startDate": day.isoformat(), "endDate": day.isoformat()}

    problem = problem_of(world.post("/requests", body), 422)

    assert problem["type"] == "no-approver"
    assert problem["detail"] == REFUSAL_TEXTS["no-approver"]
    assert await world.timeoff_events() == []
    assert world.get("/summary").json()["pendingCount"] == 0


async def test_the_check_names_no_approver_before_the_form_is_sent(start: StartWorld) -> None:
    world = start("priya")
    await world.fund("priya")
    await world.clear_manager("priya")
    day = world.workday(30)

    body = world.post(
        "/check", {"type": "pto", "startDate": day.isoformat(), "endDate": day.isoformat()}
    ).json()

    assert body["ok"] is False
    assert body["problems"] == [{"code": "no-approver", "text": REFUSAL_TEXTS["no-approver"]}]
    assert body["amountMinutes"] == 480


async def test_an_engine_problem_comes_before_no_approver(start: StartWorld) -> None:
    world = start("priya")
    await world.clear_manager("priya")
    saturday = world.workday(30) + timedelta(days=1)
    while saturday.isoweekday() != 6:
        saturday += timedelta(days=1)
    body = {"type": "pto", "startDate": saturday.isoformat(), "endDate": saturday.isoformat()}

    refused = problem_of(world.post("/requests", body), 422)
    checked = world.post("/check", body).json()

    assert refused["type"] == "no-scheduled-days"
    assert [p["code"] for p in checked["problems"]] == ["no-scheduled-days", "no-approver"]


async def test_sick_time_for_someone_with_no_manager_is_recorded(start: StartWorld) -> None:
    world = start("priya")
    await world.clear_manager("priya")
    day = world.workday(40)
    body = {"type": "sick", "startDate": day.isoformat(), "endDate": day.isoformat()}

    assert world.post("/check", body).json()["ok"] is True
    response = world.post("/requests", body)

    assert response.status_code == 201, response.text
    assert response.json()["status"] == "recorded"


# ---------------------------------------------------------------------------------------------
# The check


async def test_a_check_gives_the_engines_answer_with_labels_draws_and_rules(
    start: StartWorld,
) -> None:
    world = start("priya")
    await world.fund("priya")
    monday = monday_on_or_after(world.today + timedelta(days=30))
    # Hold the week clear of company holidays by looking one up.
    holidays = oakland_holidays(monday.year, monday.year + 1)
    while any(monday + timedelta(days=n) in holidays for n in range(5)):
        monday += timedelta(days=7)
    balance = world.get("/balances").json()["pto"]["availableMinutes"]

    response = world.post(
        "/check",
        {
            "type": "pto",
            "startDate": monday.isoformat(),
            "endDate": (monday + timedelta(days=4)).isoformat(),
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True
    assert body["problems"] == []
    assert body["countedDays"] == [(monday + timedelta(days=n)).isoformat() for n in range(5)]
    assert body["skippedDays"] == []
    assert body["overlappingDays"] == []
    assert (body["amountMinutes"], body["amountLabel"]) == (2400, "40 hours (5 days)")
    [draw] = body["draws"]
    assert draw == {
        "year": None,
        "amountMinutes": 2400,
        "amountLabel": "40 hours (5 days)",
        "availableBeforeMinutes": balance,
        "availableBeforeLabel": label(balance),
        "availableAfterMinutes": balance - 2400,
        "availableAfterLabel": label(balance - 2400),
    }
    assert {rule["rule"] for rule in body["rules"]} >= {"scheduled-days", "pto-available"}
    for rule in body["rules"]:
        assert set(rule) == {"sectionId", "rule", "title", "deepLink"}
    # Nothing was written.
    assert await world.timeoff_events() == []
    assert (
        world.get("/requests", **{"from": monday.isoformat(), "to": monday.isoformat()}).json()[
            "items"
        ]
        == []
    )


async def test_a_check_over_a_weekend_lists_the_skipped_days_with_their_reasons(
    start: StartWorld,
) -> None:
    world = start("priya")
    monday = monday_on_or_after(world.today + timedelta(days=30))
    saturday = monday + timedelta(days=5)

    body = world.post(
        "/check",
        {
            "type": "pto",
            "startDate": saturday.isoformat(),
            "endDate": (saturday + timedelta(days=1)).isoformat(),
        },
    ).json()

    assert body["ok"] is False
    assert [p["code"] for p in body["problems"]] == ["no-scheduled-days"]
    assert body["skippedDays"] == [
        {"day": saturday.isoformat(), "reason": "not scheduled"},
        {"day": (saturday + timedelta(days=1)).isoformat(), "reason": "not scheduled"},
    ]
    assert (body["countedDays"], body["amountMinutes"], body["amountLabel"], body["draws"]) == (
        [],
        None,
        None,
        [],
    )


async def test_a_check_names_the_days_other_requests_already_cover(start: StartWorld) -> None:
    world = start("priya", now=far())
    monday = monday_on_or_after(world.today + timedelta(days=30))
    await world.put("priya", monday, monday + timedelta(days=2), status="approved")
    await world.put("priya", monday + timedelta(days=4), type="sick")

    body = world.post(
        "/check",
        {
            "type": "pto",
            "startDate": (monday + timedelta(days=1)).isoformat(),
            "endDate": (monday + timedelta(days=6)).isoformat(),
        },
    ).json()

    # Tuesday and Wednesday are in the approved request, Friday is a recorded sick day. Thursday,
    # Saturday, and Sunday are free.
    assert body["overlappingDays"] == [(monday + timedelta(days=n)).isoformat() for n in (1, 2, 4)]
    assert "overlaps" in [p["code"] for p in body["problems"]]


async def test_a_sick_check_across_new_year_has_one_draw_per_year(start: StartWorld) -> None:
    world = start("priya")
    year = world.today.year
    body = world.post(
        "/check",
        {"type": "sick", "startDate": f"{year}-12-28", "endDate": f"{year + 1}-01-08"},
    ).json()

    assert [draw["year"] for draw in body["draws"]] == [year, year + 1]
    for draw in body["draws"]:
        assert draw["availableAfterLabel"] == label(draw["availableAfterMinutes"])


async def test_short_notice_is_a_warning_not_a_problem(start: StartWorld) -> None:
    world = start("priya")
    await world.fund("priya")
    monday = monday_on_or_after(world.today + timedelta(days=2))
    holidays = oakland_holidays(monday.year, monday.year + 1)
    while any(monday + timedelta(days=n) in holidays for n in range(4)):
        monday += timedelta(days=7)

    body = world.post(
        "/check",
        {
            "type": "pto",
            "startDate": monday.isoformat(),
            "endDate": (monday + timedelta(days=3)).isoformat(),
        },
    ).json()

    assert body["warnings"] == ["short-notice"]
    assert body["problems"] == []


def test_a_check_to_the_end_of_time_is_answered_at_once(start: StartWorld) -> None:
    world = start("priya")

    response = world.post(
        "/check", {"type": "pto", "startDate": "2030-01-07", "endDate": "9999-12-31"}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert [p["code"] for p in body["problems"]][:2] == ["too-long", "out-of-range"]
    assert body["overlappingDays"] == []


# ---------------------------------------------------------------------------------------------
# The calendar


def test_the_calendar_gives_weekdays_holidays_across_new_year_and_the_earliest_days(
    start: StartWorld,
) -> None:
    world = start("priya")
    year = world.today.year
    holidays = oakland_holidays(year, year + 1)
    first, last = date(year, 12, 20), date(year + 1, 1, 5)
    expected = [
        {"day": day.isoformat(), "name": name}
        for day, name in sorted(holidays.items())
        if first <= day <= last
    ]

    response = world.get("/calendar", **{"from": first.isoformat(), "to": last.isoformat()})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["scheduledWeekdays"] == MON_TO_FRI
    assert body["holidays"] == expected
    names = [holiday["name"] for holiday in body["holidays"]]
    assert any(name.startswith("Christmas Day") for name in names)
    assert any(name.startswith("New Year's Day") for name in names)
    years = {holiday["day"][:4] for holiday in body["holidays"]}
    assert years >= {str(year)}
    # PTO starts today, sick time reaches 30 days back, and neither reaches past next December.
    assert body["earliestStart"] == {
        "pto": world.today.isoformat(),
        "sick": (world.today - timedelta(days=30)).isoformat(),
    }
    assert body["latestEnd"] == f"{year + 1}-12-31"


def test_the_calendar_follows_the_held_clock_and_the_locations_today(start: StartWorld) -> None:
    moment = datetime(datetime.now(UTC).year + 1, 1, 2, 3, 0, tzinfo=UTC)
    world = start("priya", now=moment)

    body = world.get("/calendar", **{"from": "2030-01-01", "to": "2030-01-02"}).json()

    # 03:00 UTC on January 2 is still January 1 in Oakland, so the latest end is a year on.
    assert body["earliestStart"]["pto"] == f"{moment.year}-01-01"
    assert body["earliestStart"]["sick"] == f"{moment.year - 1}-12-02"
    assert body["latestEnd"] == f"{moment.year + 1}-12-31"


@pytest.mark.parametrize(
    "params",
    [
        pytest.param({"from": "2030-02-01", "to": "2030-01-01"}, id="backwards"),
        pytest.param({"from": "2030-02-01"}, id="no end"),
        pytest.param({}, id="neither"),
    ],
)
def test_a_bad_calendar_window_is_a_422(start: StartWorld, params: dict[str, str]) -> None:
    assert problem_of(start("priya").get("/calendar", **params), 422)["status"] == 422


# ---------------------------------------------------------------------------------------------
# The summary


async def test_an_employees_summary_has_pto_pending_approver_and_no_waiting_count(
    start: StartWorld,
) -> None:
    world = start("priya")
    available = world.get("/balances").json()["pto"]["availableMinutes"]

    body = world.get("/summary").json()

    assert body == {
        "ptoAvailableMinutes": available,
        "ptoAvailableLabel": label(available),
        "pendingCount": 0,
        "approver": {"name": "Marcus Bell"},
        "waitingCount": None,
    }


async def test_a_managers_summary_counts_what_waits_for_them(start: StartWorld) -> None:
    world = start("marcus", now=far())
    today = world.today
    # Zara's seeded request waits. Another from a direct report, and some that don't count.
    await world.put("priya", today + timedelta(days=10))
    await world.put("oak-apparel-1", today + timedelta(days=10))
    await world.put("oak-home-lead", today + timedelta(days=10), status="approved")
    await world.put("marcus", today + timedelta(days=10))

    body = world.get("/summary").json()

    assert body["waitingCount"] == 2
    # Marcus's own request is his pending count, not his waiting count.
    assert body["pendingCount"] == 1
    assert body["approver"] is not None


async def test_someone_with_no_manager_has_no_approver(
    start: StartWorld, make_tenant: MakeTenant, app_engine: AsyncEngine
) -> None:
    world = start("priya")
    tenant = await make_tenant()
    async with tenant_session(app_engine, TenantContext(tenant.id, None)) as db:
        tokens = await start_session(db, tenant.id, tenant.hr_id)
    world.browser.client.cookies.clear()
    world.browser.client.cookies.set(SESSION_COOKIE, tokens.session)
    world.browser.client.cookies.set(CSRF_COOKIE, tokens.csrf)

    body = world.get("/summary").json()

    # Dana has no manager, and the sample company's one pending request (her report Priya's) waits
    # for her.
    assert body["approver"] is None
    assert body["waitingCount"] == 1


# ---------------------------------------------------------------------------------------------
# Logging


async def test_a_not_allowed_decision_is_logged_as_a_denied_authorization(
    start: StartWorld, caplog: pytest.LogCaptureFixture
) -> None:
    world = start("dana")
    zara = await seeded_zara_request(world)

    with caplog.at_level(logging.WARNING, logger="app.security"):
        assert world.post(f"/requests/{zara}/decision", {"decision": "approve"}).status_code == 403

    [record] = [r for r in caplog.records if r.name == "app.security"]
    assert record.getMessage() == "security.authz_denied"
    assert record.__dict__["fields"]["reason"] == "timeoff.decide"
