"""The assistant's tool definitions and the checks that run before a tool does."""

import json
from typing import Any, cast

import pytest

from app.ai.tools.registry import TOOL_DEFINITIONS, ToolContext, run_tool
from app.ai.transport import ModelRequest

# The API answers 400 to a strict tool schema that carries any of these, so limits live in the
# descriptions and in our own checks.
FORBIDDEN_KEYWORDS = {"minLength", "maxLength", "minimum", "maximum", "multipleOf"}
# Nothing a tool takes may say "whose data": the actor is the signed-in person, always.
WHOSE_DATA = {
    "person_id",
    "personid",
    "user_id",
    "userid",
    "employee",
    "employee_id",
    "as_user",
    "actor",
    "actor_id",
    "on_behalf_of",
    "person",
    "target",
    "email",
}


def walk(node: Any) -> list[dict[str, Any]]:
    """Every dict inside a schema, however deep."""
    found: list[dict[str, Any]] = []
    if isinstance(node, dict):
        found.append(node)
        for value in node.values():
            found.extend(walk(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(walk(item))
    return found


def no_database() -> ToolContext:
    """A context whose engine is never reached: these inputs are refused before any tool runs."""
    return cast(ToolContext, None)


def test_the_tools_come_in_a_fixed_order() -> None:
    assert [tool["name"] for tool in TOOL_DEFINITIONS] == [
        "search_handbook",
        "get_my_profile",
        "find_people",
    ]


def test_every_definition_has_a_name_a_plain_description_and_a_schema() -> None:
    for tool in TOOL_DEFINITIONS:
        assert set(tool) == {"name", "description", "input_schema"}
        assert len(tool["description"]) > 40
        assert tool["input_schema"]["type"] == "object"


def test_every_object_in_every_schema_forbids_extra_properties() -> None:
    for tool in TOOL_DEFINITIONS:
        objects = [n for n in walk(tool["input_schema"]) if n.get("type") == "object"]
        assert objects
        for node in objects:
            assert node["additionalProperties"] is False, tool["name"]


def test_no_schema_carries_a_length_or_numeric_limit() -> None:
    for tool in TOOL_DEFINITIONS:
        for node in walk(tool["input_schema"]):
            assert not FORBIDDEN_KEYWORDS & set(node), tool["name"]


def test_the_limits_are_stated_in_the_descriptions_instead() -> None:
    by_name = {tool["name"]: tool for tool in TOOL_DEFINITIONS}
    search = json.dumps(by_name["search_handbook"])
    assert "500" in search
    assert "5" in by_name["search_handbook"]["description"]
    assert "100" in json.dumps(by_name["find_people"])
    assert "10" in by_name["find_people"]["description"]


def test_no_property_names_a_person_for_whose_data() -> None:
    for tool in TOOL_DEFINITIONS:
        for node in walk(tool["input_schema"]):
            for name in node.get("properties", {}):
                assert name.lower() not in WHOSE_DATA, (tool["name"], name)


def test_the_optional_properties_stay_few() -> None:
    optional = 0
    for tool in TOOL_DEFINITIONS:
        schema = tool["input_schema"]
        optional += len(set(schema["properties"]) - set(schema["required"]))
    # The API allows 24 across all strict tools.
    assert optional <= 4


def test_get_my_profile_takes_no_input() -> None:
    schema = {t["name"]: t for t in TOOL_DEFINITIONS}["get_my_profile"]["input_schema"]
    assert schema["properties"] == {}


def test_the_definitions_serialize_through_a_request() -> None:
    request = ModelRequest(
        model="claude-opus-5-5",
        system=({"type": "text", "text": "x"},),
        tools=tuple(TOOL_DEFINITIONS),
        messages=({"role": "user", "content": "hi"},),
        effort="medium",
        max_tokens=1000,
        betas=("server-side-fallback-2026-07-01",),
    )
    tools = request.to_api_kwargs()["tools"]
    assert [t["name"] for t in tools] == [t["name"] for t in TOOL_DEFINITIONS]
    assert all(t["strict"] is True for t in tools)
    json.dumps(tools)


async def test_an_unknown_tool_is_an_error_the_model_can_read() -> None:
    outcome = await run_tool("delete_everything", {}, no_database())
    assert outcome.is_error is True
    assert outcome.content[0]["type"] == "text"
    assert "search_handbook" in outcome.content[0]["text"]
    assert outcome.sources == []


@pytest.mark.parametrize(
    ("name", "raw", "fragment"),
    [
        ("search_handbook", {}, "query"),
        ("search_handbook", {"query": 5}, "query"),
        ("search_handbook", {"query": "   "}, "empty"),
        ("search_handbook", {"query": "x" * 501}, "500"),
        ("search_handbook", {"query": "pto", "person_id": "abc"}, "person_id"),
        ("search_handbook", {"query": "pto", "location": "sf"}, "Unknown location 'sf'"),
        ("search_handbook", {"query": "pto", "location": 3}, "location"),
        ("get_my_profile", {"person_id": "abc"}, "person_id"),
        ("find_people", {}, "scope"),
        ("find_people", {"scope": "everyone", "query": "x" * 101}, "100"),
        ("find_people", {"scope": "her_team"}, "scope"),
        ("find_people", {"scope": "my_team", "as_user": "x"}, "as_user"),
        ("find_people", {"scope": "my_team", "query": 7}, "query"),
        ("find_people", {"scope": "everyone", "query": "\ud800"}, "empty"),
        ("find_people", {"scope": "everyone", "query": "  \x00 "}, "empty"),
    ],
)
async def test_an_invalid_input_is_refused_before_the_tool_runs(
    name: str, raw: dict[str, Any], fragment: str
) -> None:
    outcome = await run_tool(name, raw, no_database())
    assert outcome.is_error is True
    text = outcome.content[0]["text"]
    assert fragment in text
    assert "Traceback" not in text
    assert "SELECT" not in text


async def test_the_unknown_location_error_lists_the_real_codes() -> None:
    outcome = await run_tool("search_handbook", {"query": "pto", "location": "sf"}, no_database())
    assert outcome.content[0]["text"] == "Unknown location 'sf'. Use one of: den, oak, aus, atl."


async def test_the_summary_never_repeats_a_long_question() -> None:
    outcome = await run_tool(
        "search_handbook", {"query": "q" * 400, "location": "zz"}, no_database()
    )
    assert len(outcome.summary) < 200


async def test_the_summary_holds_the_cleaned_query_not_the_raw_one() -> None:
    # The search is refused for its location, after the query was cleaned.
    raw = {"query": "sick\x00\ud800  leave", "location": "zz"}
    outcome = await run_tool("search_handbook", raw, no_database())
    assert "sick leave" in outcome.summary
    assert "\x00" not in outcome.summary
    assert "\ud800" not in outcome.summary


def test_find_people_says_it_reports_when_there_are_more() -> None:
    description = {t["name"]: t for t in TOOL_DEFINITIONS}["find_people"]["description"]
    assert "10" in description
    assert "truncated" in description
