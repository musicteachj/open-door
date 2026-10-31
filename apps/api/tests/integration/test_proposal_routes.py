"""Confirm and Dismiss over HTTP: the two routes a person's click reaches.

Each test starts a real sandbox (the 145-person seed) as a persona and gives them a conversation
with a proposal, made by the card builders and the proposal service (no model is involved). Priya
Raman works in Oakland and reports to Marcus Bell, who decides her PTO. A proposal is the person's
own: another persona's, a missing one, and one from before a persona switch are all a 404.

The proposal's clock is the database's, so a test that needs an expired one ages the row through
the owner. A 409 that wrote something (an expiry, a turn that never finished) must commit, so those
tests read the row back from the database to see that it stayed.
"""

import asyncio
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.ai.fixed_texts import STILL_ANSWERING_TEXT
from app.domain.timeoff.evaluate import NewRequest
from app.modules.assistant.routes import PROPOSAL_CONFLICT_TEXTS
from app.modules.timeoff.texts import refusal_text
from tests.integration.conftest import Browser, OpenBrowser, audit_events, turn_row
from tests.integration.test_proposals import (
    Chat,
    age,
    end_turn,
    make_chat,
    propose_cancel,
    propose_decision,
    propose_request,
    row_of,
)
from tests.integration.test_timeoff_routes import (
    StartWorld,
    World,
    problem_of,
)

pytestmark = pytest.mark.integration

BASE = "/api/v1/assistant/proposals"
PROPOSAL_KEYS = {
    "id",
    "action",
    "status",
    "canceledReason",
    "expiresAt",
    "card",
    "failure",
    "turnRunning",
    "deniedNote",
}


