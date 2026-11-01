"""The directory and private details over HTTP: the permission matrix, isolation, and paging."""

import logging
from collections.abc import Mapping
from typing import Any
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

    response = browser.client.get(path(target_id, kind), headers=browser.csrf)

    assert response.status_code == status_code, response.text
    if status_code == 200:
        expected = CARD_FIELDS if kind == "directory" else PRIVATE_FIELDS
        assert set(response.json()) == expected


async def test_hr_reading_private_details_is_audited_by_field_name_only(
    browser: Browser, app_engine: AsyncEngine
) -> None:
    sandbox = browser.start_sandbox("dana")
    leo = person_id(sandbox, "leo")

    response = browser.client.get(path(leo, "private"), headers=browser.csrf)

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

    response = browser.client.get(path(leo, "private"), headers=browser.csrf)

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
        response = mine.client.get(path(target_id, kind), headers=mine.csrf)
        assert response.status_code == 404, response.text
        assert response.json()["detail"] == "No such person in this company."


def test_without_permission_a_colleague_and_a_missing_id_look_the_same(browser: Browser) -> None:
    sandbox = browser.start_sandbox("priya")

    responses = [
        browser.client.get(path(target_id, "private"), headers=browser.csrf)
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
    assert [len(page) for page in pages] == [50, 50, 45]
    assert len({person["id"] for person in people}) == 145
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
    assert set(card["location"]) == {"id", "code", "name", "city", "state", "timezone"}
    assert set(card["manager"]) == {"id", "givenName", "familyName"}


def test_priyas_card_carries_her_locations_timezone(browser: Browser) -> None:
    browser.start_sandbox("priya")

    me = browser.client.get("/api/v1/me").json()

    assert me["location"]["timezone"] == "America/Los_Angeles"


def test_a_location_carries_its_handbook_code(browser: Browser) -> None:
    # The handbook's audiences name locations by code (oak, den, aus, atl), so the page can compare.
    browser.start_sandbox("priya")
    assert browser.client.get("/api/v1/me").json()["location"]["code"] == "oak"

    browser.start_sandbox("mateo")
    assert browser.client.get("/api/v1/me").json()["location"]["code"] == "aus"


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
        path(person_id(sandbox, "leo"), "private"), headers={**fetch_metadata, **browser.csrf}
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
    headers = {**session_cookie(signed_in.session_token), **signed_in.csrf}
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
        response = browser.client.get(
            path(person_id(sandbox, "leo"), "private"), headers=browser.csrf
        )
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


def get_all(
    browser: Browser, params: Mapping[str, str | int] | None = None
) -> list[dict[str, Any]]:
    """Every card the directory lists for these filters, read at the largest page size."""
    cards: list[dict[str, Any]] = []
    cursor: str | None = None
    while True:
        page_params: dict[str, str | int] = {"limit": 100, **(params or {})}
        if cursor is not None:
            page_params["cursor"] = cursor
        response = browser.client.get("/api/v1/people", params=page_params)
        assert response.status_code == 200, response.text
        cards.extend(response.json()["items"])
        cursor = response.json()["nextCursor"]
        if cursor is None:
            return cards


def get_facets(browser: Browser, params: dict[str, str] | None = None) -> dict[str, Any]:
    response = browser.client.get("/api/v1/people/facets", params=params)
    assert response.status_code == 200, response.text
    facets: dict[str, Any] = response.json()
    return facets


def test_each_filter_narrows_the_list_and_the_facets_agree(browser: Browser) -> None:
    browser.start_sandbox("marcus")
    me = browser.client.get("/api/v1/me").json()
    location, department = me["location"]["id"], me["department"]["id"]
    cases: list[dict[str, str]] = [
        {},
        {"q": "manager"},
        {"locationId": location},
        {"departmentId": department},
        {"team": "mine"},
        {"q": "lead", "locationId": location, "departmentId": department},
        {"q": "a", "locationId": location, "team": "mine"},
    ]

    for params in cases:
        cards = get_all(browser, params)
        facets = get_facets(browser, params)

        assert cards, params  # Every case must match someone, or the checks below prove nothing.
        assert facets["total"] == 145
        assert facets["matching"] == len(cards), params
        if "locationId" in params:
            assert {card["location"]["id"] for card in cards} == {location}
        if "departmentId" in params:
            assert {card["department"]["id"] for card in cards} == {department}
        if "q" in params:
            needle = params["q"].lower()
            for card in cards:
                text = " ".join(
                    [card["givenName"], card["familyName"], card["title"], card["workEmail"]]
                )
                assert needle in text.lower()
    assert len(get_all(browser, cases[0])) == 145
    assert len(get_all(browser, cases[2])) < 145
    # The location menu agrees with the list for each location.
    for option in get_facets(browser, cases[1])["locations"]:
        chosen = get_all(browser, {"q": "manager", "locationId": option["id"]})
        assert option["count"] == len(chosen)
    for option in get_facets(browser, cases[2])["departments"]:
        chosen = get_all(browser, {"locationId": location, "departmentId": option["id"]})
        assert option["count"] == len(chosen)


def test_the_facets_have_the_agreed_shape(browser: Browser) -> None:
    browser.start_sandbox("marcus")

    facets = get_facets(browser)

    assert set(facets) == {"total", "matching", "locations", "departments", "myTeam"}
    assert [set(location) for location in facets["locations"]] == [
        {"id", "name", "state", "count"}
    ] * 4
    assert {tuple(sorted(department)) for department in facets["departments"]} == {
        ("count", "id", "name")
    }
    assert [(loc["name"], loc["count"]) for loc in facets["locations"]] == [
        ("Atlanta store", 25),
        ("Austin warehouse", 35),
        ("Denver HQ", 40),
        ("Oakland store", 45),
    ]


def test_marcus_sees_his_team_of_44_and_priya_has_none(open_browser: OpenBrowser) -> None:
    marcus, priya = open_browser(), open_browser()
    marcus.start_sandbox("marcus")
    priya.start_sandbox("priya")

    team = get_all(marcus, {"team": "mine"})
    marcus_facets = get_facets(marcus, {"team": "mine"})
    priyas = priya.client.get("/api/v1/people", params={"team": "mine"})

    assert len(team) == 44
    assert marcus_facets["myTeam"] == marcus_facets["matching"] == 44
    assert get_facets(marcus)["myTeam"] == 44
    assert priyas.status_code == 200
    assert priyas.json() == {"items": [], "nextCursor": None}
    assert get_facets(priya)["myTeam"] is None
    assert get_facets(priya, {"team": "mine"})["matching"] == 0


def test_the_search_is_trimmed_and_limited_to_100_characters(browser: Browser) -> None:
    browser.start_sandbox()
    long_name = "x" * 100

    too_long = browser.client.get("/api/v1/people", params={"q": "x" * 101})
    too_long_facets = browser.client.get("/api/v1/people/facets", params={"q": "x" * 101})
    padded = browser.client.get("/api/v1/people", params={"q": f"  {long_name}  "})
    blank = browser.client.get("/api/v1/people", params={"q": "   ", "limit": 100})
    padded_101 = browser.client.get("/api/v1/people", params={"q": f" {long_name}x "})

    assert [too_long.status_code, too_long_facets.status_code] == [422, 422]
    assert padded.status_code == 200
    assert padded.json()["items"] == []
    assert padded_101.status_code == 422
    assert blank.status_code == 200
    assert len(blank.json()["items"]) == 100
    # The stripped value is what is matched, and a blank search on the facets is no filter.
    marcus = get_all(browser, {"q": "  marcus "})
    assert "Marcus Bell" in {f"{card['givenName']} {card['familyName']}" for card in marcus}
    assert 0 < len(marcus) < 145
    assert get_all(browser, {"q": "  marcus "}) == get_all(browser, {"q": "marcus"})
    blank_facets = get_facets(browser, {"q": "   "})
    assert blank_facets["matching"] == blank_facets["total"] == 145
    assert get_facets(browser, {"q": "  marcus "})["matching"] == len(marcus)


def test_a_search_with_a_nul_byte_is_a_422_not_a_500(browser: Browser) -> None:
    browser.start_sandbox()

    responses = [
        browser.client.get(url, params={"q": "abc\x00x"})
        for url in ("/api/v1/people", "/api/v1/people/facets")
    ]

    assert [response.status_code for response in responses] == [422, 422]
    assert all(
        [error["loc"] for error in response.json()["errors"]] == [["query", "q"]]
        for response in responses
    )


@pytest.mark.parametrize(
    "params", [{"team": "everyone"}, {"locationId": "not-a-uuid"}, {"departmentId": "42"}]
)
def test_a_bad_filter_is_a_422(browser: Browser, params: dict[str, str]) -> None:
    browser.start_sandbox()

    statuses = [
        browser.client.get(url, params=params).status_code
        for url in ("/api/v1/people", "/api/v1/people/facets")
    ]

    assert statuses == [422, 422]


def test_another_sandboxs_location_matches_no_one(open_browser: OpenBrowser) -> None:
    mine, theirs = open_browser(), open_browser()
    mine.start_sandbox("priya")
    theirs.start_sandbox("priya")
    their_location = theirs.client.get("/api/v1/me").json()["location"]["id"]
    their_department = theirs.client.get("/api/v1/me").json()["department"]["id"]

    for params in ({"locationId": their_location}, {"departmentId": their_department}):
        assert get_all(mine, params) == []
        facets = get_facets(mine, params)
        assert (facets["total"], facets["matching"]) == (145, 0)
        # The foreign ID is no menu option either: every option is this sandbox's own.
        assert their_location not in {loc["id"] for loc in facets["locations"]}
        assert their_department not in {dep["id"] for dep in facets["departments"]}


def test_the_facets_route_is_not_taken_for_a_person_id(browser: Browser) -> None:
    browser.start_sandbox()

    response = browser.client.get("/api/v1/people/facets")

    assert response.status_code == 200
    assert "person_id" not in response.text


def test_the_facets_need_a_session(browser: Browser) -> None:
    assert browser.client.get("/api/v1/people/facets").status_code == 401
    assert (
        browser.client.get("/api/v1/people", params={"q": "a", "team": "mine"}).status_code == 401
    )


@pytest.mark.parametrize("header", [None, "wrong-token"])
async def test_an_audited_read_without_the_csrf_header_is_refused_and_writes_no_audit_event(
    browser: Browser,
    app_engine: AsyncEngine,
    caplog: pytest.LogCaptureFixture,
    header: str | None,
) -> None:
    sandbox = browser.start_sandbox("dana")
    headers = {} if header is None else {"X-CSRF-Token": header}

    response = browser.client.get(path(person_id(sandbox, "leo"), "private"), headers=headers)

    assert response.status_code == 403
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["detail"] == "The CSRF token is missing or wrong."
    assert not any(name in response.text for name in PRIVATE_FIELDS)
    events = await audit_events(app_engine, UUID(sandbox["tenant"]["id"]))
    assert [event.action for event in events] == ["sandbox.created"]
    assert [r.getMessage() for r in caplog.records if r.name == "app.security"] == [
        "security.csrf_rejected"
    ]


def test_an_ordinary_read_still_needs_no_csrf_header(browser: Browser) -> None:
    browser.start_sandbox("priya")

    assert browser.client.get("/api/v1/people").status_code == 200
