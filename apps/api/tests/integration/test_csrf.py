"""CSRF on every method, and one transaction for each signed-in request (Phase 8, stage 1).

`current_session` checks `X-CSRF-Token` on every signed-in request, including a read, so no
per-route dependency is needed for an audited read and a future one cannot forget it. The shared
`browser` client adds the header from its cookie jar, as the web app does on every request; these
tests turn that off with `browser.without_csrf()` to see the refusal.
"""

import logging
from typing import Any

import pytest
from fastapi import Request
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.modules.identity.deps import CallerDep, SignedInDep
from tests.integration.conftest import Browser, OpenBrowser, session_cookie

pytestmark = pytest.mark.integration


def security_messages(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == "app.security"]


def test_a_signed_in_get_without_the_csrf_header_is_refused_and_logged(
    browser: Browser, caplog: pytest.LogCaptureFixture
) -> None:
    sandbox = browser.start_sandbox()

    with browser.without_csrf():
        response = browser.client.get("/api/v1/me")

    assert response.status_code == 403
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["detail"] == "The CSRF token is missing or wrong."
    assert response.json()["type"] == "csrf-rejected"
    assert "personaKey" not in response.text
    assert security_messages(caplog) == ["security.csrf_rejected"]
    [record] = [r for r in caplog.records if r.name == "app.security"]
    assert record.__dict__["fields"]["tenantId"] == sandbox["tenant"]["id"]


def test_a_signed_in_get_with_the_csrf_header_is_served(browser: Browser) -> None:
    browser.start_sandbox()

    response = browser.client.get("/api/v1/me", headers=browser.csrf)

    assert response.status_code == 200
    assert response.json()["personaKey"] == "priya"


@pytest.mark.parametrize("token", ["", "not-the-csrf-token"])
def test_a_wrong_csrf_header_on_a_get_is_refused(
    browser: Browser, caplog: pytest.LogCaptureFixture, token: str
) -> None:
    browser.start_sandbox()

    response = browser.client.get("/api/v1/me", headers={"X-CSRF-Token": token})

    assert response.status_code == 403
    assert security_messages(caplog) == ["security.csrf_rejected"]


def test_the_session_token_is_not_a_csrf_token(browser: Browser) -> None:
    browser.start_sandbox()

    response = browser.client.get("/api/v1/me", headers={"X-CSRF-Token": browser.session_token})

    assert response.status_code == 403


def test_a_get_with_no_session_is_a_401_before_any_csrf_check(
    browser: Browser, caplog: pytest.LogCaptureFixture
) -> None:
    response = browser.client.get("/api/v1/me")

    assert response.status_code == 401
    assert security_messages(caplog) == []


def test_an_unknown_session_is_a_401_not_a_403(browser: Browser) -> None:
    browser.start_sandbox()

    response = browser.client.get("/api/v1/me", headers=session_cookie("not-a-real-token"))

    assert response.status_code == 401


def test_the_assistant_texts_read_needs_the_header_too(browser: Browser) -> None:
    # It uses the short `current_session` lookup, not `signed_in`.
    browser.start_sandbox()

    with browser.without_csrf():
        refused = browser.client.get("/api/v1/assistant/texts")
    served = browser.client.get("/api/v1/assistant/texts", headers=browser.csrf)

    assert (refused.status_code, served.status_code) == (403, 200)


def test_the_health_check_and_starting_a_sandbox_need_no_csrf_header(
    open_browser: OpenBrowser,
) -> None:
    visitor = open_browser()

    with visitor.without_csrf():
        health = visitor.client.get("/api/v1/health")
        started = visitor.create_sandbox()

    assert health.status_code == 200
    assert started.status_code == 201


def test_a_second_sandbox_start_with_cookies_needs_no_csrf_header_either(
    open_browser: OpenBrowser,
) -> None:
    visitor = open_browser()
    visitor.start_sandbox()

    with visitor.without_csrf():
        again = visitor.create_sandbox()

    assert again.status_code == 201


