"""Signing in over HTTP: sandboxes, sessions, the CSRF and same-origin checks, and their logs."""

import json
import logging
import re
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Session

from app.core.logging import JsonFormatter
from app.db.tenancy import TenantContext, tenant_session
from app.modules.identity import deps as identity_deps
from app.modules.identity import routes as identity_routes
from app.modules.identity.cookies import CSRF_COOKIE, SESSION_COOKIE
from app.modules.identity.sessions import (
    SessionRecord,
    end_session,
    rotate_session,
    start_session,
)
from app.modules.identity.tokens import SessionTokens, hash_token
from tests.integration.conftest import (
    Browser,
    MakeTenant,
    OpenBrowser,
    audit_events,
    session_cookie,
)

pytestmark = pytest.mark.integration

ME_FIELDS = {
    "id",
    "givenName",
    "familyName",
    "title",
    "department",
    "location",
    "manager",
    "workEmail",
    "employmentType",
    "isManager",
    "isHrAdmin",
    "personaKey",
    "tenantExpiresAt",
}
SET_COOKIE = re.compile(
    r"(__Host-od_session|__Host-od_csrf)=[A-Za-z0-9_-]{43}; (HttpOnly; )?Max-Age=([0-9]+); "
    r"Path=/; SameSite=lax; Secure"
)


def security_events(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.name == "app.security"]


def test_a_new_sandbox_signs_the_visitor_in_as_priya(browser: Browser) -> None:
    response = browser.create_sandbox()

    assert response.status_code == 201
    body = response.json()
    expires_at = datetime.fromisoformat(body["tenant"]["expiresAt"])
    assert timedelta(hours=23, minutes=59) < expires_at - datetime.now(UTC) <= timedelta(hours=24)
    assert set(body["me"]) == ME_FIELDS
    assert (body["me"]["givenName"], body["me"]["personaKey"]) == ("Priya", "priya")
    assert body["me"]["tenantExpiresAt"] == body["tenant"]["expiresAt"]


def test_both_cookies_are_set_secure_host_only_and_until_the_sandbox_expires(
    browser: Browser,
) -> None:
    response = browser.create_sandbox({"persona": "mateo"})

    cookies = [SET_COOKIE.fullmatch(header) for header in response.headers.get_list("set-cookie")]
    assert all(cookies), response.headers.get_list("set-cookie")
    named = {match[1]: match for match in cookies if match}
    assert named["__Host-od_session"][2] == "HttpOnly; "
    # The page must read the CSRF token, so that cookie is not HttpOnly.
    assert named["__Host-od_csrf"][2] is None
    assert 86_390 < int(named["__Host-od_session"][3]) < 86_400


@pytest.mark.parametrize(
    ("persona", "name", "employment_type", "is_manager", "is_hr_admin"),
    [
        ("priya", "Priya", "salaried", False, False),
        ("mateo", "Mateo", "hourly", False, False),
        ("marcus", "Marcus", "salaried", True, False),
        ("dana", "Dana", "salaried", False, True),
    ],
)
def test_each_persona_sees_their_own_card_at_me(
    browser: Browser,
    persona: str,
    name: str,
    employment_type: str,
    is_manager: bool,
    is_hr_admin: bool,
) -> None:
    created = browser.start_sandbox(persona)

    response = browser.client.get("/api/v1/me")

    me = response.json()
    assert response.status_code == 200
    assert me == created["me"]
    assert (me["givenName"], me["personaKey"], me["employmentType"]) == (
        name,
        persona,
        employment_type,
    )
    assert (me["isManager"], me["isHrAdmin"]) == (is_manager, is_hr_admin)


@pytest.mark.parametrize("persona", ["leo", "Priya", "", "admin"])
def test_only_the_four_personas_can_sign_in(browser: Browser, persona: str) -> None:
    response = browser.create_sandbox({"persona": persona})

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    assert "__Host-od_session" not in browser.client.cookies