@pytest.fixture
def start(
    open_browser: OpenBrowser, app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> StartWorld:
    """Start a sandbox as a persona, with a World to drive it (the time-off tests' own)."""

    def begin(persona: str = "priya", *, now: datetime | None = None) -> World:
        browser = open_browser()
        sandbox = browser.start_sandbox(persona)
        return World(browser, sandbox, app_engine, owner_engine, now or datetime.now(UTC))

    return begin


def confirm_path(proposal_id: UUID) -> str:
    return f"{BASE}/{proposal_id}/confirm"


def cancel_path(proposal_id: UUID) -> str:
    return f"{BASE}/{proposal_id}/cancel"


def post(world: World, path: str, body: object = None) -> Any:
    return world.browser.client.post(path, json=body, headers=world.browser.csrf)


def pto(start_day: date, end_day: date | None = None) -> NewRequest:
    return NewRequest("pto", start_day, end_day or start_day, None)


async def book(
    world: World,
    day: date | None = None,
    end: date | None = None,
    *,
    persona: str = "priya",
    **chat_options: Any,
) -> UUID:
    """A pending request card for the persona, on `day` (a month out by default)."""
    person = world.person(persona)
    chat = await make_chat(world.engine, world.tenant_id, person, owner=world.owner, **chat_options)
    return await propose_request(
        world.engine, world.tenant_id, person, chat, pto(day or world.workday(30), end), world.now
    )


async def chat_for(world: World, persona: str, **options: Any) -> Chat:
    return await make_chat(world.engine, world.tenant_id, world.person(persona), **options)


async def requests_for(world: World, persona: str) -> list[Any]:
    from sqlalchemy import select

    from app.db.models import TimeOffRequest
    from app.db.tenancy import TenantContext, tenant_session

    async with tenant_session(world.engine, TenantContext(world.tenant_id, None)) as session:
        query = select(TimeOffRequest).where(TimeOffRequest.person_id == world.person(persona))
        return list((await session.execute(query)).scalars())


async def events_named(world: World, prefix: str) -> list[Any]:
    return [
        e for e in await audit_events(world.engine, world.tenant_id) if e.action.startswith(prefix)
    ]


async def proposal_status(world: World, proposal_id: UUID) -> str:
    return str((await row_of(world.owner, proposal_id))["status"])


# ---------------------------------------------------------------------------------------------
# The session and CSRF

BOTH = ["confirm", "cancel"]


def path_for(kind: str, proposal_id: UUID) -> str:
    return confirm_path(proposal_id) if kind == "confirm" else cancel_path(proposal_id)


@pytest.mark.parametrize("kind", BOTH)
def test_a_route_needs_a_session(browser: Browser, kind: str) -> None:
    response = browser.client.post(
        path_for(kind, uuid4()), headers={"Sec-Fetch-Site": "same-origin"}
    )

    assert problem_of(response, 401)["title"] == "Unauthorized"


@pytest.mark.parametrize("kind", BOTH)
async def test_a_write_without_the_csrf_header_is_forbidden_and_changes_nothing(
    start: StartWorld, kind: str
) -> None:
    world = start("priya")
    await world.fund("priya")
    proposal_id = await book(world)

    response = world.browser.client.post(path_for(kind, proposal_id))

    assert problem_of(response, 403)["detail"] == "The CSRF token is missing or wrong."
    assert await proposal_status(world, proposal_id) == "pending"
    assert all(r.proposal_id != proposal_id for r in await requests_for(world, "priya"))


# ---------------------------------------------------------------------------------------------
# Confirm


async def test_confirming_a_booking_card_books_it_and_returns_the_proposal_as_it_now_stands(
    start: StartWorld,
) -> None:
    world = start("priya")
    await world.fund("priya")
    day = world.workday(30)
    before = len(await requests_for(world, "priya"))
    proposal_id = await book(world, day)

    response = post(world, confirm_path(proposal_id))

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == PROPOSAL_KEYS
    assert body["turnRunning"] is False
    assert (body["id"], body["action"], body["status"]) == (
        str(proposal_id),
        "timeoff.request",
        "executed",
    )
    assert (body["canceledReason"], body["failure"]) == (None, None)
    assert body["card"]["startDate"] == day.isoformat()
    assert (body["card"]["amountMinutes"], body["card"]["amountLabel"]) == (
        480,
        "8 hours (1 day)",
    )
    assert body["card"]["approver"] == {"name": "Marcus Bell"}
    made = [r for r in await requests_for(world, "priya") if r.proposal_id == proposal_id]
    [request] = made
    assert (request.status, request.created_via, request.start_date) == (
        "pending",
        "assistant",
        day,
    )
    assert len(await requests_for(world, "priya")) == before + 1
    # The action's event says the assistant made it; the confirm is the person's own click.
    events = {e.action: e for e in await events_named(world, "timeoff.")}
    assert (events["timeoff.requested"].via, events["timeoff.requested"].proposal_id) == (
        "assistant",
        proposal_id,
    )
    confirmed = (await events_named(world, "proposal.confirmed"))[0]
    assert (confirmed.via, confirmed.proposal_id, confirmed.actor_person_id) == (
        "ui",
        proposal_id,
        world.person("priya"),
    )


async def test_a_card_whose_balance_changed_fails_not_enough_with_its_text_and_books_nothing(
    start: StartWorld,
) -> None:
    world = start("priya")
    # 40,000 minutes: far more than four weeks of PTO plus whatever her seeded history has taken.
    # The seed draws that history at random over the days before the sandbox's start, so a
    # smaller opening fits on some days and not on others.
    await world.fund("priya", 40_000)
    # About twenty working days, four weeks from the first Monday a month out: more than she has
    # once the opening drops to nothing (a whole year of month-ends earns 7,200).
    monday = world.workday(30) + timedelta(days=(7 - world.workday(30).weekday()) % 7)
    proposal_id = await book(world, monday, monday + timedelta(days=27))
    # Afterward her opening balance drops to nothing, so the card no longer fits.
    await world.fund("priya", 0)
    before = len(await requests_for(world, "priya"))

    response = post(world, confirm_path(proposal_id))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "failed"
    assert body["failure"] == {
        "code": "not-enough",
        "text": refusal_text("not-enough"),
        "dates": None,
    }
    assert body["card"]["amountMinutes"] > 4800
    assert len(await requests_for(world, "priya")) == before
    failed = await events_named(world, "proposal.failed")
    assert [(e.via, e.proposal_id) for e in failed] == [("ui", proposal_id)]
    assert await events_named(world, "timeoff.requested") == []


async def test_a_failure_for_overlapping_days_carries_the_dates(start: StartWorld) -> None:
    world = start("priya")
    await world.fund("priya")
    day = world.workday(30)
    proposal_id = await book(world, day)
    await world.put("priya", day, status="approved")

    response = post(world, confirm_path(proposal_id))

    assert response.status_code == 200, response.text
    failure = response.json()["failure"]
    assert (failure["code"], failure["text"], failure["dates"]) == (
        "overlaps",
        refusal_text("overlaps"),
        [day.isoformat()],
    )


async def test_confirming_a_decision_decides_as_the_manager_and_keeps_the_note_on_the_request_only(
    start: StartWorld,
) -> None:
    world = start("marcus")
    day = world.workday(30)
    request_id = await world.put("priya", day)
    chat = await chat_for(world, "marcus")
    proposal_id = await propose_decision(
        world.engine, world.tenant_id, world.person("marcus"), chat, request_id, "deny", world.now
    )
    note = "Two of the team are out that week, sorry."

    response = post(world, confirm_path(proposal_id), {"note": f"  {note}  "})

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "executed"
    [request] = [r for r in await requests_for(world, "priya") if r.id == request_id]
    assert (request.status, request.decided_by, request.decision_note) == (
        "denied",
        world.person("marcus"),
        note,
    )
    row = await row_of(world.owner, proposal_id)
    everything = json.dumps(
        [row["payload"], row["card"], row["outcome"], response.json()]
        + [[e.before, e.after] for e in await audit_events(world.engine, world.tenant_id)]
    )
    assert note not in everything
    denied = (await events_named(world, "timeoff.denied"))[0]
    assert (denied.via, denied.proposal_id, denied.actor_person_id) == (
        "assistant",
        proposal_id,
        world.person("marcus"),
    )


async def test_confirming_a_cancel_card_cancels_the_request(start: StartWorld) -> None:
    world = start("priya")
    day = world.workday(30)
    request_id = await world.put("priya", day, status="approved")
    chat = await chat_for(world, "priya")
    proposal_id = await propose_cancel(
        world.engine, world.tenant_id, world.person("priya"), chat, request_id, world.now
    )

    response = post(world, confirm_path(proposal_id))

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["status"], body["card"]["returnsMinutes"]) == ("executed", 480)
    [request] = [r for r in await requests_for(world, "priya") if r.id == request_id]
    assert request.status == "canceled"


