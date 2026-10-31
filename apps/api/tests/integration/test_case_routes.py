"""The case routes over HTTP, as a browser calls them.

The sandbox is the seeded company: Priya (an employee) opens cases, Marcus is her manager, Dana is
HR, and Mateo is another employee. Four other people already have a case each (Keisha and Chloe
new, Aaliyah in review, Lucia closed). The model transport is the scripted one: "hurt myself" in the
words is a crisis verdict and "harass" is sensitive.
"""

from datetime import date
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.locks import database_now
from app.db.models import Case
from app.db.tenancy import TenantContext, set_is_hr, tenant_session
from app.modules.cases import queries, routes, texts
from app.modules.cases.summary_task import SummaryJob
from tests.integration.conftest import Browser, OpenBrowser, audit_events

pytestmark = pytest.mark.integration

WORDS = "My team lead keeps changing my schedule without telling me."
SSN = "My number is 078-05-1120."
BASE = "/api/v1/cases"
CASE_AUDIT_ACTIONS = {"case.opened", "case.viewed", "case.text.read", "case.status_changed"}


def switch(browser: Browser, persona: str) -> None:
    response = browser.client.put(
        "/api/v1/session/persona", json={"persona": persona}, headers=browser.csrf
    )
    assert response.status_code == 200, response.text


def send(
    browser: Browser, text: str = WORDS, *, submission_id: UUID | None = None, **extra: Any
) -> Any:
    body = {"submissionId": str(submission_id or uuid4()), "category": "pay", "text": text}
    return browser.client.post(BASE, json={**body, **extra}, headers=browser.csrf)


def get(browser: Browser, path: str, **params: Any) -> Any:
    return browser.client.get(f"{BASE}{path}", params=params, headers=browser.csrf)


def opened_case_as_priya(browser: Browser, text: str = WORDS) -> str:
    browser.start_sandbox("priya")
    response = send(browser, text)
    assert response.status_code == 201, response.text
    case_id: str = response.json()["case"]["id"]
    return case_id


def tenant_of(sandbox: dict[str, Any]) -> UUID:
    return UUID(sandbox["tenant"]["id"])


async def case_audit(engine: AsyncEngine, tenant_id: UUID) -> list[str]:
    return [
        e.action for e in await audit_events(engine, tenant_id) if e.action in CASE_AUDIT_ACTIONS
    ]


# --- POST /cases ---


def test_sending_opens_a_case_and_returns_the_status_view(browser: Browser) -> None:
    browser.start_sandbox("priya")

    response = send(browser)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["created"] is True
    assert body["crisisText"] is None
    assert set(body["case"]) == {
        "id",
        "category",
        "status",
        "sentAt",
        "replyBy",
        "statusChangedAt",
    }
    assert (body["case"]["category"], body["case"]["status"]) == ("pay", "new")
    # The screening label is never sent to the person who opened the case.
    assert "screening" not in response.text
    assert WORDS not in response.text


def test_a_repeated_submission_returns_the_same_case_and_schedules_nothing(
    browser: Browser, monkeypatch: pytest.MonkeyPatch
) -> None:
    scheduled: list[SummaryJob] = []
    monkeypatch.setattr(routes, "schedule_summary", lambda _tasks, job: scheduled.append(job))
    browser.start_sandbox("priya")
    submission = uuid4()

    first = send(browser, submission_id=submission)
    again = send(browser, submission_id=submission)

    assert (first.status_code, again.status_code) == (201, 200)
    assert again.json()["case"]["id"] == first.json()["case"]["id"]
    assert again.json()["created"] is False
    # Only the first send asks for a summary.
    assert len(scheduled) == 1


def expected_sent_line(body: dict[str, Any], where: str) -> dict[str, str]:
    """The sent line for the case's own reply-by date, cut from the hashed template."""
    lead, pointer = texts.sent_state_parts(date.fromisoformat(body["case"]["replyBy"]), where=where)
    return {"lead": lead, "pointer": pointer}