async def test_creating_a_sandbox_is_audited(browser: Browser, app_engine: AsyncEngine) -> None:
    sandbox = browser.start_sandbox("marcus")
    tenant_id = UUID(sandbox["tenant"]["id"])

    [event] = await audit_events(app_engine, tenant_id)

    assert (event.action, event.via, event.actor_person_id) == (
        "sandbox.created",
        "ui",
        UUID(sandbox["me"]["id"]),
    )
    assert (event.target_type, event.target_id, event.after) == (
        "tenant",
        tenant_id,
        {"personaKey": "marcus"},
    )
    assert event.request_id is not None


def test_a_new_sandbox_ends_the_session_the_browser_already_had(browser: Browser) -> None:
    first = browser.start_sandbox()
    first_token = browser.session_token

    second = browser.start_sandbox()

    assert browser.client.get("/api/v1/me", headers=session_cookie(first_token)).status_code == 401
    me = browser.client.get("/api/v1/me").json()
    assert me["id"] == second["me"]["id"] != first["me"]["id"]


def test_without_a_session_the_api_answers_401(
    browser: Browser, caplog: pytest.LogCaptureFixture
) -> None:
    responses = [
        browser.client.get("/api/v1/me"),
        browser.client.put("/api/v1/session/persona", json={"persona": "dana"}),
        browser.client.delete("/api/v1/session"),
        browser.client.get("/api/v1/me", headers=session_cookie("not-a-real-session-token")),
    ]

    assert [response.status_code for response in responses] == [401] * 4
    assert all(r.headers["content-type"] == "application/problem+json" for r in responses)
    reasons = [record.__dict__["fields"]["reason"] for record in security_events(caplog)]
    assert reasons == ["no session cookie"] * 3 + ["unknown or expired session"]