@pytest.mark.parametrize(
    "note",
    ["x" * 301, "a\u0000b"],
    ids=["over 300 characters", "NUL"],
)
async def test_a_note_that_cannot_be_stored_is_a_422_and_changes_nothing(
    start: StartWorld, note: str
) -> None:
    world = start("marcus")
    request_id = await world.put("priya", world.workday(30))
    chat = await chat_for(world, "marcus")
    proposal_id = await propose_decision(
        world.engine, world.tenant_id, world.person("marcus"), chat, request_id, "deny", world.now
    )

    response = post(world, confirm_path(proposal_id), {"note": note})

    assert problem_of(response, 422)["title"] == "Unprocessable Content"
    assert await proposal_status(world, proposal_id) == "pending"


async def test_a_note_on_anything_but_a_denial_is_a_422_and_changes_nothing(
    start: StartWorld,
) -> None:
    world = start("priya")
    await world.fund("priya")
    proposal_id = await book(world)

    response = post(world, confirm_path(proposal_id), {"note": "Please approve"})

    assert problem_of(response, 422)["detail"] == "Only a denial takes a note."
    assert await proposal_status(world, proposal_id) == "pending"


@pytest.mark.parametrize(
    "body",
    [
        {"personId": str(uuid4())},
        {"payload": {"type": "pto"}},
        {"note": None, "decision": "approve"},
    ],
    ids=["a person", "a payload", "a decision"],
)
async def test_the_only_thing_a_confirm_takes_from_the_client_is_the_note(
    start: StartWorld, body: dict[str, Any]
) -> None:
    world = start("priya")
    await world.fund("priya")
    proposal_id = await book(world)

    response = post(world, confirm_path(proposal_id), body)

    assert response.status_code == 422, response.text
    assert await proposal_status(world, proposal_id) == "pending"


# ---------------------------------------------------------------------------------------------
# Whose it is


async def test_another_persons_proposal_is_a_404_that_looks_like_a_missing_one(
    start: StartWorld,
) -> None:
    world = start("priya")
    await world.fund("priya")
    proposal_id = await book(world)
    world.switch("marcus")

    for path in (confirm_path(proposal_id), cancel_path(proposal_id)):
        other = problem_of(post(world, path), 404)
        missing = problem_of(post(world, path.replace(str(proposal_id), str(uuid4()))), 404)
        assert other["detail"] == missing["detail"]
        assert other["title"] == missing["title"] == "Not Found"
    assert await proposal_status(world, proposal_id) == "pending"


async def test_after_a_persona_switch_the_old_personas_proposal_is_a_404_for_the_new_one(
    start: StartWorld,
) -> None:
    world = start("priya")
    await world.fund("priya")
    proposal_id = await book(world)
    for persona in ("dana", "mateo"):
        world.switch(persona)
        assert post(world, confirm_path(proposal_id)).status_code == 404
        assert post(world, cancel_path(proposal_id)).status_code == 404
    world.switch("priya")

    assert post(world, confirm_path(proposal_id)).status_code == 200


# ---------------------------------------------------------------------------------------------
# 409: not pending, not yet, never


def expected_conflict(status: str) -> dict[str, str]:
    return {"type": status, "currentStatus": status, "detail": PROPOSAL_CONFLICT_TEXTS[status]}


async def a_proposal_that(world: World, ended: str) -> UUID:
    """A proposal for Priya that has ended the way `ended` says."""
    proposal_id = await book(world)
    if ended == "executed":
        assert post(world, confirm_path(proposal_id)).status_code == 200
    elif ended == "canceled":
        assert post(world, cancel_path(proposal_id)).status_code == 200
    elif ended == "failed":
        await world.put("priya", world.workday(30), status="approved")
        assert post(world, confirm_path(proposal_id)).json()["status"] == "failed"
    else:
        assert ended == "expired"
        await age(world.owner, proposal_id, timedelta(minutes=16))
        assert post(world, confirm_path(proposal_id)).status_code == 409
    return proposal_id


