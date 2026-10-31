"""The two case tools' definitions and input checks (no database). The tools that touch cases are
tested against the real database in tests/integration/test_case_tools.py."""

from typing import Any, cast
from uuid import uuid4

import pytest

from app.ai.tools.cases import ONLY_HR_TEXT
from app.ai.tools.registry import TOOL_DEFINITIONS, ToolContext, describe_call, input_problems
from app.ai.tools.registry import run_tool as registry_run_tool
from app.policy import Actor


def definition(name: str) -> dict[str, Any]:
    return next(tool for tool in TOOL_DEFINITIONS if tool["name"] == name)


def test_the_case_tools_come_last_in_the_fixed_order() -> None:
    assert [tool["name"] for tool in TOOL_DEFINITIONS][-2:] == ["get_my_cases", "list_cases"]


def test_get_my_cases_takes_no_input() -> None:
    schema = definition("get_my_cases")["input_schema"]
    assert schema["properties"] == {}
    assert schema["required"] == []
    assert schema["additionalProperties"] is False
    assert input_problems("get_my_cases", {}) == []
    assert input_problems("get_my_cases", {"person_id": "x"})


def test_list_cases_takes_one_required_status() -> None:
    schema = definition("list_cases")["input_schema"]
    assert set(schema["properties"]) == {"status"}
    assert schema["required"] == ["status"]
    assert schema["properties"]["status"]["enum"] == ["open", "new", "in_review", "closed"]
    assert schema["additionalProperties"] is False


@pytest.mark.parametrize(
    "raw",
    [{}, {"status": "all"}, {"status": 1}, {"status": "open", "person_id": "x"}, {"status": None}],
)
def test_list_cases_refuses_a_bad_input(raw: dict[str, Any]) -> None:
    assert input_problems("list_cases", raw)


@pytest.mark.parametrize("status", ["open", "new", "in_review", "closed"])
def test_list_cases_accepts_each_status(status: str) -> None:
    assert input_problems("list_cases", {"status": status}) == []
    assert describe_call("list_cases", {"status": status}) == f"status={status}"


def test_the_descriptions_say_what_the_tools_never_return() -> None:
    for name in ("get_my_cases", "list_cases"):
        description = definition(name)["description"]
        assert "wrote" in description
        assert "summary" in description


def test_the_fixed_error_is_the_specs_sentence() -> None:
    assert ONLY_HR_TEXT == "Only the HR team can see cases."


async def test_a_non_hr_actor_gets_the_fixed_error_before_anything_is_read() -> None:
    """The check runs before the input is parsed and before the database is touched: the engine here
    is None, so reaching it would raise. A bad input gets the same answer as a good one."""
    actor = Actor(uuid4(), uuid4(), False, frozenset(), frozenset())
    ctx = cast(ToolContext, type("Ctx", (), {"actor": actor, "engine": None})())

    good = await registry_run_tool("list_cases", {"status": "open"}, ctx)
    bad = await registry_run_tool("list_cases", {"status": "everything", "x": 1}, ctx)

    for outcome in (good, bad):
        assert outcome.is_error is True
        assert outcome.content == [{"type": "text", "text": ONLY_HR_TEXT}]
    assert good.content == bad.content


def test_list_cases_says_it_leaves_out_the_askers_own_cases() -> None:
    description = definition("list_cases")["description"]
    assert (
        "Leaves out any case you opened yourself; you see those with get_my_cases." in description
    )
