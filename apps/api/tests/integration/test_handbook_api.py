"""The handbook over HTTP: the list, a section, a passage, and full-text search."""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.integration.conftest import Browser, OpenBrowser

pytestmark = pytest.mark.integration

SUMMARY_FIELDS = {
    "id",
    "title",
    "kind",
    "chapter",
    "addendumState",
    "groupName",
    "audience",
    "audienceLabel",
    "appliesToMe",
    "lastUpdated",
}


def signed_in(browser: Browser, persona: str) -> Browser:
    browser.start_sandbox(persona)
    return browser


def sections_by_id(browser: Browser) -> dict[str, dict[str, Any]]:
    response = browser.client.get("/api/v1/handbook")
    assert response.status_code == 200, response.text
    return {section["id"]: section for section in response.json()["sections"]}


# Priya: California, salaried. Mateo: Texas, hourly. Dana: Colorado, salaried.
APPLIES = [
    ("priya", "CA-4.3", True),
    ("priya", "CO-4.3", False),
    ("priya", "3.2", False),
    ("priya", "4.2", True),
    ("mateo", "CA-4.3", False),
    ("mateo", "CO-4.3", False),
    ("mateo", "3.2", True),
    ("mateo", "4.2", True),
    ("dana", "CA-4.3", False),
    ("dana", "CO-4.3", True),
    ("dana", "3.2", False),
    ("dana", "4.2", True),
]


def test_the_list_has_the_version_every_section_in_order_and_the_group_names(
    browser: Browser,
) -> None:
    signed_in(browser, "priya")
    body = browser.client.get("/api/v1/handbook").json()

    assert set(body) == {"version", "chapters", "addenda", "sections"}
    assert set(body["version"]) == {"label", "title", "updatedOn"}
    assert body["version"]["title"] == "Juniper Row Employee Handbook"
    assert body["chapters"]["4"] == "Time off"
    assert body["addenda"]["CA"] == "California addendum"
    sections = body["sections"]
    assert all(set(section) == SUMMARY_FIELDS for section in sections)
    ids = [section["id"] for section in sections]
    # Company sections by number, then each state's addendum.
    assert ids.index("1.1") < ids.index("4.3") < ids.index("CA-4.3")
    assert [section["kind"] for section in sections] == sorted(
        (section["kind"] for section in sections), key=lambda kind: kind == "addendum"
    )
    sick = next(section for section in sections if section["id"] == "CA-4.3")
    assert sick["kind"] == "addendum"
    assert sick["chapter"] is None
    assert sick["addendumState"] == "CA"
    assert sick["groupName"] == "California addendum"
    assert sick["audience"] == {"states": ["CA"], "employmentTypes": [], "locations": []}
    assert sick["audienceLabel"] == "California employees"
    assert sick["lastUpdated"] == "2026-10-07"
    company = next(section for section in sections if section["id"] == "4.3")
    assert (company["chapter"], company["groupName"]) == (4, "Time off")
    assert company["audienceLabel"] == "Everyone"


@pytest.mark.parametrize(("persona", "section_id", "expected"), APPLIES)
def test_applies_to_me_comes_from_the_signed_in_person(
    browser: Browser, persona: str, section_id: str, expected: bool
) -> None:
    signed_in(browser, persona)

    listed = sections_by_id(browser)[section_id]["appliesToMe"]
    detail = browser.client.get(f"/api/v1/handbook/sections/{section_id}").json()["appliesToMe"]

    assert listed is expected
    assert detail is expected


def test_a_section_has_its_text_related_sections_sources_and_neighbors(browser: Browser) -> None:
    signed_in(browser, "priya")

    addendum = browser.client.get("/api/v1/handbook/sections/CA-4.3").json()
    assert set(addendum) == SUMMARY_FIELDS | {
        "blocks",
        "sources",
        "supplements",
        "supplementedBy",
        "previous",
        "next",
    }
    assert addendum["supplements"] == {
        "id": "4.3",
        "title": "Sick leave",
        "audienceLabel": "Everyone",
        "appliesToMe": True,
    }
    assert addendum["supplementedBy"] == []
    assert addendum["sources"]
    assert addendum["previous"]["id"]
    assert addendum["next"]["title"]
    heading = next(block for block in addendum["blocks"] if block["type"] == "heading")
    assert set(heading) == {"type", "level", "text"}
    passage = next(block for block in addendum["blocks"] if block["type"] == "passage")
    assert passage["id"] == "p1"
    assert passage["kind"] == "paragraph"
    assert set(passage) == {"id", "type", "kind", "inlines"}
    assert set(passage["inlines"][0]) == {"text", "bold", "italic", "linkSectionId"}

    company = browser.client.get("/api/v1/handbook/sections/4.3").json()
    assert company["supplements"] is None
    assert {ref["id"] for ref in company["supplementedBy"]} == {"CA-4.3", "CO-4.3"}
    by_id = {ref["id"]: ref for ref in company["supplementedBy"]}
    assert by_id["CA-4.3"]["appliesToMe"] is True
    assert by_id["CO-4.3"]["appliesToMe"] is False
    assert set(by_id["CA-4.3"]) == {"id", "title", "audienceLabel", "appliesToMe"}