async def test_an_expired_session_is_refused(
    browser: Browser, app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant(expired=True)
    async with tenant_session(app_engine, TenantContext(tenant.id, None)) as session:
        tokens = await start_session(session, tenant.id, tenant.employee_id)

    response = browser.client.get("/api/v1/me", headers=session_cookie(tokens.session))

    assert response.status_code == 401


async def test_switching_persona_issues_new_tokens_and_retires_the_old_ones(
    browser: Browser, app_engine: AsyncEngine
) -> None:
    sandbox = browser.start_sandbox()
    old_session, old_csrf = browser.session_token, browser.csrf_token

    response = browser.client.put(
        "/api/v1/session/persona", json={"persona": "dana"}, headers=browser.csrf
    )

    assert response.status_code == 200
    assert (response.json()["personaKey"], response.json()["isHrAdmin"]) == ("dana", True)
    assert browser.session_token != old_session
    assert browser.csrf_token != old_csrf
    # The old session token is unknown now.
    assert browser.client.get("/api/v1/me", headers=session_cookie(old_session)).status_code == 401
    # The new session token with the old CSRF token can't change anything.
    stale = browser.client.put(
        "/api/v1/session/persona", json={"persona": "priya"}, headers={"X-CSRF-Token": old_csrf}
    )
    assert stale.status_code == 403
    assert browser.client.get("/api/v1/me").json()["personaKey"] == "dana"

    events = await audit_events(app_engine, UUID(sandbox["tenant"]["id"]))
    [switch] = [event for event in events if event.action == "session.persona_switched"]
    assert (switch.actor_person_id, switch.target_id) == (
        UUID(sandbox["me"]["id"]),
        UUID(response.json()["id"]),
    )
    assert (switch.before, switch.after) == ({"personaKey": "priya"}, {"personaKey": "dana"})


@pytest.mark.parametrize("csrf_token", [None, "", "not-the-csrf-token"])
def test_a_change_without_the_right_csrf_token_is_refused(
    browser: Browser, caplog: pytest.LogCaptureFixture, csrf_token: str | None
) -> None:
    sandbox = browser.start_sandbox()
    headers = {} if csrf_token is None else {"X-CSRF-Token": csrf_token}
    # The session token is valid, but it is not a CSRF token.
    wrong_kind = {"X-CSRF-Token": browser.session_token}

    for attempt in (headers, wrong_kind):
        switch = browser.client.put(
            "/api/v1/session/persona", json={"persona": "marcus"}, headers=attempt
        )
        sign_out = browser.client.delete("/api/v1/session", headers=attempt)
        assert (switch.status_code, sign_out.status_code) == (403, 403)

    assert browser.client.get("/api/v1/me").json()["personaKey"] == "priya"
    [record, *_] = security_events(caplog)
    assert record.getMessage() == "security.csrf_rejected"
    assert record.__dict__["fields"]["tenantId"] == sandbox["tenant"]["id"]
    assert record.__dict__["fields"]["actorId"] == sandbox["me"]["id"]


def test_an_unknown_persona_switch_is_refused(browser: Browser) -> None:
    browser.start_sandbox()

    response = browser.client.put(
        "/api/v1/session/persona", json={"persona": "leo"}, headers=browser.csrf
    )

    assert response.status_code == 422


async def test_signing_out_ends_the_session_and_clears_both_cookies(
    browser: Browser, app_engine: AsyncEngine
) -> None:
    sandbox = browser.start_sandbox()
    token = browser.session_token

    response = browser.client.delete("/api/v1/session", headers=browser.csrf)

    assert response.status_code == 204
    cleared = response.headers.get_list("set-cookie")
    assert [header.split("=")[0] for header in cleared] == ["__Host-od_session", "__Host-od_csrf"]
    assert all("Max-Age=0; Path=/; SameSite=lax; Secure" in header for header in cleared)
    assert "__Host-od_session" not in browser.client.cookies
    assert browser.client.get("/api/v1/me", headers=session_cookie(token)).status_code == 401
    events = await audit_events(app_engine, UUID(sandbox["tenant"]["id"]))
    assert [event.action for event in events] == ["sandbox.created", "session.ended"]


@pytest.mark.parametrize(
    "headers",
    [
        {"Sec-Fetch-Site": "cross-site"},
        {"Sec-Fetch-Site": "same-site"},
        {"Origin": "https://evil.example"},
        {},
    ],
)
def test_sandbox_creation_and_session_changes_need_the_same_origin(
    open_browser: OpenBrowser, caplog: pytest.LogCaptureFixture, headers: dict[str, str]
) -> None:
    signed_in = open_browser()
    signed_in.start_sandbox()
    script = open_browser(same_origin_header=False)
    cookies = {"Cookie": f"__Host-od_session={signed_in.session_token}"}

    create = script.create_sandbox({}, headers=headers)
    switch = script.client.put(
        "/api/v1/session/persona",
        json={"persona": "dana"},
        headers={**headers, **cookies, **signed_in.csrf},
    )
    sign_out = script.client.delete("/api/v1/session", headers={**headers, **cookies})

    assert (create.status_code, switch.status_code, sign_out.status_code) == (403, 403, 403)
    assert create.json()["requestId"] == create.headers["X-Request-ID"]
    assert "set-cookie" not in create.headers
    assert [record.getMessage() for record in security_events(caplog)] == [
        "security.origin_rejected"
    ] * 3
    assert signed_in.client.get("/api/v1/me").json()["personaKey"] == "priya"


def test_the_app_origin_passes_without_fetch_metadata(open_browser: OpenBrowser) -> None:
    script = open_browser(same_origin_header=False)

    response = script.create_sandbox({}, headers={"Origin": "http://localhost:5173"})

    assert response.status_code == 201


def test_security_events_never_contain_a_raw_token(
    open_browser: OpenBrowser, caplog: pytest.LogCaptureFixture
) -> None:
    browser = open_browser()
    browser.start_sandbox()
    session_token, csrf_token = browser.session_token, browser.csrf_token
    cross_site = open_browser(same_origin_header=False)

    # One of each event this stage logs: a bad CSRF token, a cross-site change, and an unknown
    # session. Each carries the real session token in its cookie.
    browser.client.delete("/api/v1/session", headers={"X-CSRF-Token": "wrong"})
    cross_site.client.delete(
        "/api/v1/session",
        headers={"Sec-Fetch-Site": "cross-site", **session_cookie(session_token)},
    )
    browser.client.delete("/api/v1/session", headers=browser.csrf)
    browser.client.get("/api/v1/me", headers=session_cookie(session_token))

    records = security_events(caplog)
    lines = [JsonFormatter().format(record) for record in records]
    assert [json.loads(line)["event"] for line in lines] == [
        "security.csrf_rejected",
        "security.origin_rejected",
        "security.session_invalid",
    ]
    prefix = hash_token(session_token).hex()[:8]
    for line in lines:
        entry = json.loads(line)
        assert session_token not in line
        assert csrf_token not in line
        assert entry["tokenHashPrefix"] == prefix
        assert entry["clientIp"] == "testclient"
        assert entry["requestId"]


async def test_switching_persona_on_a_session_another_tab_just_ended_is_a_401(
    browser: Browser,
    app_engine: AsyncEngine,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sandbox = browser.start_sandbox()
    old_session, old_csrf = browser.session_token, browser.csrf_token

    async def rotate_after_a_sign_out(
        db: AsyncSession, current: SessionRecord, person_id: UUID
    ) -> SessionTokens:
        # The other tab's sign-out lands between this request's lookup and its rotation.
        await end_session(db, current.token_hash)
        return await rotate_session(db, current, person_id)

    monkeypatch.setattr(identity_routes, "rotate_session", rotate_after_a_sign_out)

    response = browser.client.put(
        "/api/v1/session/persona", json={"persona": "dana"}, headers=browser.csrf
    )

    assert response.status_code == 401
    assert response.headers["content-type"] == "application/problem+json"
    # Nothing was rotated: no new cookies, and no audit event for a switch that didn't happen.
    assert "set-cookie" not in response.headers
    assert (browser.session_token, browser.csrf_token) == (old_session, old_csrf)
    [record] = security_events(caplog)
    assert record.getMessage() == "security.session_invalid"
    assert record.__dict__["fields"]["tenantId"] == sandbox["tenant"]["id"]
    assert record.__dict__["fields"]["actorId"] == sandbox["me"]["id"]
    events = await audit_events(app_engine, UUID(sandbox["tenant"]["id"]))
    assert [event.action for event in events] == ["sandbox.created"]


async def test_signing_out_of_a_session_that_is_already_gone_audits_nothing_twice(
    browser: Browser, app_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    sandbox = browser.start_sandbox()

    async def end_it_in_another_tab_first(db: AsyncSession, token_hash: bytes) -> bool:
        await end_session(db, token_hash)
        # This request's own delete now finds nothing, so it didn't end the session.
        return await end_session(db, token_hash)

    monkeypatch.setattr(identity_routes, "end_session", end_it_in_another_tab_first)

    response = browser.client.delete("/api/v1/session", headers=browser.csrf)

    assert response.status_code == 204
    cleared = response.headers.get_list("set-cookie")
    assert [header.split("=")[0] for header in cleared] == ["__Host-od_session", "__Host-od_csrf"]
    assert "__Host-od_session" not in browser.client.cookies
    events = await audit_events(app_engine, UUID(sandbox["tenant"]["id"]))
    assert [event.action for event in events] == ["sandbox.created"]


def test_every_api_response_is_marked_no_store(open_browser: OpenBrowser) -> None:
    """A cache in front of the API that forwards cookies but doesn't key on them could otherwise
    hand one visitor's response to another."""
    signed_in, signed_out = open_browser(), open_browser()
    script = open_browser(same_origin_header=False)

    created = signed_in.create_sandbox()
    me = signed_in.client.get("/api/v1/me")
    switched = signed_in.client.put(
        "/api/v1/session/persona", json={"persona": "dana"}, headers=signed_in.csrf
    )
    ended = signed_in.client.delete("/api/v1/session", headers=signed_in.csrf)
    not_signed_in = signed_out.client.get("/api/v1/me")
    cross_origin = script.create_sandbox({}, headers={"Sec-Fetch-Site": "cross-site"})

    responses = {
        "POST /sandboxes": (created, 201),
        "GET /me": (me, 200),
        "PUT /session/persona": (switched, 200),
        "DELETE /session": (ended, 204),
        "a 401": (not_signed_in, 401),
        "a same-origin 403": (cross_origin, 403),
    }
    assert {name: response.status_code for name, (response, _) in responses.items()} == {
        name: expected for name, (_, expected) in responses.items()
    }
    assert {
        name: response.headers.get("cache-control") for name, (response, _) in responses.items()
    } == {name: "no-store" for name in responses}


def test_a_commit_that_fails_is_an_error_not_a_success(open_browser: OpenBrowser) -> None:
    browser = open_browser(raise_server_exceptions=False)
    browser.start_sandbox()
    old_session, old_csrf = browser.session_token, browser.csrf_token

    def fail_the_requests_commit(session: Session) -> None:
        # Only the signed-in request's transaction is scoped to a tenant here. The session lookup
        # before it has no tenant, so it commits normally.
        context = session.info.get("tenant")
        if isinstance(context, TenantContext) and context.tenant_id is not None:
            msg = "simulated commit failure"
            raise RuntimeError(msg)

    event.listen(Session, "before_commit", fail_the_requests_commit)
    try:
        response = browser.client.put(
            "/api/v1/session/persona", json={"persona": "dana"}, headers=browser.csrf
        )
    finally:
        event.remove(Session, "before_commit", fail_the_requests_commit)

    # The commit ran before the response was sent, so the client was told, and was not signed in
    # as someone it never became.
    assert response.status_code == 500
    assert response.headers["content-type"] == "application/problem+json"
    assert response.headers["cache-control"] == "no-store"
    assert "set-cookie" not in response.headers
    assert (browser.session_token, browser.csrf_token) == (old_session, old_csrf)
    still_signed_in = browser.client.get("/api/v1/me", headers=session_cookie(old_session))
    assert (still_signed_in.status_code, still_signed_in.json()["personaKey"]) == (200, "priya")


def test_a_csrf_token_from_another_session_is_refused(
    open_browser: OpenBrowser, caplog: pytest.LogCaptureFixture
) -> None:
    browser_a, browser_b = open_browser(), open_browser()
    sandbox_a = browser_a.start_sandbox()
    browser_b.start_sandbox()
    # A's session with B's valid CSRF token, as both the cookie and the header. A check that only
    # compared the cookie with the header, as a double-submit cookie does, would accept this.
    cookies = f"{SESSION_COOKIE}={browser_a.session_token}; {CSRF_COOKIE}={browser_b.csrf_token}"

    response = browser_a.client.put(
        "/api/v1/session/persona",
        json={"persona": "dana"},
        headers={"Cookie": cookies, **browser_b.csrf},
    )

    assert response.status_code == 403
    [record] = security_events(caplog)
    assert record.getMessage() == "security.csrf_rejected"
    assert record.__dict__["fields"]["tenantId"] == sandbox_a["tenant"]["id"]
    assert record.__dict__["fields"]["actorId"] == sandbox_a["me"]["id"]
    assert browser_a.client.get("/api/v1/me").json()["personaKey"] == "priya"


def test_a_session_whose_sandbox_is_gone_is_a_401_that_logs_who_it_was(
    browser: Browser, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    sandbox = browser.start_sandbox()

    async def person_not_found(db: AsyncSession, tenant_id: UUID, person_id: UUID) -> None:
        # What load_actor finds if the sandbox is deleted between the session lookup and now.
        return None

    monkeypatch.setattr(identity_deps, "load_actor", person_not_found)

    response = browser.client.get("/api/v1/me")

    assert response.status_code == 401
    [record] = security_events(caplog)
    assert record.getMessage() == "security.session_invalid"
    assert record.__dict__["fields"]["reason"] == "the sandbox is gone"
    assert record.__dict__["fields"]["tenantId"] == sandbox["tenant"]["id"]
    assert record.__dict__["fields"]["actorId"] == sandbox["me"]["id"]
