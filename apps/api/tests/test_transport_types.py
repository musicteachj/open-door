"""The transport interface: frozen events, a stable request, and the guard's output shape."""

import dataclasses
import json
from typing import Any

import pytest

from app.ai.pricing import IterationUsage, Usage
from app.ai.transport import (
    GUARD_MAX_TOKENS,
    GUARD_NEW_MESSAGE_TAG,
    GUARD_OUTPUT_SCHEMA,
    GUARD_TIMEOUT_SECONDS,
    Finished,
    GuardUnavailable,
    ModelRequest,
    SearchResultCitation,
    StatusNote,
    TextBlockEnd,
    TextDelta,
    ToolCall,
    parse_guard_output,
)

USAGE = Usage(input_tokens=10, output_tokens=5, cache_read_tokens=0, cache_write_tokens=0)
BETAS = ("server-side-fallback-2026-07-01", "thinking-display-updates-2026-08-18")
TOOL = {
    "name": "search_handbook",
    "description": "Search the handbook.",
    "input_schema": {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
        "additionalProperties": False,
    },
}


def a_request(**changes: Any) -> ModelRequest:
    fields: dict[str, Any] = {
        "model": "claude-opus-5-5",
        "system": ({"type": "text", "text": "You are Open Door."},),
        "tools": (TOOL,),
        "messages": ({"role": "user", "content": [{"type": "text", "text": "hi"}]},),
        "effort": "low",
        "max_tokens": 8000,
        "betas": BETAS,
        "fallbacks": "default",
    }
    return ModelRequest(**{**fields, **changes})


def test_every_event_is_frozen() -> None:
    citation = SearchResultCitation(
        search_result_index=0,
        start_block_index=0,
        end_block_index=1,
        source="/handbook/4.3",
        title="Sick leave",
        cited_text="text",
    )
    events: list[Any] = [
        StatusNote("Searching"),
        TextDelta("hi"),
        TextBlockEnd((citation,)),
        ToolCall("toolu_1", "search_handbook", {"query": "q"}),
        Finished(
            message={"role": "assistant", "content": []},
            stop_reason="end_turn",
            stop_details=None,
            usage=USAGE,
            iterations=(IterationUsage("claude-opus-5-5", USAGE),),
            served_by="claude-opus-5-5",
        ),
        citation,
        a_request(),
    ]
    for event in events:
        assert dataclasses.is_dataclass(event)
        field = dataclasses.fields(event)[0].name
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(event, field, "changed")


def test_the_request_is_built_exactly_as_the_api_wants_it() -> None:
    kwargs = a_request().to_api_kwargs()

    assert kwargs["model"] == "claude-opus-5-5"
    assert kwargs["max_tokens"] == 8000
    assert kwargs["betas"] == list(BETAS)
    assert kwargs["fallbacks"] == "default"
    assert kwargs["thinking"] == {"type": "adaptive", "display": "updates"}
    assert kwargs["output_config"] == {"effort": "low"}
    assert kwargs["system"] == [{"type": "text", "text": "You are Open Door."}]
    assert kwargs["messages"] == [{"role": "user", "content": [{"type": "text", "text": "hi"}]}]


def test_every_tool_is_strict_and_streams_eagerly() -> None:
    (tool,) = a_request().to_api_kwargs()["tools"]

    assert tool["strict"] is True
    assert tool["eager_input_streaming"] is True
    assert tool["name"] == "search_handbook"


def test_the_request_has_no_sampling_keys_and_no_tool_choice() -> None:
    kwargs = a_request().to_api_kwargs()

    for forbidden in ("temperature", "top_p", "top_k", "tool_choice", "stream"):
        assert forbidden not in kwargs
    assert "budget_tokens" not in json.dumps(kwargs)
    assert kwargs["thinking"]["type"] != "disabled"


def test_the_same_request_always_serializes_identically() -> None:
    first = json.dumps(a_request().to_api_kwargs(), sort_keys=True)
    second = json.dumps(a_request().to_api_kwargs(), sort_keys=True)

    assert first == second
    assert first != json.dumps(a_request(effort="medium").to_api_kwargs(), sort_keys=True)


def test_changing_the_built_kwargs_does_not_change_the_request() -> None:
    request = a_request()
    kwargs = request.to_api_kwargs()
    kwargs["messages"].append({"role": "user", "content": "x"})
    kwargs["tools"][0]["name"] = "changed"
    kwargs["system"][0]["text"] = "changed"

    assert request.to_api_kwargs() == a_request().to_api_kwargs()