def test_the_first_and_last_sections_have_one_neighbor(browser: Browser) -> None:
    signed_in(browser, "priya")
    ids = list(sections_by_id(browser))

    first = browser.client.get(f"/api/v1/handbook/sections/{ids[0]}").json()
    last = browser.client.get(f"/api/v1/handbook/sections/{ids[-1]}").json()

    assert first["previous"] is None
    assert first["next"] == {"id": ids[1], "title": sections_by_id(browser)[ids[1]]["title"]}
    assert last["next"] is None
    assert last["previous"]["id"] == ids[-2]


def test_a_passage_comes_with_its_neighbors_and_its_sections_header(browser: Browser) -> None:
    signed_in(browser, "priya")

    body = browser.client.get("/api/v1/handbook/sections/CA-4.3/passages/p2").json()

    assert set(body) == {"section", "passage", "previous", "next"}
    assert set(body["section"]) == SUMMARY_FIELDS
    assert body["section"]["id"] == "CA-4.3"
    assert body["passage"]["id"] == "p2"
    assert body["previous"]["id"] == "p1"
    assert body["next"]["id"] == "p3"
    assert body["previous"]["type"] == "passage"

    first = browser.client.get("/api/v1/handbook/sections/CA-4.3/passages/p1").json()
    assert first["previous"] is None


def test_unknown_sections_and_passages_are_404_problems(browser: Browser) -> None:
    signed_in(browser, "priya")

    for path in (
        "/api/v1/handbook/sections/8.2",
        "/api/v1/handbook/sections/8.2/passages/p1",
        "/api/v1/handbook/sections/CA-4.3/passages/p999",
        "/api/v1/handbook/sections/CA-4.3%00",
        "/api/v1/handbook/sections/CA-4.3%00/passages/p1",
        "/api/v1/handbook/sections/CA-4.3/passages/p1%00",
    ):
        response = browser.client.get(path)
        assert response.status_code == 404, path
        assert response.headers["content-type"].startswith("application/problem+json")
        assert response.json()["status"] == 404


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/handbook",
        "/api/v1/handbook/sections/4.3",
        "/api/v1/handbook/sections/4.3/passages/p1",
        "/api/v1/handbook/search?q=sick",
    ],
)
def test_anonymous_gets_401(browser: Browser, path: str) -> None:
    assert browser.client.get(path).status_code == 401


async def set_pin(engine: AsyncEngine, tenant_id: UUID, version_id: UUID | None) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text("UPDATE tenants SET handbook_version_id = :version WHERE id = :id"),
            {"id": tenant_id, "version": version_id},
        )


@asynccontextmanager
async def second_version(
    engine: AsyncEngine, body: str = "Zebra crossings are painted."
) -> AsyncIterator[UUID]:
    """An unpublished version with one section and one passage
    (`body`), committed as the owner and removed afterward.

    It is unpublished so no other test's new sandbox is pinned to it. The caller must stop
    pinning a sandbox to it before the block ends, or the delete is refused.
    """
    version_id = uuid4()
    section_id = uuid4()
    blocks = [
        {
            "type": "passage",
            "id": "p1",
            "kind": "paragraph",
            "inlines": [{"text": body, "bold": False, "italic": False, "linkSectionId": None}],
        }
    ]
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO handbook_versions (id, label, title, content_hash, embedding_model,"
                " embedding_dimensions, updated_on) VALUES (:id, :label, 'Other Handbook', :label,"
                " 'voyage-4', 1024, current_date)"
            ),
            {"id": version_id, "label": f"test-{version_id}"},
        )
        await connection.execute(
            text(
                "INSERT INTO handbook_sections (id, version_id, section_key, position, kind,"
                " chapter, title, audience, updated_on, sources, blocks) VALUES (:id, :version,"
                " '9.9', 0, 'company', 9, 'Zebra crossings', '{}'::jsonb, current_date,"
                " '[]'::jsonb, CAST(:blocks AS jsonb))"
            ),
            {"id": section_id, "version": version_id, "blocks": json.dumps(blocks)},
        )
        await connection.execute(
            text(
                "INSERT INTO handbook_chunks (version_id, section_id, section_key, section_title,"
                " position, passage_ids, text, embedding) VALUES (:version, :section, '9.9',"
                " 'Zebra crossings', 0, ARRAY['p1'], CAST(:body AS text),"
                " array_fill(0, ARRAY[1024])::vector)"
            ),
            {"version": version_id, "section": section_id, "body": body},
        )
    try:
        yield version_id
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM handbook_versions WHERE id = :id"), {"id": version_id}
            )


