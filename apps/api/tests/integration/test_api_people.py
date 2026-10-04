"""The directory and private details over HTTP: the permission matrix, isolation, and paging."""

import logging
from uuid import UUID, uuid4, uuid5

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.orm import Session

from app.core.logging import JsonFormatter
from app.db.tenancy import TenantContext
from app.modules.people import routes
from app.modules.people.queries import DirectoryCursor
from app.policy import Action, Actor, PersonResource, can
from tests.integration.conftest import Browser, OpenBrowser, audit_events, session_cookie
from tests.test_people_schemas import UNSTORABLE_NAMES

pytestmark = pytest.mark.integration

CARD_FIELDS = {
    "id",
    "givenName",
    "familyName",
    "title",
    "department",
    "location",
    "manager",
    "workEmail",
}
PRIVATE_FIELDS = {"personalEmail", "phone", "homeAddress", "dateOfBirth"}
ME_ONLY_FIELDS = {"employmentType", "isManager", "isHrAdmin", "personaKey", "tenantExpiresAt"}

# Each persona against themselves, Leo (one of Marcus's reports), and Dana (HR). Marcus is Leo's
# manager, and still may not read his private details.
PRIVATE_MATRIX = {
    ("priya", "self"): 200,
    ("priya", "leo"): 403,
    ("priya", "dana"): 403,
    ("mateo", "self"): 200,
    ("mateo", "leo"): 403,
    ("mateo", "dana"): 403,
    ("marcus", "self"): 200,
    ("marcus", "leo"): 403,
    ("marcus", "dana"): 403,
    ("dana", "self"): 200,
    ("dana", "leo"): 200,
    ("dana", "dana"): 200,
}
MATRIX = [
    (persona, target, kind, 200 if kind == "directory" else private)
    for (persona, target), private in PRIVATE_MATRIX.items()
    for kind in ("directory", "private")
]


def person_id(sandbox: dict[str, object], key: str) -> UUID:
    """A seeded person's ID in this sandbox. `self` is the persona signed in."""
    me = sandbox["me"]
    assert isinstance(me, dict)
    tenant = sandbox["tenant"]
    assert isinstance(tenant, dict)
    if key == "self":
        return UUID(me["id"])
    return uuid5(UUID(tenant["id"]), f"person:{key}")


def path(target_id: UUID, kind: str) -> str:
    return f"/api/v1/people/{target_id}" + ("/private" if kind == "private" else "")


@pytest.mark.parametrize(("persona", "target", "kind", "status_code"), MATRIX)
def test_the_permission_matrix(
    browser: Browser, persona: str, target: str, kind: str, status_code: int
) -> None:
    sandbox = browser.start_sandbox(persona)
    target_id = person_id(sandbox, target)

    response = browser.client.get(path(target_id, kind))

    assert response.status_code == status_code, response.text
    if status_code == 200:
        expected = CARD_FIELDS if kind == "directory" else PRIVATE_FIELDS
        assert set(response.json()) == expected


async def test_hr_reading_private_details_is_audited_by_field_name_only(
    browser: Browser, app_engine: AsyncEngine
) -> None:
    sandbox = browser.start_sandbox("dana")
    leo = person_id(sandbox, "leo")

    response = browser.client.get(path(leo, "private"))

    assert response.status_code == 200
    [read] = [
        event
        for event in await audit_events(app_engine, UUID(sandbox["tenant"]["id"]))
        if event.action == "person_private.read"
    ]
    assert (read.actor_person_id, read.via, read.target_type, read.target_id) == (
        person_id(sandbox, "self"),
        "ui",
        "person",
        leo,
    )
    assert read.after == {"fields": sorted(PRIVATE_FIELDS)}
    assert read.request_id == response.headers["X-Request-ID"]
    for value in response.json().values():
        assert value not in str(read.after)


async def test_a_denied_read_is_logged_and_never_audited(
    browser: Browser, app_engine: AsyncEngine, caplog: pytest.LogCaptureFixture
) -> None:
    sandbox = browser.start_sandbox("marcus")
    leo = person_id(sandbox, "leo")

    response = browser.client.get(path(leo, "private"))

    assert response.status_code == 403
    assert response.headers["content-type"] == "application/problem+json"
    events = await audit_events(app_engine, UUID(sandbox["tenant"]["id"]))
    assert [event.action for event in events] == ["sandbox.created"]
    [record] = [record for record in caplog.records if record.name == "app.security"]
    assert record.levelno == logging.WARNING
    assert record.getMessage() == "security.authz_denied"
    fields = record.__dict__["fields"]
    assert (fields["reason"], fields["tenantId"], fields["actorId"], fields["targetId"]) == (
        "person_private.read",
        sandbox["tenant"]["id"],
        sandbox["me"]["id"],
        str(leo),
    )
    assert record.__dict__["request_id"] == response.headers["X-Request-ID"]
    line = JsonFormatter().format(record)
    assert browser.session_token not in line
    assert browser.csrf_token not in line