@pytest.mark.parametrize("ended", ["executed", "canceled", "failed", "expired"])
@pytest.mark.parametrize("kind", BOTH)
async def test_a_proposal_that_ended_is_a_409_with_the_status_it_has(
    start: StartWorld, ended: str, kind: str
) -> None:
    world = start("priya")
    await world.fund("priya")
    proposal_id = await a_proposal_that(world, ended)
    requests = len(await requests_for(world, "priya"))
    ended_events = len(await events_named(world, "proposal."))

    response = post(world, path_for(kind, proposal_id))

    body = problem_of(response, 409)
    assert {key: body[key] for key in ("type", "currentStatus", "detail")} == expected_conflict(
        ended
    )
    assert await proposal_status(world, proposal_id) == ended
    assert len(await requests_for(world, "priya")) == requests
    assert len(await events_named(world, "proposal.")) == ended_events


async def test_a_confirm_after_the_expiry_is_a_409_and_the_expiry_stays_written(
    start: StartWorld,
) -> None:
    world = start("priya")
    await world.fund("priya")
    proposal_id = await book(world)
    await age(world.owner, proposal_id, timedelta(minutes=16))

    response = post(world, confirm_path(proposal_id))

    assert problem_of(response, 409)["type"] == "expired"
    row = await row_of(world.owner, proposal_id)
    # The route answered 409 and still committed: the proposal is expired in the database.
    assert (row["status"], row["no_outcome"], row["ended_at"] is not None) == (
        "expired",
        True,
        True,
    )
    assert all(r.proposal_id != proposal_id for r in await requests_for(world, "priya"))


async def test_a_dismiss_after_the_expiry_is_a_409_and_the_expiry_stays_written(
    start: StartWorld,
) -> None:
    world = start("priya")
    await world.fund("priya")
    proposal_id = await book(world)
    await age(world.owner, proposal_id, timedelta(minutes=16))

    response = post(world, cancel_path(proposal_id))

    assert problem_of(response, 409)["type"] == "expired"
    assert await proposal_status(world, proposal_id) == "expired"


async def test_a_confirm_while_its_turn_is_running_is_a_409_turn_running_and_writes_nothing(
    start: StartWorld,
) -> None:
    world = start("priya")
    await world.fund("priya")
    proposal_id = await book(world, turn_status="running")
    events_before = len(await events_named(world, "proposal."))

    response = post(world, confirm_path(proposal_id))

    body = problem_of(response, 409)
    assert (body["type"], body["detail"], body["currentStatus"]) == (
        "turn-running",
        STILL_ANSWERING_TEXT,
        "pending",
    )
    assert await proposal_status(world, proposal_id) == "pending"
    assert len(await events_named(world, "proposal.")) == events_before
    assert all(r.proposal_id != proposal_id for r in await requests_for(world, "priya"))


async def test_a_confirm_for_an_abandoned_turn_is_a_409_and_the_cancellation_stays_written(
    start: StartWorld,
) -> None:
    world = start("priya")
    await world.fund("priya")
    proposal_id = await book(world, turn_status="running", started_ago=timedelta(minutes=11))

    response = post(world, confirm_path(proposal_id))

    body = problem_of(response, 409)
    assert (body["type"], body["currentStatus"]) == ("turn-incomplete", "canceled")
    assert body["detail"] == PROPOSAL_CONFLICT_TEXTS["turn-incomplete"]
    row = await row_of(world.owner, proposal_id)
    assert (row["status"], row["outcome"]) == ("canceled", {"reason": "turn-incomplete"})
    # Confirmed again later, the stored card still says why, not "dismissed or replaced".
    later = problem_of(post(world, confirm_path(proposal_id)), 409)
    assert (later["type"], later["currentStatus"]) == ("turn-incomplete", "canceled")
    canceled = [
        e for e in await events_named(world, "proposal.canceled") if e.proposal_id == proposal_id
    ]
    assert [e.via for e in canceled] == ["system"]


# ---------------------------------------------------------------------------------------------
# Dismiss


async def test_dismissing_cancels_the_proposal_and_says_why(start: StartWorld) -> None:
    world = start("priya")
    await world.fund("priya")
    proposal_id = await book(world)

    response = post(world, cancel_path(proposal_id))

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["status"], body["canceledReason"], body["failure"]) == (
        "canceled",
        "dismissed",
        None,
    )
    row = await row_of(world.owner, proposal_id)
    assert row["outcome"] == {"reason": "dismissed"}
    event = (await events_named(world, "proposal.canceled"))[0]
    assert (event.via, event.proposal_id, event.actor_person_id) == (
        "ui",
        proposal_id,
        world.person("priya"),
    )