# Search


def search(browser: Browser, query: str) -> Any:
    response = browser.client.get("/api/v1/handbook/search", params={"q": query})
    assert response.status_code == 200, response.text
    return response.json()["results"]


def test_search_results_have_the_list_fields_and_an_excerpt_as_segments(browser: Browser) -> None:
    signed_in(browser, "mateo")

    results = search(browser, "overtime")

    assert results
    for result in results:
        assert set(result) == {"section", "passageId", "excerpt"}
        assert set(result["section"]) == SUMMARY_FIELDS
        assert all(set(segment) == {"text", "match"} for segment in result["excerpt"])
        assert all("<" not in segment["text"] for segment in result["excerpt"])
    matched = {
        segment["text"].lower()
        for result in results
        for segment in result["excerpt"]
        if segment["match"]
    }
    assert any(word.startswith("overtime") for word in matched)
    # The segments put back together are the excerpt text, with no marker characters left.
    joined = "".join(segment["text"] for segment in results[0]["excerpt"])
    assert "\x02" not in joined
    assert "\x03" not in joined


def test_search_puts_the_sections_that_apply_to_the_person_first(browser: Browser) -> None:
    signed_in(browser, "mateo")

    results = search(browser, "overtime")

    flags = [result["section"]["appliesToMe"] for result in results]
    assert flags[0] is True
    assert flags == sorted(flags, reverse=True)
    assert False in flags
    ids = [result["section"]["id"] for result in results]
    assert len(ids) == len(set(ids)), "one result per section"


def test_search_requires_every_word(browser: Browser) -> None:
    signed_in(browser, "priya")

    assert search(browser, "dental plan") == []
    assert search(browser, "sick leave")
    assert search(browser, "sick zebra") == []


def test_search_with_only_stop_words_finds_nothing(browser: Browser) -> None:
    signed_in(browser, "priya")

    assert search(browser, "the of") == []


def test_control_characters_in_the_query_cannot_forge_a_match_marker(browser: Browser) -> None:
    signed_in(browser, "priya")

    forged = search(browser, "sick\x02 leave\x03")
    plain = search(browser, "sick leave")

    assert [r["section"]["id"] for r in forged] == [r["section"]["id"] for r in plain]
    for result in forged:
        for segment in result["excerpt"]:
            assert "\x02" not in segment["text"]
            assert "\x03" not in segment["text"]
    # What is emphasized is a word of the query, never text the caller marked.
    marked = {s["text"].lower() for r in forged for s in r["excerpt"] if s["match"]}
    assert marked
    assert all(word.startswith(("sick", "leav")) for word in marked)


def test_a_query_of_only_control_characters_is_a_422(browser: Browser) -> None:
    signed_in(browser, "priya")

    response = browser.client.get("/api/v1/handbook/search", params={"q": " \x02\x03 "})

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")


def test_the_query_is_limited_to_100_characters_and_required(browser: Browser) -> None:
    signed_in(browser, "priya")
    path = "/api/v1/handbook/search"

    assert browser.client.get(path, params={"q": "a" * 100}).status_code == 200
    assert browser.client.get(path, params={"q": "a" * 101}).status_code == 422
    assert browser.client.get(path).status_code == 422


def test_a_query_that_looks_like_sql_or_tsquery_syntax_is_just_words(browser: Browser) -> None:
    signed_in(browser, "priya")

    for query in ("'; DROP TABLE tenants; --", "sick & !leave | (", "sick:*", "\\"):
        browser.client.get("/api/v1/handbook/search", params={"q": query}).raise_for_status()


# Versions


async def test_a_sandbox_with_no_pinned_version_gets_404_problems(
    browser: Browser, owner_engine: AsyncEngine
) -> None:
    """The trigger pins every new sandbox, so the owner clears the pin of one test sandbox. The
    sandbox is deleted with the others when the test session ends, so no row is left behind."""
    sandbox = browser.start_sandbox("priya")
    await set_pin(owner_engine, UUID(sandbox["tenant"]["id"]), None)

    for path in (
        "/api/v1/handbook",
        "/api/v1/handbook/sections/4.3",
        "/api/v1/handbook/sections/4.3/passages/p1",
        "/api/v1/handbook/search?q=sick",
    ):
        response = browser.client.get(path)
        assert response.status_code == 404, path
        assert response.headers["content-type"].startswith("application/problem+json")