# --- One transaction ----------------------------------------------------------------------


def count_begins(engine: AsyncEngine) -> list[int]:
    begins: list[int] = []

    def on_begin(connection: Any) -> None:
        begins.append(1)

    event.listen(engine.sync_engine, "begin", on_begin)
    return begins


def test_a_signed_in_request_opens_one_transaction(browser: Browser) -> None:
    browser.start_sandbox()
    engine: AsyncEngine = browser.client.app.state.engine  # type: ignore[attr-defined]
    begins = count_begins(engine)

    response = browser.client.get("/api/v1/me", headers=browser.csrf)

    assert response.status_code == 200
    assert len(begins) == 1


def test_a_refused_signed_in_request_still_opens_only_the_lookup_transaction(
    browser: Browser,
) -> None:
    browser.start_sandbox()
    engine: AsyncEngine = browser.client.app.state.engine  # type: ignore[attr-defined]
    begins = count_begins(engine)

    with browser.without_csrf():
        response = browser.client.get("/api/v1/me")

    assert response.status_code == 403
    assert len(begins) == 1


def probe_app(browser: Browser) -> None:
    """Two routes that report how many connections the request holds while the route runs."""
    app = browser.client.app

    async def one_transaction(signed_in: SignedInDep, request: Request) -> dict[str, int]:
        engine = request.app.state.engine
        return {"checkedOut": engine.sync_engine.pool.checkedout()}

    async def no_transaction(caller: CallerDep, request: Request) -> dict[str, int]:
        engine = request.app.state.engine
        return {"checkedOut": engine.sync_engine.pool.checkedout()}

    app.add_api_route("/api/v1/_probe/signed-in", one_transaction)  # type: ignore[attr-defined]
    app.add_api_route("/api/v1/_probe/caller", no_transaction)  # type: ignore[attr-defined]


def test_signed_in_holds_one_connection_and_the_caller_holds_none_while_the_route_runs(
    browser: Browser,
) -> None:
    browser.start_sandbox()
    probe_app(browser)

    held = browser.client.get("/api/v1/_probe/signed-in", headers=browser.csrf)
    free = browser.client.get("/api/v1/_probe/caller", headers=browser.csrf)

    assert held.json() == {"checkedOut": 1}
    # signed_in_caller closed its transaction before the route ran, so the stream can take its own.
    assert free.json() == {"checkedOut": 0}


def test_the_session_info_names_the_tenant_so_a_later_transaction_is_not_tenantless(
    browser: Browser,
) -> None:
    """The context is set with set_config in the lookup's transaction, and also on the ORM session,
    where the after_begin hook reads it for any transaction the session begins afterward."""
    sandbox = browser.start_sandbox()
    app = browser.client.app

    async def report(signed_in: SignedInDep) -> dict[str, str | None]:
        context = signed_in.db.info.get("tenant")
        people = await signed_in.db.scalar(text("SELECT count(*) FROM people"))
        return {
            "tenantId": None if context is None else str(context.tenant_id),
            "personId": None if context is None else str(context.person_id),
            "people": str(people),
        }

    app.add_api_route("/api/v1/_probe/context", report)  # type: ignore[attr-defined]

    body = browser.client.get("/api/v1/_probe/context", headers=browser.csrf).json()

    assert body["tenantId"] == sandbox["tenant"]["id"]
    assert body["personId"] == sandbox["me"]["id"]
    assert int(body["people"]) > 100


def test_a_session_ended_by_another_tab_is_a_401_not_a_half_finished_request(
    open_browser: OpenBrowser, caplog: pytest.LogCaptureFixture
) -> None:
    tab = open_browser()
    tab.start_sandbox()
    token, csrf = tab.session_token, tab.csrf_token
    tab.client.delete("/api/v1/session", headers={"X-CSRF-Token": csrf})
    caplog.clear()
    caplog.set_level(logging.DEBUG)

    response = tab.client.get("/api/v1/me", headers={**session_cookie(token), "X-CSRF-Token": csrf})

    assert response.status_code == 401