async def test_dismissing_works_while_the_turn_is_still_running(start: StartWorld) -> None:
    world = start("priya")
    await world.fund("priya")
    proposal_id = await book(world, turn_status="running")

    response = post(world, cancel_path(proposal_id))

    assert response.status_code == 200, response.text
    assert response.json()["canceledReason"] == "dismissed"


async def test_a_dismissed_card_cannot_then_be_confirmed(start: StartWorld) -> None:
    world = start("priya")
    await world.fund("priya")
    proposal_id = await book(world)
    assert post(world, cancel_path(proposal_id)).status_code == 200

    response = post(world, confirm_path(proposal_id))

    assert problem_of(response, 409)["type"] == "canceled"
    assert all(r.proposal_id != proposal_id for r in await requests_for(world, "priya"))


# ---------------------------------------------------------------------------------------------
# Exactly once, from two places at once


def fire_together(clients: list[Browser], path: str) -> list[Any]:
    """Post the same confirm from each client at the same moment."""
    # Warm each client's app first, one at a time, with a confirm that answers 404. FastAPI builds
    # a router's routes on the first request that reaches them, inside `warnings.catch_warnings()`
    # to hide a pydantic warning, and that context manager swaps the process-wide filters: two
    # threads building at once can restore them under each other, and the hidden warning then
    # escapes into this suite's "warnings are errors" setting.
    for client in clients:
        warm = client.client.post(confirm_path(uuid4()), headers=client.csrf)
        assert warm.status_code == 404, warm.text
    barrier = threading.Barrier(len(clients))

    def go(client: Browser) -> Any:
        barrier.wait()
        return client.client.post(path, headers=client.csrf)

    with ThreadPoolExecutor(max_workers=len(clients)) as pool:
        return list(pool.map(go, clients))


async def test_two_confirms_at_once_book_once(start: StartWorld, open_browser: OpenBrowser) -> None:
    world = start("priya")
    await world.fund("priya")
    # A second window, signed in as the same person.
    second = open_browser()
    for cookie in world.browser.client.cookies.jar:
        second.client.cookies.jar.set_cookie(cookie)
    person = world.person("priya")
    first_day = world.workday(30)
    days = [first_day + timedelta(days=7 * week) for week in range(5)]
    days = [world.workday((day - world.today).days) for day in days]
    before = len(await requests_for(world, "priya"))

    for day in days:
        chat = await make_chat(world.engine, world.tenant_id, person)
        proposal_id = await propose_request(
            world.engine, world.tenant_id, person, chat, pto(day), world.now
        )

        responses = await asyncio.to_thread(
            fire_together, [world.browser, second], confirm_path(proposal_id)
        )

        by_status = sorted(response.status_code for response in responses)
        assert by_status == [200, 409], [r.text for r in responses]
        loser = next(r for r in responses if r.status_code == 409)
        assert loser.json()["type"] == "executed"
        winner = next(r for r in responses if r.status_code == 200)
        assert winner.json()["status"] == "executed"

    assert len(await requests_for(world, "priya")) == before + len(days)
    confirmed = await events_named(world, "proposal.confirmed")
    assert len(confirmed) == len(days)
    assert len({e.proposal_id for e in confirmed}) == len(days)


async def test_a_status_with_no_fixed_text_is_still_a_409_never_a_500(start: StartWorld) -> None:
    from sqlalchemy import insert

    from app.db.models import TimeOffRequest
    from app.db.tenancy import TenantContext, tenant_session

    world = start("priya")
    await world.fund("priya")
    proposal_id = await book(world)
    # A request already carries this proposal, though the proposal is still pending (a state the
    # service never makes): the one-request-per-proposal index refuses the confirm's insert, and
    # the conflict's status is `pending`, which has no sentence of its own.
    other = world.workday(45)
    async with tenant_session(
        world.engine, TenantContext(world.tenant_id, world.person("priya"))
    ) as session:
        await session.execute(
            insert(TimeOffRequest).values(
                tenant_id=world.tenant_id,
                person_id=world.person("priya"),
                type="pto",
                start_date=other,
                end_date=other,
                amount_minutes=480,
                status="pending",
                created_via="assistant",
                proposal_id=proposal_id,
            )
        )

    response = post(world, confirm_path(proposal_id))

    body = problem_of(response, 409)
    assert body["type"] == "pending"
    assert body["detail"]


# ---------------------------------------------------------------------------------------------
# The conversation read gives each turn its proposals

CURRENT = "/api/v1/assistant/conversations/current"


def proposals_of(world: World) -> list[dict[str, Any]]:
    """The proposals of the newest conversation's only turn, as the page reads them."""
    response = world.browser.client.get(CURRENT)
    assert response.status_code == 200, response.text
    [turn] = response.json()["turns"]
    proposals: list[dict[str, Any]] = turn["proposals"]
    return proposals


