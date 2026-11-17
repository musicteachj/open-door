"""Starting a sandbox needs a passed Turnstile check, run before anything else. Cloudflare is never
called: the app's verifier is a stub, or the local one for Cloudflare's test keys."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.modules.sandbox import texts
from app.modules.sandbox.turnstile import DUMMY_TOKEN, Verdict
from tests.integration.conftest import Browser, OpenBrowser, session_cookie

pytestmark = pytest.mark.integration


class StubVerifier:
    def __init__(self, verdict: Verdict) -> None:
        self.verdict = verdict
        self.calls: list[tuple[str, str | None]] = []

    async def verify(self, token: str, remote_ip: str | None) -> Verdict:
        self.calls.append((token, remote_ip))
        return self.verdict


async def start_count(owner_engine: AsyncEngine) -> int:
    async with owner_engine.connect() as connection:
        return int(
            (await connection.execute(text("SELECT count(*) FROM sandbox_starts"))).scalar_one()
        )


async def tenant_count(owner_engine: AsyncEngine) -> int:
    async with owner_engine.connect() as connection:
        return int((await connection.execute(text("SELECT count(*) FROM tenants"))).scalar_one())


def test_the_dummy_token_starts_a_sandbox(browser: Browser) -> None:
    response = browser.client.post(
        "/api/v1/sandboxes", json={"persona": "priya", "turnstileToken": DUMMY_TOKEN}
    )
    assert response.status_code == 201, response.text


def test_the_wrong_token_is_refused_with_the_approved_text(browser: Browser) -> None:
    response = browser.client.post(
        "/api/v1/sandboxes", json={"persona": "priya", "turnstileToken": "not-the-dummy"}
    )
    assert response.status_code == 403
    problem = response.json()
    assert problem["type"] == "turnstile-failed"
    assert problem["detail"] == texts.TURNSTILE_FAILED_TEXT


@pytest.mark.parametrize("body", [{"persona": "priya"}, None, {"turnstileToken": 5}])
def test_a_missing_or_malformed_token_is_a_422(browser: Browser, body: object) -> None:
    response = browser.client.post("/api/v1/sandboxes", json=body)
    assert response.status_code == 422


def test_an_oversized_token_is_a_422(browser: Browser) -> None:
    response = browser.client.post("/api/v1/sandboxes", json={"turnstileToken": "x" * 2049})
    assert response.status_code == 422


@pytest.mark.parametrize(
    ("verdict", "status", "kind", "text_"),
    [
        (Verdict.FAILED, 403, "turnstile-failed", texts.TURNSTILE_FAILED_TEXT),
        (Verdict.UNAVAILABLE, 503, "turnstile-unavailable", texts.TURNSTILE_UNAVAILABLE_TEXT),
    ],
)
async def test_a_refused_check_changes_nothing(
    open_browser: OpenBrowser,
    owner_engine: AsyncEngine,
    verdict: Verdict,
    status: int,
    kind: str,
    text_: str,
) -> None:
    visitor = open_browser()
    first = visitor.start_sandbox()
    token = visitor.session_token
    stub = StubVerifier(verdict)
    visitor.client.app.state.turnstile = stub  # type: ignore[attr-defined]
    starts, tenants = await start_count(owner_engine), await tenant_count(owner_engine)

    response = visitor.create_sandbox()

    assert response.status_code == status
    assert response.json()["type"] == kind
    assert response.json()["detail"] == text_
    assert [call[0] for call in stub.calls] == [DUMMY_TOKEN]
    # No row, no sandbox, and the visitor's current session is still alive.
    assert await start_count(owner_engine) == starts
    assert await tenant_count(owner_engine) == tenants
    still = visitor.client.get("/api/v1/me", headers=session_cookie(token))
    assert still.status_code == 200
    assert still.json()["id"] == first["me"]["id"]