@pytest.mark.parametrize(("persona", "kind"), [("priya", "directory"), ("dana", "private")])
def test_a_person_from_another_sandbox_is_not_found(
    open_browser: OpenBrowser, persona: str, kind: str
) -> None:
    mine, theirs = open_browser(), open_browser()
    mine.start_sandbox(persona)
    other = theirs.start_sandbox("dana")

    for target_id in (person_id(other, "leo"), person_id(other, "self"), uuid4()):
        response = mine.client.get(path(target_id, kind))
        assert response.status_code == 404, response.text
        assert response.json()["detail"] == "No such person in this company."


def test_without_permission_a_colleague_and_a_missing_id_look_the_same(browser: Browser) -> None:
    sandbox = browser.start_sandbox("priya")

    responses = [
        browser.client.get(path(target_id, "private"))
        for target_id in (person_id(sandbox, "leo"), uuid4())
    ]

    # The policy layer answers before any lookup, so a 403 never reveals whether someone exists.
    assert [response.status_code for response in responses] == [403, 403]
    assert responses[0].json()["detail"] == responses[1].json()["detail"]


def test_the_directory_pages_through_everyone_in_order(browser: Browser) -> None:
    browser.start_sandbox()

    pages: list[list[dict[str, object]]] = []
    cursor: str | None = None
    while True:
        params = {} if cursor is None else {"cursor": cursor}
        response = browser.client.get("/api/v1/people", params=params)
        assert response.status_code == 200
        body = response.json()
        pages.append(body["items"])
        cursor = body["nextCursor"]
        if cursor is None:
            break

    people = [person for page in pages for person in page]
    assert [len(page) for page in pages] == [50, 50, 20]
    assert len({person["id"] for person in people}) == 120
    keys = [(p["familyName"], p["givenName"], p["id"]) for p in people]
    assert keys == sorted(keys)
    assert all(set(person) == CARD_FIELDS for person in people)


def test_the_page_size_can_be_set_up_to_100(browser: Browser) -> None:
    browser.start_sandbox()

    sizes = [
        len(browser.client.get("/api/v1/people", params={"limit": limit}).json()["items"])
        for limit in (1, 100)
    ]
    refused = [
        browser.client.get("/api/v1/people", params=params).status_code
        for params in ({"limit": 0}, {"limit": 101}, {"cursor": "not-a-cursor"})
    ]

    assert sizes == [1, 100]
    assert refused == [422, 422, 422]


def test_the_directory_shows_only_the_cards_fields(browser: Browser) -> None:
    sandbox = browser.start_sandbox("dana")
    leo = person_id(sandbox, "leo")

    listed = browser.client.get("/api/v1/people").json()["items"]
    card = browser.client.get(path(leo, "directory")).json()
    me = browser.client.get("/api/v1/me").json()

    forbidden = ME_ONLY_FIELDS | PRIVATE_FIELDS | {"hireDate", "managerId", "tenantId"}
    for shown in [*listed, card]:
        assert set(shown) == CARD_FIELDS
        assert forbidden.isdisjoint(shown)
    assert set(me) == CARD_FIELDS | ME_ONLY_FIELDS
    assert set(card["department"]) == {"id", "name"}
    assert set(card["location"]) == {"id", "name", "state"}
    assert set(card["manager"]) == {"id", "givenName", "familyName"}


def test_the_people_endpoints_need_a_session(browser: Browser) -> None:
    some_id = uuid4()

    statuses = [
        browser.client.get(url).status_code
        for url in ("/api/v1/people", path(some_id, "directory"), path(some_id, "private"))
    ]

    assert statuses == [401, 401, 401]


@pytest.mark.parametrize("name", UNSTORABLE_NAMES)
def test_a_cursor_postgres_cannot_compare_is_a_422_not_a_500(
    open_browser: OpenBrowser, name: str
) -> None:
    browser = open_browser(raise_server_exceptions=False)
    browser.start_sandbox()
    cursors = [
        DirectoryCursor(name, "Mina", uuid4()).encode(),
        DirectoryCursor("Abbott", name, uuid4()).encode(),
    ]

    responses = [
        browser.client.get("/api/v1/people", params={"cursor": cursor}) for cursor in cursors
    ]

    assert [response.status_code for response in responses] == [422, 422]
    assert {response.json()["detail"] for response in responses} == {
        "The cursor is not one this API issued."
    }