def only(world: World) -> dict[str, Any]:
    [proposal] = proposals_of(world)
    return proposal


async def test_a_pending_card_of_a_finished_turn_reads_pending_with_its_card_and_confirm_allowed(
    start: StartWorld,
) -> None:
    world = start("priya")
    await world.fund("priya")
    day = world.workday(30)
    proposal_id = await book(world, day)

    proposal = only(world)

    assert set(proposal) == PROPOSAL_KEYS
    assert (proposal["id"], proposal["status"], proposal["turnRunning"]) == (
        str(proposal_id),
        "pending",
        False,
    )
    assert proposal["card"]["startDate"] == day.isoformat()
    assert (proposal["canceledReason"], proposal["failure"]) == (None, None)


async def test_a_pending_card_of_a_running_turn_reads_pending_and_says_its_turn_is_running(
    start: StartWorld,
) -> None:
    world = start("priya")
    await world.fund("priya")
    await book(world, turn_status="running")

    proposal = only(world)

    assert (proposal["status"], proposal["turnRunning"]) == ("pending", True)


async def test_a_confirmed_card_reads_executed_and_has_the_shape_the_confirm_returned(
    start: StartWorld,
) -> None:
    world = start("priya")
    await world.fund("priya")
    proposal_id = await book(world)
    confirmed = post(world, confirm_path(proposal_id)).json()

    assert only(world) == confirmed
    assert confirmed["status"] == "executed"
    assert confirmed["turnRunning"] is False


async def test_a_failed_card_reads_failed_with_its_code_and_fixed_text(start: StartWorld) -> None:
    world = start("priya")
    await world.fund("priya")
    day = world.workday(30)
    proposal_id = await book(world, day)
    await world.put("priya", day, status="approved")
    confirmed = post(world, confirm_path(proposal_id)).json()

    proposal = only(world)

    assert proposal == confirmed
    assert proposal["status"] == "failed"
    assert proposal["failure"] == {
        "code": "overlaps",
        "text": refusal_text("overlaps"),
        "dates": [day.isoformat()],
    }


async def test_a_dismissed_card_and_a_replaced_card_read_canceled_with_their_reasons(
    start: StartWorld,
) -> None:
    world = start("priya")
    await world.fund("priya")
    person = world.person("priya")
    chat = await chat_for(world, "priya", turn_status="running")
    first = await propose_request(
        world.engine, world.tenant_id, person, chat, pto(world.workday(30)), world.now
    )
    second = await propose_request(
        world.engine, world.tenant_id, person, chat, pto(world.workday(40)), world.now
    )
    assert post(world, cancel_path(second)).status_code == 200
    third = await propose_request(
        world.engine, world.tenant_id, person, chat, pto(world.workday(50)), world.now
    )
    await end_turn(world.engine, chat, "completed")

    got = proposals_of(world)

    # Oldest first, each with its reason.
    assert [(p["id"], p["status"], p["canceledReason"]) for p in got] == [
        (str(first), "canceled", "replaced"),
        (str(second), "canceled", "dismissed"),
        (str(third), "pending", None),
    ]


async def test_a_pending_card_past_its_expiry_reads_expired_and_the_read_writes_nothing(
    start: StartWorld,
) -> None:
    world = start("priya")
    await world.fund("priya")
    proposal_id = await book(world)
    await age(world.owner, proposal_id, timedelta(minutes=20))
    before = await row_of(world.owner, proposal_id)

    proposal = only(world)

    assert (proposal["status"], proposal["turnRunning"]) == ("expired", False)
    assert await row_of(world.owner, proposal_id) == before
    assert before["status"] == "pending"


async def test_an_expired_card_of_a_running_turn_reads_expired_not_running(
    start: StartWorld,
) -> None:
    world = start("priya")
    await world.fund("priya")
    proposal_id = await book(world, turn_status="running")
    await age(world.owner, proposal_id, timedelta(minutes=20))

    proposal = only(world)

    assert (proposal["status"], proposal["turnRunning"]) == ("expired", False)


@pytest.mark.parametrize("turn_status", ["failed", "stopped", "crisis", "guard_unavailable"])
async def test_a_pending_card_of_a_turn_that_did_not_finish_reads_canceled_turn_incomplete(
    start: StartWorld, turn_status: str
) -> None:
    world = start("priya")
    await world.fund("priya")
    proposal_id = await book(world, turn_status=turn_status)
    before = await row_of(world.owner, proposal_id)

    proposal = only(world)

    assert (proposal["status"], proposal["canceledReason"], proposal["turnRunning"]) == (
        "canceled",
        "turn-incomplete",
        False,
    )
    assert before["status"] == "pending"
    assert await row_of(world.owner, proposal_id) == before