def test_a_persons_send_carries_the_sent_line_pointing_to_my_cases(browser: Browser) -> None:
    browser.start_sandbox("priya")

    body = send(browser).json()

    assert body["sentLine"] == expected_sent_line(body, "My cases")
    assert body["sentLine"]["pointer"] == "You can see its status in My cases."


def test_an_hr_persons_send_points_to_cases_since_hr_has_no_my_cases(browser: Browser) -> None:
    browser.start_sandbox("dana")

    body = send(browser).json()

    assert body["sentLine"] == expected_sent_line(body, "Cases")


def test_a_repeated_submission_carries_the_same_sent_line_from_the_cases_own_date(
    browser: Browser,
) -> None:
    browser.start_sandbox("priya")
    submission = uuid4()

    first = send(browser, submission_id=submission).json()
    again = send(browser, submission_id=submission).json()

    assert again["sentLine"] == first["sentLine"] == expected_sent_line(first, "My cases")


def test_the_same_submission_with_other_words_is_a_conflict(browser: Browser) -> None:
    browser.start_sandbox("priya")
    submission = uuid4()
    send(browser, submission_id=submission)

    response = send(browser, "Something else entirely.", submission_id=submission)

    assert response.status_code == 409
    assert "Something else entirely" not in response.text


def test_a_crisis_verdict_saves_the_case_and_returns_the_crisis_text(
    browser: Browser, monkeypatch: pytest.MonkeyPatch
) -> None:
    scheduled: list[SummaryJob] = []
    monkeypatch.setattr(routes, "schedule_summary", lambda _tasks, job: scheduled.append(job))
    browser.start_sandbox("priya")

    response = send(browser, "I want to hurt myself.")

    assert response.status_code == 201
    body = response.json()
    assert "988" in body["crisisText"]
    assert body["case"]["status"] == "new"
    assert "screening" not in response.text
    # No summary is written for a crisis verdict.
    assert scheduled == []


def test_words_over_the_service_limit_get_its_own_problem(browser: Browser) -> None:
    browser.start_sandbox("priya")

    response = send(browser, "a" * 4001)

    assert response.status_code == 422
    assert response.json()["type"] == "case-words-too-long"


def test_a_huge_body_is_refused_at_validation_and_not_echoed(browser: Browser) -> None:
    browser.start_sandbox("priya")

    response = send(browser, "ZEBRA" * 4001)

    assert response.status_code == 422
    assert response.json()["type"] != "case-words-too-long"
    assert "ZEBRA" not in response.text
    assert get(browser, "/mine").json()["items"] == []


def test_a_social_security_number_is_refused_and_not_echoed(browser: Browser) -> None:
    browser.start_sandbox("priya")

    response = send(browser, SSN)

    assert response.status_code == 422
    assert response.json()["type"] == "case-personal-data"
    assert "078" not in response.text
    assert get(browser, "/mine").json()["items"] == []


def test_sending_needs_the_csrf_header_and_a_session(browser: Browser) -> None:
    body = {"submissionId": str(uuid4()), "category": "pay", "text": WORDS}
    assert browser.client.post(BASE, json=body).status_code == 401
    browser.start_sandbox("priya")

    assert browser.client.post(BASE, json=body).status_code == 403


def test_a_summary_is_scheduled_for_a_sensitive_verdict_too(
    browser: Browser, monkeypatch: pytest.MonkeyPatch
) -> None:
    scheduled: list[SummaryJob] = []
    monkeypatch.setattr(routes, "schedule_summary", lambda _tasks, job: scheduled.append(job))
    browser.start_sandbox("priya")

    send(browser, "A coworker said something I would call harassment.")

    assert len(scheduled) == 1


# --- GET /cases/mine and /cases/texts ---


def test_mine_lists_only_the_askers_own_cases_with_no_words(browser: Browser) -> None:
    case_id = opened_case_as_priya(browser)

    mine = get(browser, "/mine")

    assert mine.status_code == 200
    [item] = mine.json()["items"]
    assert item["id"] == case_id
    assert WORDS not in mine.text
    # Marcus (her manager) and a coworker see none of it.
    switch(browser, "marcus")
    assert get(browser, "/mine").json()["items"] == []
    switch(browser, "mateo")
    assert get(browser, "/mine").json()["items"] == []