def test_a_request_without_fallbacks_leaves_the_key_out() -> None:
    assert "fallbacks" not in a_request(fallbacks=None).to_api_kwargs()


def valid_output(**changes: Any) -> str:
    return json.dumps({"category": "ordinary", "kind": None, "injectionSuspected": False} | changes)


@pytest.mark.parametrize(
    ("changes", "category", "kind", "injection"),
    [
        ({}, "ordinary", None, False),
        ({"category": "sensitive", "kind": "pay"}, "sensitive", "pay", False),
        ({"category": "crisis", "kind": "self_harm"}, "crisis", "self_harm", False),
        (
            {"category": "crisis", "kind": "threat_of_violence"},
            "crisis",
            "threat_of_violence",
            False,
        ),
        ({"injectionSuspected": True}, "ordinary", None, True),
    ],
)
def test_the_guard_output_parser_accepts_each_valid_shape(
    changes: dict[str, Any], category: str, kind: str | None, injection: bool
) -> None:
    result = parse_guard_output(valid_output(**changes), usage=USAGE, served_by="claude-haiku-5-5")

    assert (result.category, result.kind, result.injection_suspected) == (
        category,
        kind,
        injection,
    )
    assert result.usage == USAGE
    assert result.served_by == "claude-haiku-5-5"


@pytest.mark.parametrize(
    "text",
    [
        valid_output(extra="x"),
        json.dumps({"category": "ordinary", "kind": None}),
        json.dumps({"category": "ordinary", "injectionSuspected": False}),
        json.dumps({"kind": None, "injectionSuspected": False}),
        valid_output(category="urgent"),
        valid_output(kind="gossip"),
        valid_output(injectionSuspected="yes"),
        valid_output(injectionSuspected=1),
        valid_output(category=None),
        "not json",
        "",
        "[]",
        "null",
    ],
)
def test_the_guard_output_parser_rejects_anything_else(text: str) -> None:
    with pytest.raises(GuardUnavailable) as raised:
        parse_guard_output(text, usage=USAGE, served_by="claude-haiku-5-5")

    # The guard did run, so the spend travels with the failure.
    assert raised.value.usage == USAGE


def test_the_guard_schema_matches_what_the_parser_accepts() -> None:
    assert GUARD_OUTPUT_SCHEMA["additionalProperties"] is False
    assert GUARD_OUTPUT_SCHEMA["required"] == ["category", "kind", "injectionSuspected"]
    assert GUARD_OUTPUT_SCHEMA["properties"]["category"]["enum"] == [
        "ordinary",
        "sensitive",
        "crisis",
    ]
    kinds = GUARD_OUTPUT_SCHEMA["properties"]["kind"]["anyOf"]
    assert {"type": "null"} in kinds
    assert {
        "harassment_discrimination",
        "safety",
        "medical_accommodation",
        "pay",
        "self_harm",
        "threat_of_violence",
        "other",
    } == set(next(k for k in kinds if "enum" in k)["enum"])


def test_the_guards_limits_and_tag_are_defined_once_here() -> None:
    assert GUARD_TIMEOUT_SECONDS == 4
    assert GUARD_MAX_TOKENS == 1024
    assert GUARD_NEW_MESSAGE_TAG == "new_message"


def test_a_guard_failure_carries_no_usage_unless_given() -> None:
    assert GuardUnavailable("no answer").usage is None
    assert GuardUnavailable("bad", usage=USAGE).usage == USAGE


def test_fallbacks_without_the_fallback_beta_is_refused_at_construction() -> None:
    # The API would answer every such call with a 400, which would look like an outage.
    with pytest.raises(ValueError, match="server-side-fallback-2026-07-01"):
        a_request(betas=("thinking-display-updates-2026-08-18",))
    with pytest.raises(ValueError, match="fallbacks"):
        a_request(betas=())


def test_no_fallbacks_is_allowed_with_or_without_the_beta() -> None:
    assert a_request(fallbacks=None, betas=()).fallbacks is None
    assert a_request(fallbacks=None).betas == BETAS


def test_the_request_asks_for_automatic_caching_of_the_conversation() -> None:
    kwargs = a_request().to_api_kwargs()

    # Top level, so the cache follows the end of the history on every call. The system block keeps
    # its own breakpoint; both are far under the limit of four.
    assert kwargs["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in json.dumps(kwargs["messages"])