async def test_a_card_of_an_abandoned_running_turn_reads_canceled_turn_incomplete_without_writing(
    start: StartWorld,
) -> None:
    world = start("priya")
    await world.fund("priya")
    proposal_id = await book(world, turn_status="running", started_ago=timedelta(minutes=11))
    before = await row_of(world.owner, proposal_id)

    proposal = only(world)

    assert (proposal["status"], proposal["canceledReason"], proposal["turnRunning"]) == (
        "canceled",
        "turn-incomplete",
        False,
    )
    assert await row_of(world.owner, proposal_id) == before


async def test_a_confirm_after_such_a_read_agrees_with_what_the_read_showed(
    start: StartWorld,
) -> None:
    world = start("priya")
    await world.fund("priya")
    proposal_id = await book(world, turn_status="failed")
    shown = only(world)

    response = post(world, confirm_path(proposal_id))

    assert response.status_code == 409
    assert await proposal_status(world, proposal_id) == shown["status"] == "canceled"


async def test_a_proposal_from_another_conversation_or_person_never_appears(
    start: StartWorld,
) -> None:
    world = start("priya")
    await world.fund("priya")
    await world.fund("marcus")
    # An older conversation of Priya's, a colleague's conversation, and then her newest.
    await book(world)
    await book(world, persona="marcus")
    mine = await book(world, world.workday(40))

    got = proposals_of(world)

    assert [p["id"] for p in got] == [str(mine)]


async def test_the_proposals_are_read_in_one_statement_however_many_turns_have_cards(
    start: StartWorld,
) -> None:
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    world = start("priya")
    await world.fund("priya")
    person = world.person("priya")
    chat = await chat_for(world, "priya")
    await propose_request(
        world.engine, world.tenant_id, person, chat, pto(world.workday(30)), world.now
    )
    # Two more turns in the same conversation, each with a card of its own.
    for offset in (40, 50):
        from app.db.tenancy import TenantContext, tenant_session

        turn_id = uuid4()
        async with tenant_session(world.engine, TenantContext(world.tenant_id, person)) as db:
            db.add(
                await turn_row(db, chat.conversation_id, turn_id, "And another?", status="running")
            )
        more = Chat(chat.conversation_id, turn_id, world.tenant_id, person, "completed")
        await propose_request(
            world.engine, world.tenant_id, person, more, pto(world.workday(offset)), world.now
        )
    seen: list[str] = []

    def record(conn: Any, cursor: Any, statement: str, *rest: Any) -> None:
        if "FROM ai_proposals" in statement:
            seen.append(statement)

    event.listen(Engine, "before_cursor_execute", record)
    try:
        response = world.browser.client.get(CURRENT)
    finally:
        event.remove(Engine, "before_cursor_execute", record)

    turns = response.json()["turns"]
    assert [len(t["proposals"]) for t in turns] == [1, 1, 1]
    assert len(seen) == 1


@pytest.mark.parametrize(
    ("turn", "started_ago", "read", "confirm_status", "row_after"),
    [
        ("completed", None, ("pending", False), 200, "executed"),
        ("running", None, ("pending", True), 409, "pending"),
        ("running", timedelta(minutes=11), ("canceled", False), 409, "canceled"),
        ("failed", None, ("canceled", False), 409, "canceled"),
        ("stopped", None, ("canceled", False), 409, "canceled"),
    ],
    ids=["completed", "running", "abandoned", "failed", "stopped"],
)
async def test_what_the_read_shows_is_what_a_confirm_then_does(
    start: StartWorld,
    turn: str,
    started_ago: timedelta | None,
    read: tuple[str, bool],
    confirm_status: int,
    row_after: str,
) -> None:
    world = start("priya")
    await world.fund("priya")
    proposal_id = await book(world, turn_status=turn, started_ago=started_ago or timedelta(0))

    shown = only(world)
    response = post(world, confirm_path(proposal_id))

    assert (shown["status"], shown["turnRunning"]) == read
    assert response.status_code == confirm_status
    assert await proposal_status(world, proposal_id) == row_after
    if confirm_status == 409:
        # Nothing was booked, and a running turn's card is the only one still waiting.
        assert all(r.proposal_id != proposal_id for r in await requests_for(world, "priya"))
        assert (shown["status"] == "pending") == (row_after == "pending")


async def test_a_replaced_card_keeps_its_own_409_and_a_dismissed_one_too(start: StartWorld) -> None:
    world = start("priya")
    await world.fund("priya")
    person = world.person("priya")
    chat = await make_chat(world.engine, world.tenant_id, person, turn_status="running")
    first = await propose_request(
        world.engine, world.tenant_id, person, chat, pto(world.workday(30)), world.now
    )
    second = await propose_request(
        world.engine, world.tenant_id, person, chat, pto(world.workday(40)), world.now
    )
    assert post(world, cancel_path(second)).status_code == 200

    replaced = problem_of(post(world, confirm_path(first)), 409)
    dismissed = problem_of(post(world, confirm_path(second)), 409)

    for body in (replaced, dismissed):
        assert (body["type"], body["currentStatus"]) == ("canceled", "canceled")
        assert body["detail"] == PROPOSAL_CONFLICT_TEXTS["canceled"]