def test_hr_mine_lists_their_own_cases_not_everyone_s(browser: Browser) -> None:
    browser.start_sandbox("dana")
    assert send(browser).status_code == 201

    items = get(browser, "/mine").json()["items"]

    assert len(items) == 1


async def test_texts_carry_todays_reply_by_date(browser: Browser, app_engine: AsyncEngine) -> None:
    sandbox = browser.start_sandbox("priya")

    response = get(browser, "/texts")

    assert response.status_code == 200
    body = response.json()
    async with tenant_session(
        app_engine, TenantContext(tenant_of(sandbox), UUID(sandbox["me"]["id"]))
    ) as db:
        now = await database_now(db)
        expected = await queries.reply_by_at(db, tenant_of(sandbox), now)
    assert body["replyBy"] == expected.isoformat()
    assert len(body["bullets"]) == 5
    # The waiting-limit line is the API's, so the web app holds no copy that could drift.
    assert body["waitingLimit"] == texts.WAITING_LIMIT_TEXT
    assert any(expected.strftime("%A, %B") in bullet for bullet in body["bullets"])
    # The HR team's contacts come with them, for My cases, which has no panel to carry them.
    names = [contact["name"] for contact in body["hrContacts"]]
    assert "Dana Whitfield" in names
    assert all(contact["workEmail"] for contact in body["hrContacts"])
    # Anyone with a session reads them; no session is a 401.
    browser.client.cookies.clear()
    assert browser.client.get(f"{BASE}/texts").status_code == 401


# --- the fixed paths come before /{id} ---


@pytest.mark.parametrize("path", ["/mine", "/texts", "/counts"])
def test_fixed_paths_are_not_read_as_a_case_id(browser: Browser, path: str) -> None:
    browser.start_sandbox("dana")

    assert get(browser, path).status_code == 200


# --- HR: counts, queue, detail ---


def test_counts_are_for_hr_and_everyone_else_gets_not_found(browser: Browser) -> None:
    browser.start_sandbox("dana")
    seeded = get(browser, "/counts")
    assert seeded.status_code == 200
    assert set(seeded.json()) == {"new", "replyDue"}
    assert seeded.json()["new"] == 2

    for persona in ("priya", "marcus"):
        switch(browser, persona)
        refused = get(browser, "/counts")
        assert refused.status_code == 404
        assert refused.json()["type"] == "case-not-found"


def test_counts_leave_out_hrs_own_cases(browser: Browser) -> None:
    browser.start_sandbox("dana")
    send(browser)

    assert get(browser, "/counts").json()["new"] == 2


def test_the_queue_orders_new_cases_first_by_reply_by_then_the_rest_oldest_first(
    browser: Browser,
) -> None:
    browser.start_sandbox("priya")
    send(browser)
    switch(browser, "dana")

    items = get(browser, "").json()["items"]

    names = [item["givenName"] for item in items]
    assert names[:3] == ["Chloe", "Keisha", "Priya"]
    new = [item for item in items if item["status"] == "new"]
    assert [item["replyBy"] for item in new] == sorted(item["replyBy"] for item in new)
    # Then Lucia (closed, sent 15 business days back) before Aaliyah (in review, 6 back).
    assert names[3:] == ["Lucia", "Aaliyah"]
    rest = items[len(new) :]
    assert [item["sentAt"] for item in rest] == sorted(item["sentAt"] for item in rest)


def test_the_queue_filters_by_status(browser: Browser) -> None:
    browser.start_sandbox("dana")

    def names(status: str) -> list[str]:
        return [item["givenName"] for item in get(browser, "", status=status).json()["items"]]

    assert names("new") == ["Chloe", "Keisha"]
    assert names("in_review") == ["Aaliyah"]
    assert names("closed") == ["Lucia"]
    # `open` is new and in review.
    assert sorted(names("open")) == ["Aaliyah", "Chloe", "Keisha"]