@pytest.mark.parametrize(
    "fetch_metadata",
    [
        # A link, window.open, or location change on another site: SameSite=Lax sends the cookie.
        {
            "Sec-Fetch-Site": "cross-site",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Dest": "document",
        },
        # An <img> on a sibling subdomain: same-site, so the cookie goes on subresources too.
        {"Sec-Fetch-Site": "same-site", "Sec-Fetch-Mode": "no-cors", "Sec-Fetch-Dest": "image"},
    ],
)
async def test_another_site_cannot_make_hr_read_private_details(
    browser: Browser, app_engine: AsyncEngine, fetch_metadata: dict[str, str]
) -> None:
    sandbox = browser.start_sandbox("dana")

    response = browser.client.get(
        path(person_id(sandbox, "leo"), "private"), headers=fetch_metadata
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Requests to the API must come from the Open Door app."
    events = await audit_events(app_engine, UUID(sandbox["tenant"]["id"]))
    assert [event.action for event in events] == ["sandbox.created"]


@pytest.mark.parametrize("site", ["same-origin", "none", None])
def test_the_app_a_typed_url_and_a_script_can_still_read_private_details(
    open_browser: OpenBrowser, site: str | None
) -> None:
    signed_in = open_browser()
    sandbox = signed_in.start_sandbox("dana")
    # This browser sends no Sec-Fetch-Site of its own, so `None` means the header is absent.
    reader = open_browser(same_origin_header=False)
    headers = session_cookie(signed_in.session_token)
    if site is not None:
        headers["Sec-Fetch-Site"] = site

    response = reader.client.get(path(person_id(sandbox, "leo"), "private"), headers=headers)

    assert response.status_code == 200, response.text
    assert set(response.json()) == PRIVATE_FIELDS


async def test_private_details_are_never_sent_unless_their_audit_row_commits(
    open_browser: OpenBrowser, app_engine: AsyncEngine
) -> None:
    browser = open_browser(raise_server_exceptions=False)
    sandbox = browser.start_sandbox("dana")

    def fail_the_requests_commit(session: Session) -> None:
        # Only the signed-in request's transaction is scoped to a tenant here. The session lookup
        # before it has no tenant, so it commits normally.
        context = session.info.get("tenant")
        if isinstance(context, TenantContext) and context.tenant_id is not None:
            msg = "simulated commit failure"
            raise RuntimeError(msg)

    event.listen(Session, "before_commit", fail_the_requests_commit)
    try:
        response = browser.client.get(path(person_id(sandbox, "leo"), "private"))
    finally:
        event.remove(Session, "before_commit", fail_the_requests_commit)

    # The read and its audit row commit together, before the response is sent.
    assert response.status_code == 500
    assert response.headers["content-type"] == "application/problem+json"
    assert not any(name in response.text for name in PRIVATE_FIELDS)
    events = await audit_events(app_engine, UUID(sandbox["tenant"]["id"]))
    assert [audited.action for audited in events] == ["sandbox.created"]


def test_the_list_asks_the_policy_about_each_card_and_pages_past_hidden_people(
    browser: Browser, monkeypatch: pytest.MonkeyPatch
) -> None:
    def read_pages(limit: int) -> list[list[UUID]]:
        """Every page of the directory, until there is no next cursor."""
        pages: list[list[UUID]] = []
        cursor: str | None = None
        while True:
            params: dict[str, str | int] = {"limit": limit}
            if cursor is not None:
                params["cursor"] = cursor
            body = browser.client.get("/api/v1/people", params=params).json()
            pages.append([UUID(card["id"]) for card in body["items"]])
            cursor = body["nextCursor"]
            if cursor is None:
                return pages

    browser.start_sandbox()
    everyone = [person for page in read_pages(100) for person in page]
    # Hide the first two people, which is a whole page at a limit of 2, and the fifth, which starts
    # the third page. A page can then be empty, and a page can be only partly hidden.
    hidden = {everyone[0], everyone[1], everyone[4]}

    def can_except_hidden(actor: Actor, action: Action, target: PersonResource) -> bool:
        return target.person_id not in hidden and can(actor, action, target)

    monkeypatch.setattr(routes, "can", can_except_hidden)

    pages = read_pages(2)

    shown = [person for page in pages for person in page]
    assert shown == [person for person in everyone if person not in hidden]
    # The cursor continues from the last row read, not the last card shown.
    assert pages[:3] == [[], [everyone[2], everyone[3]], [everyone[5]]]