async def test_a_sandbox_reads_only_its_own_version(
    open_browser: OpenBrowser, owner_engine: AsyncEngine
) -> None:
    ordinary = open_browser()
    ordinary.start_sandbox("priya")
    pinned_elsewhere = open_browser()
    other = pinned_elsewhere.start_sandbox("priya")
    other_tenant = UUID(other["tenant"]["id"])

    async with second_version(owner_engine) as version_id:
        try:
            await set_pin(owner_engine, other_tenant, version_id)

            mine = ordinary.client.get("/api/v1/handbook").json()
            theirs = pinned_elsewhere.client.get("/api/v1/handbook").json()
            assert mine["version"]["title"] == "Juniper Row Employee Handbook"
            assert theirs["version"]["title"] == "Other Handbook"
            assert [s["id"] for s in theirs["sections"]] == ["9.9"]
            assert "9.9" not in {s["id"] for s in mine["sections"]}

            assert ordinary.client.get("/api/v1/handbook/sections/9.9").status_code == 404
            assert pinned_elsewhere.client.get("/api/v1/handbook/sections/9.9").status_code == 200
            assert pinned_elsewhere.client.get("/api/v1/handbook/sections/4.3").status_code == 404
            assert search(ordinary, "zebra") == []
            assert [r["section"]["id"] for r in search(pinned_elsewhere, "zebra")] == ["9.9"]
            assert search(pinned_elsewhere, "sick") == []
        finally:
            # Release the version, so it can be deleted. The sandbox goes with the rest later.
            await set_pin(owner_engine, other_tenant, None)


def passage_text(browser: Browser, section_id: str, passage_id: str) -> str:
    body = browser.client.get(
        f"/api/v1/handbook/sections/{section_id}/passages/{passage_id}"
    ).json()
    inlines = body["passage"].get("inlines") or [
        i for item in body["passage"]["items"] for i in item
    ]
    return "".join(inline["text"] for inline in inlines)


def test_the_link_and_the_excerpt_name_the_same_passage(browser: Browser) -> None:
    signed_in(browser, "priya")

    results = search(browser, "wage")

    hit = next(result for result in results if result["section"]["id"] == "CA-3.4")
    assert hit["passageId"] == "p3"
    text_of_passage = passage_text(browser, "CA-3.4", hit["passageId"]).lower()
    matched = [s["text"].lower() for s in hit["excerpt"] if s["match"]]
    assert matched
    assert all(word in text_of_passage for word in matched)
    # Every result's matched words are in the passage it links to.
    for result in results:
        words = [s["text"].lower() for s in result["excerpt"] if s["match"]]
        linked = passage_text(browser, result["section"]["id"], result["passageId"]).lower()
        assert all(word in linked for word in words), result["section"]["id"]


async def test_stored_text_cannot_forge_a_match_marker(
    browser: Browser, owner_engine: AsyncEngine
) -> None:
    """A passage and a chunk whose stored text contains the marker characters."""
    forged = "Zebra \x02crossings\x03 are painted."
    sandbox = browser.start_sandbox("priya")
    tenant = UUID(sandbox["tenant"]["id"])
    async with second_version(owner_engine, forged) as version_id:
        try:
            await set_pin(owner_engine, tenant, version_id)

            results = search(browser, "painted")

            assert [r["section"]["id"] for r in results] == ["9.9"]
            excerpt = results[0]["excerpt"]
            assert [s["text"] for s in excerpt if s["match"]] == ["painted"]
            assert "\x02" not in "".join(s["text"] for s in excerpt)
            assert "\x03" not in "".join(s["text"] for s in excerpt)
        finally:
            await set_pin(owner_engine, tenant, None)


async def test_stored_text_cannot_forge_a_marker_in_the_chunk_level_excerpt(
    browser: Browser, owner_engine: AsyncEngine
) -> None:
    """The query matches only the section's title, so no passage has a match and the excerpt falls
    back to the chunk's own text, which holds marker characters."""
    sandbox = browser.start_sandbox("priya")
    tenant = UUID(sandbox["tenant"]["id"])
    async with second_version(owner_engine, "Cars \x02stop\x03 here.") as version_id:
        try:
            await set_pin(owner_engine, tenant, version_id)

            results = search(browser, "zebra")

            assert [r["section"]["id"] for r in results] == ["9.9"]
            assert results[0]["passageId"] == "p1"
            assert not any(s["match"] for s in results[0]["excerpt"])
            assert "\x02" not in "".join(s["text"] for s in results[0]["excerpt"])
        finally:
            await set_pin(owner_engine, tenant, None)