def test_the_queue_pages_with_a_cursor(browser: Browser, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(queries, "PAGE_SIZE", 2)
    browser.start_sandbox("dana")

    first = get(browser, "").json()
    second = get(browser, "", cursor=first["nextCursor"]).json()

    assert first["nextCursor"] is not None
    assert second["nextCursor"] is None
    assert [item["givenName"] for page in (first, second) for item in page["items"]] == [
        "Chloe",
        "Keisha",
        "Lucia",
        "Aaliyah",
    ]


def test_a_made_up_cursor_is_a_422_not_a_500(browser: Browser) -> None:
    browser.start_sandbox("dana")

    response = get(browser, "", cursor="not-a-cursor")

    assert response.status_code == 422


def test_the_queue_shows_the_safety_checks_fact_and_no_words(browser: Browser) -> None:
    browser.start_sandbox("priya")
    send(browser, "I want to hurt myself.")
    send(browser)
    switch(browser, "dana")

    response = get(browser, "")

    items = response.json()["items"]
    priya = [item for item in items if item["givenName"] == "Priya"]
    assert sorted(item["crisis"] for item in priya) == [False, True]
    assert all(item["crisis"] is False for item in items if item["givenName"] != "Priya")
    assert "hurt myself" not in response.text
    assert WORDS not in response.text
    for key in ("givenName", "familyName", "title", "locationName", "sentAt", "replyBy", "isOwn"):
        assert key in items[0]
    assert "screening" not in items[0]


def test_the_queue_is_hr_only(browser: Browser) -> None:
    browser.start_sandbox("priya")
    send(browser)

    for persona in ("priya", "marcus", "mateo"):
        switch(browser, persona)
        response = get(browser, "")
        assert response.status_code == 404
        assert response.json()["type"] == "case-not-found"


def test_the_detail_holds_no_words(browser: Browser) -> None:
    browser.start_sandbox("priya")
    case_id = send(browser).json()["case"]["id"]
    switch(browser, "dana")

    response = get(browser, f"/{case_id}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == case_id
    assert (body["givenName"], body["familyName"]) == ("Priya", "Raman")
    assert body["screening"] == "ordinary"
    # The scripted summarizer wrote its summary in the background, right after the send.
    assert body["summary"]["status"] == "written"
    assert [entry["kind"] for entry in body["timeline"]] == ["opened", "summary_written"]
    assert WORDS not in response.text
    for key in ("text", "words"):
        assert key not in body
    assert body["workEmail"] == "priya.raman@juniperrow.example"


async def test_the_detail_is_not_audited(browser: Browser, app_engine: AsyncEngine) -> None:
    sandbox = browser.start_sandbox("priya")
    case_id = send(browser).json()["case"]["id"]
    switch(browser, "dana")

    get(browser, f"/{case_id}")

    assert await case_audit(app_engine, tenant_of(sandbox)) == ["case.opened"]


def test_a_case_someone_cannot_see_is_always_not_found_never_forbidden(
    open_browser: OpenBrowser,
) -> None:
    priya = open_browser()
    case_id = opened_case_as_priya(priya)
    paths = [
        ("GET", f"/{case_id}", None),
        ("GET", f"/{case_id}/summary", None),
        ("GET", f"/{case_id}/text", None),
        ("POST", f"/{case_id}/status", {"to": "in_review"}),
    ]
    other_sandbox = open_browser()
    other_sandbox.start_sandbox("dana")

    for actor in ("priya", "marcus", "mateo"):
        switch(priya, actor)
        for method, path, body in paths:
            response = priya.client.request(method, f"{BASE}{path}", json=body, headers=priya.csrf)
            assert response.status_code == 404, (actor, method, path, response.text)
            assert response.json()["type"] == "case-not-found"
            assert response.headers["Cache-Control"] == "no-store"
    # HR in another sandbox, and an ID that is not a case at all, get the same answer.
    for path_id in (case_id, str(uuid4())):
        for method, path, body in paths:
            response = other_sandbox.client.request(
                method,
                f"{BASE}{path.replace(case_id, path_id)}",
                json=body,
                headers=other_sandbox.csrf,
            )
            assert response.status_code == 404, (method, path, response.text)
            assert response.json()["type"] == "case-not-found"
    assert get(other_sandbox, "").json()["items"] != []
    assert case_id not in get(other_sandbox, "").text


def test_the_opener_sees_their_own_status_but_never_the_detail(browser: Browser) -> None:
    case_id = opened_case_as_priya(browser)

    # The detail is HR's: the person has "mine".
    assert get(browser, f"/{case_id}").status_code == 404


# --- the audited reads ---


async def test_the_summary_and_the_words_are_audited_no_store_reads(
    browser: Browser, app_engine: AsyncEngine
) -> None:
    sandbox = browser.start_sandbox("priya")
    case_id = send(browser).json()["case"]["id"]
    switch(browser, "dana")

    text = get(browser, f"/{case_id}/text")
    summary = get(browser, f"/{case_id}/summary")

    assert text.status_code == 200, text.text
    assert text.json() == {"text": WORDS}
    assert summary.status_code == 200, summary.text
    assert summary.json()["status"] == "written"
    for response in (text, summary):
        assert response.headers["Cache-Control"] == "no-store"
    assert await case_audit(app_engine, tenant_of(sandbox)) == [
        "case.opened",
        "case.text.read",
        "case.viewed",
    ]
    detail = get(browser, f"/{case_id}").json()
    assert [entry["kind"] for entry in detail["timeline"]] == [
        "opened",
        "summary_written",
        "text_read",
        "viewed",
    ]


async def test_an_audited_read_without_the_header_is_refused_and_leaves_no_trace(
    browser: Browser, app_engine: AsyncEngine, caplog: pytest.LogCaptureFixture
) -> None:
    sandbox = browser.start_sandbox("priya")
    case_id = send(browser).json()["case"]["id"]
    switch(browser, "dana")

    for suffix in ("text", "summary"):
        missing = browser.client.get(f"{BASE}/{case_id}/{suffix}")
        wrong = browser.client.get(f"{BASE}/{case_id}/{suffix}", headers={"X-CSRF-Token": "wrong"})
        for response in (missing, wrong):
            assert response.status_code == 403
            assert response.headers["Cache-Control"] == "no-store"
            assert WORDS not in response.text

    assert await case_audit(app_engine, tenant_of(sandbox)) == ["case.opened"]
    rejected = [r for r in caplog.records if r.getMessage() == "security.csrf_rejected"]
    assert len(rejected) == 4
    # And with the header the same read passes.
    assert get(browser, f"/{case_id}/text").status_code == 200


def test_hr_cannot_read_or_act_on_their_own_case(browser: Browser) -> None:
    browser.start_sandbox("dana")
    case_id = send(browser).json()["case"]["id"]

    for path in (f"/{case_id}/text", f"/{case_id}/summary"):
        response = get(browser, path)
        assert response.status_code == 403
        assert response.json()["type"] == "case-own"
        assert response.headers["Cache-Control"] == "no-store"
    status = browser.client.post(
        f"{BASE}/{case_id}/status", json={"to": "in_review"}, headers=browser.csrf
    )
    assert (status.status_code, status.json()["type"]) == (403, "case-own")
    # The queue lists it, with no actions and no verdict.
    own = [item for item in get(browser, "").json()["items"] if item["id"] == case_id]
    assert [(item["isOwn"], item["crisis"]) for item in own] == [(True, None)]


def test_a_problem_never_echoes_the_words(browser: Browser) -> None:
    case_id = opened_case_as_priya(browser, "CANARY-lantern private words")

    for method, path, body in (
        ("GET", f"/{case_id}/text", None),
        ("POST", f"/{case_id}/status", {"to": "closed"}),
    ):
        response = browser.client.request(method, f"{BASE}{path}", json=body, headers=browser.csrf)
        assert response.status_code == 404
        assert "CANARY" not in response.text


# --- changing the status ---


async def test_a_status_change_before_reading_the_words_is_words_not_read(
    browser: Browser, app_engine: AsyncEngine
) -> None:
    sandbox = browser.start_sandbox("priya")
    case_id = send(browser).json()["case"]["id"]
    switch(browser, "dana")

    refused = browser.client.post(
        f"{BASE}/{case_id}/status", json={"to": "in_review"}, headers=browser.csrf
    )

    assert refused.status_code == 409
    assert refused.json()["type"] == "words-not-read"
    # Reading the summary is not reading the words.
    get(browser, f"/{case_id}/summary")
    assert (
        browser.client.post(
            f"{BASE}/{case_id}/status", json={"to": "in_review"}, headers=browser.csrf
        ).status_code
        == 409
    )
    get(browser, f"/{case_id}/text")

    moved = browser.client.post(
        f"{BASE}/{case_id}/status", json={"to": "in_review"}, headers=browser.csrf
    )

    assert moved.status_code == 200, moved.text
    assert moved.json()["status"] == "in_review"
    assert "case.status_changed" in await case_audit(app_engine, tenant_of(sandbox))
    # Status goes one way: back to new is refused by the database's rule.
    back = browser.client.post(f"{BASE}/{case_id}/status", json={"to": "new"}, headers=browser.csrf)
    assert back.status_code == 409
    assert back.json()["type"] == "case-status-refused"
    # The person sees the new status in "mine".
    switch(browser, "priya")
    assert get(browser, "/mine").json()["items"][0]["status"] == "in_review"


def test_a_status_change_needs_the_csrf_header(browser: Browser) -> None:
    case_id = opened_case_as_priya(browser)
    switch(browser, "dana")
    get(browser, f"/{case_id}/text")

    response = browser.client.post(f"{BASE}/{case_id}/status", json={"to": "closed"})

    assert response.status_code == 403
    assert response.json()["detail"] == "The CSRF token is missing or wrong."


async def test_the_database_holds_the_case_the_route_opened(
    browser: Browser, app_engine: AsyncEngine
) -> None:
    sandbox = browser.start_sandbox("priya")
    case_id = send(browser).json()["case"]["id"]

    async with tenant_session(app_engine, TenantContext(tenant_of(sandbox), None)) as db:
        await set_is_hr(db, True)
        row = (await db.scalars(select(Case).where(Case.id == UUID(case_id)))).one()
    assert WORDS.encode() not in row.text_ciphertext


# --- a bad enum value is the route's own validation 422 ---
# The service still checks its inputs (`case-invalid`, tested in test_case_service.py) for callers
# that skip the routes. The routes type these values, so the generated client gets them typed.


def assert_validation_problem(response: Any, field: str, bad_value: str) -> None:
    assert response.status_code == 422
    body = response.json()
    assert body["status"] == 422
    assert body["detail"] == "The request did not pass validation."
    assert [error["loc"][-1] for error in body["errors"]] == [field]
    assert bad_value not in response.text


def test_a_bad_category_is_a_validation_422_and_opens_nothing(browser: Browser) -> None:
    browser.start_sandbox("priya")

    response = send(browser, category="not_a_category")

    assert_validation_problem(response, "category", "not_a_category")
    assert get(browser, "/mine").json()["items"] == []


def test_a_bad_status_to_is_a_validation_422_not_masked_by_words_not_read(
    browser: Browser,
) -> None:
    case_id = opened_case_as_priya(browser)
    switch(browser, "dana")
    get(browser, f"/{case_id}/text")

    response = browser.client.post(
        f"{BASE}/{case_id}/status", json={"to": "archived"}, headers=browser.csrf
    )

    assert_validation_problem(response, "to", "archived")


def test_a_bad_queue_status_filter_is_a_validation_422_for_hr(browser: Browser) -> None:
    browser.start_sandbox("dana")

    assert_validation_problem(get(browser, "", status="bogus"), "status", "bogus")


def test_a_bad_queue_filter_from_a_non_hr_caller_reveals_nothing_more(browser: Browser) -> None:
    browser.start_sandbox("priya")

    response = get(browser, "", status="bogus")

    # Validation runs before the HR check, so the answer is the same 422 HR gets. It says nothing
    # about the caller's role, and the queue's existence is not secret.
    assert_validation_problem(response, "status", "bogus")