# ---------------------------------------------------------------------------------------------
# The denial's note, read back by the person who wrote it


DENIAL_NOTE = "Two of the team are out that week, sorry."


async def deny_card(
    world: World, decision: Literal["approve", "deny"] = "deny"
) -> tuple[UUID, UUID]:
    """Marcus's pending card to decide Priya's request. Returns (proposal, request)."""
    request_id = await world.put("priya", world.workday(30))
    chat = await chat_for(world, "marcus")
    proposal_id = await propose_decision(
        world.engine,
        world.tenant_id,
        world.person("marcus"),
        chat,
        request_id,
        decision,
        world.now,
    )
    return proposal_id, request_id


async def test_an_executed_denial_reads_back_the_note_stored_on_its_request(
    start: StartWorld,
) -> None:
    world = start("marcus")
    proposal_id, _ = await deny_card(world)
    confirmed = post(world, confirm_path(proposal_id), {"note": f"  {DENIAL_NOTE}  "})
    assert confirmed.status_code == 200, confirmed.text

    proposal = only(world)

    assert proposal["status"] == "executed"
    assert proposal["deniedNote"] == DENIAL_NOTE
    # Only the conversation read carries it: the confirm's own answer stays null.
    assert confirmed.json()["deniedNote"] is None


async def test_an_executed_denial_without_a_note_reads_null(start: StartWorld) -> None:
    world = start("marcus")
    proposal_id, _ = await deny_card(world)
    assert post(world, confirm_path(proposal_id)).status_code == 200

    assert only(world)["deniedNote"] is None


async def test_a_blank_note_on_a_denial_reads_null(start: StartWorld) -> None:
    world = start("marcus")
    proposal_id, _ = await deny_card(world)
    assert post(world, confirm_path(proposal_id), {"note": "   "}).status_code == 200

    assert only(world)["deniedNote"] is None


async def test_a_pending_denial_reads_null(start: StartWorld) -> None:
    world = start("marcus")
    await deny_card(world)

    proposal = only(world)

    assert (proposal["status"], proposal["deniedNote"]) == ("pending", None)


async def test_an_executed_approval_reads_null(start: StartWorld) -> None:
    world = start("marcus")
    proposal_id, _ = await deny_card(world, "approve")
    assert post(world, confirm_path(proposal_id)).status_code == 200

    proposal = only(world)

    assert (proposal["status"], proposal["deniedNote"]) == ("executed", None)


async def test_nobody_else_reads_the_note_and_the_read_makes_one_extra_query_at_most(
    start: StartWorld,
) -> None:
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    world = start("marcus")
    proposal_id, _ = await deny_card(world)
    assert post(world, confirm_path(proposal_id), {"note": DENIAL_NOTE}).status_code == 200
    seen: list[str] = []

    def record(conn: Any, cursor: Any, statement: str, *rest: Any) -> None:
        if "decision_note" in statement:
            seen.append(statement)

    event.listen(Engine, "before_cursor_execute", record)
    try:
        response = world.browser.client.get(CURRENT)
    finally:
        event.remove(Engine, "before_cursor_execute", record)

    assert DENIAL_NOTE in response.text
    assert len(seen) == 1
    # A person with no such proposal (Priya's own conversation) never sees the text.
    priya = start("priya")
    assert DENIAL_NOTE not in priya.browser.client.get(CURRENT).text


async def test_a_note_on_a_request_this_person_did_not_decide_is_not_read(
    start: StartWorld, owner_engine: AsyncEngine
) -> None:
    """The proposal's recorded request must be one this person decided, or the note stays unread."""
    from sqlalchemy import text

    world = start("marcus")
    proposal_id, request_id = await deny_card(world)
    assert post(world, confirm_path(proposal_id), {"note": DENIAL_NOTE}).status_code == 200
    # Past the freeze trigger, in one transaction that puts the trigger back.
    async with owner_engine.begin() as connection:
        await connection.execute(
            text("ALTER TABLE time_off_requests DISABLE TRIGGER enforce_time_off_request_update")
        )
        await connection.execute(
            text("UPDATE time_off_requests SET decided_by = :other WHERE id = :id"),
            {"other": world.person("dana"), "id": request_id},
        )
        await connection.execute(
            text("ALTER TABLE time_off_requests ENABLE TRIGGER enforce_time_off_request_update")
        )

    assert only(world)["deniedNote"] is None
