"""The Anthropic transport, against hand-written server-sent-event bodies served by a mock.

No test here reaches the network: the SDK's HTTP client is replaced with `httpx2.MockTransport`
(the SDK is built on httpx2, not httpx), so nothing is ever billed.
"""

import asyncio
import dataclasses
import json
from collections.abc import AsyncIterator, Callable, Coroutine
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx2
import pytest
from anthropic import APIConnectionError, APIResponseValidationError, AsyncAnthropic, Timeout
from anthropic.lib.streaming import _beta_messages as streaming_module
from pydantic import SecretStr

from app.ai import anthropic_transport
from app.ai.anthropic_transport import (
    MODEL_CONNECT_TIMEOUT_SECONDS,
    MODEL_READ_TIMEOUT_SECONDS,
    AnthropicTransport,
    from_settings,
)
from app.ai.pricing import IterationUsage, Usage, total_usage, turn_call_cost
from app.ai.transport import (
    GUARD_TIMEOUT_SECONDS,
    Finished,
    GuardRequest,
    GuardUnavailable,
    InvalidToolInput,
    ModelEvent,
    ModelRequest,
    ModelUnavailable,
    SearchResultCitation,
    SpendLimitReached,
    StatusNote,
    TextBlockEnd,
    TextDelta,
    ToolCall,
    guard_api_kwargs,
)
from app.core.config import Settings

FIXTURES = Path(__file__).parent / "fixtures" / "anthropic"
OPUS = "claude-opus-5-5"
SONNET = "claude-sonnet-5-5"
HAIKU = "claude-haiku-5-5"
BETAS = ("server-side-fallback-2026-07-01", "thinking-display-updates-2026-08-18")
SEARCH_TOOL = {
    "name": "search_handbook",
    "description": "Search the handbook.",
    "input_schema": {
        "type": "object",
        "properties": {"query": {"type": "string"}, "location": {"type": "string"}},
        "required": ["query", "location"],
        "additionalProperties": False,
    },
}

Handler = (
    Callable[[httpx2.Request], httpx2.Response]
    | Callable[[httpx2.Request], Coroutine[None, None, httpx2.Response]]
)


def sse(name: str) -> Callable[[httpx2.Request], httpx2.Response]:
    body = (FIXTURES / f"{name}.sse").read_bytes()

    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=body)

    return handler


def error_response(status: int, error_type: str, message: str) -> Callable[..., httpx2.Response]:
    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            status,
            headers={"request-id": "req_011TEST"},
            json={"type": "error", "error": {"type": error_type, "message": message}},
        )

    return handler


CITED_TEXT = "Employees accrue one hour of paid sick leave for every 30 hours worked."


def a_request() -> ModelRequest:
    return ModelRequest(
        model=OPUS,
        system=({"type": "text", "text": "You are Open Door."},),
        tools=(SEARCH_TOOL,),
        messages=({"role": "user", "content": [{"type": "text", "text": "Sick leave?"}]},),
        effort="low",
        max_tokens=8000,
        betas=BETAS,
        fallbacks="default",
    )


def a_guard_request() -> GuardRequest:
    return GuardRequest(
        model=HAIKU,
        system="Classify the message.",
        messages=({"role": "user", "content": "<message>I need leave</message>"},),
    )


@pytest.fixture
async def make_transport() -> AsyncIterator[Callable[[Handler], AnthropicTransport]]:
    clients: list[AsyncAnthropic] = []

    def make(handler: Handler) -> AnthropicTransport:
        client = AsyncAnthropic(
            api_key="test-key",
            http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
            max_retries=0,
        )
        clients.append(client)
        return AnthropicTransport(client)

    yield make
    for client in clients:
        await client.close()


async def collect(transport: AnthropicTransport, model: str = OPUS) -> list[ModelEvent]:
    request = dataclasses.replace(a_request(), model=model)
    return [event async for event in transport.stream(request)]


def finished_of(events: list[ModelEvent]) -> Finished:
    last = events[-1]
    assert isinstance(last, Finished)
    return last


# --- The stream -------------------------------------------------------------------------------


async def test_text_deltas_status_notes_and_citations_become_events(
    make_transport: Callable[[Handler], AnthropicTransport],
) -> None:
    events = await collect(make_transport(sse("text_with_citation")))

    citation = SearchResultCitation(
        search_result_index=1,
        start_block_index=0,
        end_block_index=1,  # exclusive: block 0 only
        source="/handbook/CA-4.3?passage=p1",
        title="CA-4.3 Sick leave · California addendum",
        cited_text=CITED_TEXT,
    )
    assert events[:-1] == [
        StatusNote("Checking the California sick leave rules."),
        TextDelta("You earn one hour of sick leave "),
        TextDelta("for every 30 hours worked."),
        TextBlockEnd((citation,)),
        TextDelta(" Ask HR if you want to check your balance."),
        TextBlockEnd(()),
    ]


async def test_finished_holds_the_message_to_store_and_the_priced_usage(
    make_transport: Callable[[Handler], AnthropicTransport],
) -> None:
    finished = finished_of(await collect(make_transport(sse("text_with_citation"))))

    assert finished.stop_reason == "end_turn"
    assert finished.stop_details is None
    assert finished.served_by == OPUS
    assert finished.usage == Usage(
        input_tokens=1200, output_tokens=90, cache_read_tokens=400, cache_write_tokens=0
    )
    # No iterations were reported, so the whole call is one attempt on the model that answered.
    assert finished.iterations == (IterationUsage(OPUS, finished.usage),)
    assert turn_call_cost(finished.iterations) == Decimal("0.00668")
    assert finished.message == {
        "role": "assistant",
        "content": [
            {
                "type": "thinking",
                "thinking": "Checking the California sick leave rules.",
                "signature": "EqQBCkYIBxgCKkDsig1",
            },
            {
                "type": "text",
                "text": "You earn one hour of sick leave for every 30 hours worked.",
                "citations": [
                    {
                        "type": "search_result_location",
                        "cited_text": CITED_TEXT,
                        "search_result_index": 1,
                        "start_block_index": 0,
                        "end_block_index": 1,
                        "source": "/handbook/CA-4.3?passage=p1",
                        "title": "CA-4.3 Sick leave · California addendum",
                    }
                ],
            },
            {"type": "text", "text": " Ask HR if you want to check your balance."},
        ],
    }


async def test_a_streamed_tool_input_becomes_one_tool_call_with_the_parsed_dict(
    make_transport: Callable[[Handler], AnthropicTransport],
) -> None:
    events = await collect(make_transport(sse("tool_use")))

    # The empty, signed thinking block is reasoning: nothing to show, but it is kept.
    assert events[:-1] == [
        ToolCall(
            "toolu_01SearchSick",
            "search_handbook",
            {"query": "sick leave in California", "location": "oak"},
        )
    ]
    finished = finished_of(events)
    assert finished.stop_reason == "tool_use"
    assert finished.usage.cache_write_tokens == 300
    assert finished.message["content"] == [
        {"type": "thinking", "thinking": "", "signature": "EtgBCkYIBxgCKkAreasoning1"},
        {
            "type": "tool_use",
            "id": "toolu_01SearchSick",
            "name": "search_handbook",
            "input": {"query": "sick leave in California", "location": "oak"},
        },
    ]


async def test_the_interrupted_stand_in_is_not_a_status_but_is_kept(
    make_transport: Callable[[Handler], AnthropicTransport],
) -> None:
    events = await collect(make_transport(sse("interrupted_note")))

    assert [type(event) for event in events] == [TextDelta, TextBlockEnd, Finished]
    finished = finished_of(events)
    assert finished.stop_reason == "max_tokens"
    assert finished.message["content"][1]["type"] == "thinking"


async def test_a_fallback_is_priced_per_model_and_the_echo_rule_is_applied(
    make_transport: Callable[[Handler], AnthropicTransport],
) -> None:
    events = await collect(make_transport(sse("fallback")))

    # The tool call that came before the fallback belongs to the declined attempt: it is neither
    # run nor stored. The fallback block itself is only an audit marker.
    assert events[:-1] == [
        TextDelta("Let me look that up."),
        TextBlockEnd(()),
        StatusNote("Looking at the sick leave section."),
        TextDelta("Sick leave accrues as you work."),
        TextBlockEnd(()),
    ]
    finished = finished_of(events)
    assert finished.served_by == SONNET
    assert finished.fell_back is True
    # The top-level usage is the attempt that produced the message. The declined attempt is only in
    # the iterations, so the turn's tokens are their total.
    assert finished.usage == Usage(1000, 120, 0, 0)
    assert total_usage(finished.iterations) == Usage(2000, 160, 0, 0)
    assert finished.iterations == (
        IterationUsage(OPUS, Usage(1000, 40, 0, 0)),
        IterationUsage(SONNET, Usage(1000, 120, 0, 0)),
    )
    assert turn_call_cost(finished.iterations) == Decimal("0.008")
    # Text before the boundary stays. Its thinking and tool_use are dropped, so the stored message
    # is exactly what the API accepts back. Everything after the boundary is kept.
    assert finished.message["content"] == [
        {"type": "text", "text": "Let me look that up."},
        {
            "type": "thinking",
            "thinking": "Looking at the sick leave section.",
            "signature": "EqwBserved2",
        },
        {"type": "text", "text": "Sick leave accrues as you work."},
    ]


async def test_an_unlabeled_iteration_after_a_fallback_is_priced_at_the_dearer_model(
    make_transport: Callable[[Handler], AnthropicTransport],
) -> None:
    # The SDK says a fallback_message is the terminal entry and the serving hop's earlier loop
    # iterations are `message` entries, but not whether those name their model. Asked for Sonnet
    # and served by Opus, an unlabeled entry could be either, so it is counted at the dearer one.
    events = await collect(make_transport(sse("fallback_unlabeled_iteration")), model=SONNET)

    finished = finished_of(events)
    assert finished.served_by == OPUS
    assert finished.fell_back is True
    assert [item.model for item in finished.iterations] == [OPUS, OPUS, OPUS]
    assert turn_call_cost(finished.iterations) == Decimal("0.0156")


async def test_the_same_model_in_another_form_is_not_a_fallback(
    make_transport: Callable[[Handler], AnthropicTransport],
) -> None:
    # A fallback is the API's own signal (a fallback_message entry or a fallback block), never a
    # difference in how the model is named. A dated snapshot ID of the same model is not one.
    events = await collect(make_transport(sse("model_echoed_differently")))

    finished = finished_of(events)
    assert finished.served_by == "claude-opus-5-5-20260901"
    assert finished.fell_back is False
    # With no signal it is priced as asked, not as the unfamiliar ID the API echoed.
    assert [item.model for item in finished.iterations] == [OPUS]


async def test_a_blank_text_block_is_left_out_of_the_stored_message(
    make_transport: Callable[[Handler], AnthropicTransport],
) -> None:
    events = await collect(make_transport(sse("blank_text_before_tool_use")))

    finished = finished_of(events)
    # A blank text block carries nothing, and the API refuses it when it is sent back. The empty
    # signed thinking block is not text and stays.
    assert [block["type"] for block in finished.message["content"]] == ["thinking", "tool_use"]
    assert not any(
        block["type"] == "text" and not block["text"].strip()
        for block in finished.message["content"]
    )


async def test_without_iterations_the_call_is_priced_as_asked_not_as_echoed(
    make_transport: Callable[[Handler], AnthropicTransport],
) -> None:
    finished = finished_of(await collect(make_transport(sse("dated_model_no_iterations"))))

    # The API echoed a dated ID that has no pinned price; it would be charged at the dearest rates.
    assert [item.model for item in finished.iterations] == [OPUS]


async def test_without_iterations_a_fallback_block_labels_the_serving_model(
    make_transport: Callable[[Handler], AnthropicTransport],
) -> None:
    finished = finished_of(
        await collect(make_transport(sse("fallback_block_no_iterations")), model=SONNET)
    )

    assert [item.model for item in finished.iterations] == [OPUS]


async def test_a_fallback_block_alone_is_a_fallback(
    make_transport: Callable[[Handler], AnthropicTransport],
) -> None:
    finished = finished_of(await collect(make_transport(sse("fallback_block_only")), model=SONNET))

    assert finished.served_by == OPUS
    assert [item.model for item in finished.iterations] == [OPUS, OPUS]


async def test_a_fallback_entry_alone_is_a_fallback_and_names_who_served(
    make_transport: Callable[[Handler], AnthropicTransport],
) -> None:
    # No fallback block, because no earlier model ran and declined; the entry is the signal.
    finished = finished_of(await collect(make_transport(sse("fallback_entry_only")), model=SONNET))

    assert finished.served_by == OPUS
    assert [item.model for item in finished.iterations] == [OPUS, OPUS]


async def test_an_unlabeled_iteration_without_a_fallback_is_the_requested_model(
    make_transport: Callable[[Handler], AnthropicTransport],
) -> None:
    finished = finished_of(await collect(make_transport(sse("plain_unlabeled_iteration"))))

    assert [item.model for item in finished.iterations] == [OPUS]


async def test_a_refusal_before_any_output_reaches_finished(
    make_transport: Callable[[Handler], AnthropicTransport],
) -> None:
    events = await collect(make_transport(sse("refusal_before_output")))

    (finished,) = events
    assert isinstance(finished, Finished)
    assert finished.stop_reason == "refusal"
    assert finished.stop_details == {
        "type": "refusal",
        "category": "general_harms",
        "explanation": "The request was declined by the safety filter.",
    }
    assert finished.message == {"role": "assistant", "content": []}


async def test_a_refusal_partway_through_reaches_finished_with_the_partial_text(
    make_transport: Callable[[Handler], AnthropicTransport],
) -> None:
    events = await collect(make_transport(sse("refusal_mid_stream")))

    assert events[:2] == [TextDelta("Here is how the policy works, and then"), TextBlockEnd(())]
    finished = finished_of(events)
    # The loop discards the partial text; the transport only reports what happened.
    assert finished.stop_reason == "refusal"
    assert finished.stop_details == {"type": "refusal"}
    assert finished.message["content"] == [
        {"type": "text", "text": "Here is how the policy works, and then"}
    ]


async def test_a_truncated_tool_call_is_never_emitted_for_dispatch(
    make_transport: Callable[[Handler], AnthropicTransport],
) -> None:
    events = await collect(make_transport(sse("max_tokens_tool")))

    # The SDK's tolerant parser keeps what it could read, so the input holds a cut-off `location`.
    # Only a call that ended in `tool_use` is handed on; the message still holds the dangling block.
    (finished,) = events
    assert isinstance(finished, Finished)
    assert finished.stop_reason == "max_tokens"
    assert [block["type"] for block in finished.message["content"]] == ["tool_use"]


async def test_json_that_cannot_be_parsed_is_an_invalid_tool_input(
    make_transport: Callable[[Handler], AnthropicTransport],
) -> None:
    with pytest.raises(InvalidToolInput):
        await collect(make_transport(sse("invalid_tool_json")))


async def test_any_other_value_error_from_the_sdks_stream_is_model_unavailable(
    make_transport: Callable[[Handler], AnthropicTransport], monkeypatch: pytest.MonkeyPatch
) -> None:
    # What the SDK raises when an event fails to decode is a ValueError (pydantic's is one). It is
    # not the model's tool JSON, and it comes from reading the stream, not from our own code.
    def fails_to_decode(**_kwargs: Any) -> None:
        raise ValueError("1 validation error for an event")

    monkeypatch.setattr(streaming_module, "accumulate_event", fails_to_decode)

    with pytest.raises(ModelUnavailable) as raised:
        await collect(make_transport(sse("text_with_citation")))

    assert isinstance(raised.value.__cause__, ValueError)


@pytest.mark.parametrize("bug", [RuntimeError("our bug"), AssertionError("our bug")])
async def test_a_bug_in_our_own_translation_is_not_reported_as_the_model_being_down(
    make_transport: Callable[[Handler], AnthropicTransport],
    monkeypatch: pytest.MonkeyPatch,
    bug: Exception,
) -> None:
    def broken(*_args: Any) -> list[ModelEvent]:
        raise bug

    monkeypatch.setattr(anthropic_transport, "_translate", broken)

    with pytest.raises(type(bug)) as raised:
        await collect(make_transport(sse("text_with_citation")))

    assert raised.value is bug


PRIVATE_WORDS = "my panic attacks at work"


async def test_an_invalid_tool_input_error_does_not_quote_the_input(
    make_transport: Callable[[Handler], AnthropicTransport],
) -> None:
    # The SDK's own message holds the raw tool input, which can be the person's words. Nothing
    # logs a question, so the error carries fixed text and only the chained cause has the SDK's.
    with pytest.raises(InvalidToolInput) as raised:
        await collect(make_transport(sse("invalid_tool_json_with_words")))

    assert PRIVATE_WORDS in str(raised.value.__cause__)
    assert PRIVATE_WORDS not in str(raised.value)


@pytest.mark.parametrize("bug", [ValueError, RuntimeError, AssertionError])
async def test_an_unreadable_stream_error_does_not_quote_what_the_sdk_quoted(
    make_transport: Callable[[Handler], AnthropicTransport],
    monkeypatch: pytest.MonkeyPatch,
    bug: type[Exception],
) -> None:
    def fails(**_kwargs: Any) -> None:
        raise bug(f"event failed to decode, input_value='{PRIVATE_WORDS}'")

    monkeypatch.setattr(streaming_module, "accumulate_event", fails)

    with pytest.raises(ModelUnavailable) as raised:
        await collect(make_transport(sse("text_with_citation")))

    assert PRIVATE_WORDS in str(raised.value.__cause__)
    assert PRIVATE_WORDS not in str(raised.value)


async def test_a_guard_error_does_not_quote_the_apis_error_body(
    make_transport: Callable[[Handler], AnthropicTransport],
) -> None:
    transport = make_transport(
        error_response(400, "invalid_request_error", f"messages.0: bad input {PRIVATE_WORDS}")
    )

    with pytest.raises(GuardUnavailable) as raised:
        await transport.classify(a_guard_request())

    assert PRIVATE_WORDS not in str(raised.value)


# --- Errors -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "error_type"),
    [
        (429, "rate_limit_error"),
        (500, "api_error"),
        (503, "api_error"),
        (529, "overloaded_error"),
        (401, "authentication_error"),
        (400, "invalid_request_error"),
    ],
)
async def test_an_api_error_after_the_sdks_retries_is_model_unavailable(
    make_transport: Callable[[Handler], AnthropicTransport], status: int, error_type: str
) -> None:
    transport = make_transport(error_response(status, error_type, "Something is wrong"))

    with pytest.raises(ModelUnavailable) as raised:
        await collect(transport)

    assert raised.value.status_code == status
    assert raised.value.request_id == "req_011TEST"


async def test_a_connection_error_is_model_unavailable(
    make_transport: Callable[[Handler], AnthropicTransport],
) -> None:
    def refuse(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("connection refused", request=request)

    with pytest.raises(ModelUnavailable) as raised:
        await collect(make_transport(refuse))

    assert raised.value.status_code is None


async def test_a_connection_error_text_is_fixed_and_not_the_sdks_message(
    make_transport: Callable[[Handler], AnthropicTransport], monkeypatch: pytest.MonkeyPatch
) -> None:
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")

    def fails(**_kwargs: Any) -> None:
        raise APIConnectionError(message=f"dropped while sending {PRIVATE_WORDS}", request=request)

    monkeypatch.setattr(streaming_module, "accumulate_event", fails)

    with pytest.raises(ModelUnavailable) as raised:
        await collect(make_transport(sse("text_with_citation")))

    assert PRIVATE_WORDS in str(raised.value.__cause__)
    assert PRIVATE_WORDS not in str(raised.value)
    assert "APIConnectionError" in str(raised.value)


async def test_any_other_sdk_error_opening_the_stream_is_model_unavailable(
    make_transport: Callable[[Handler], AnthropicTransport], monkeypatch: pytest.MonkeyPatch
) -> None:
    response = httpx2.Response(200, request=httpx2.Request("POST", "https://api.anthropic.com"))

    def fails_to_open(**_kwargs: Any) -> None:
        raise APIResponseValidationError(response, None, message=PRIVATE_WORDS)

    transport = make_transport(sse("text_with_citation"))
    monkeypatch.setattr(transport.client.beta.messages, "stream", fails_to_open)

    with pytest.raises(ModelUnavailable) as raised:
        await collect(transport)

    assert PRIVATE_WORDS not in str(raised.value)
    assert isinstance(raised.value.__cause__, APIResponseValidationError)


async def test_a_network_drop_in_the_middle_of_the_stream_is_model_unavailable(
    make_transport: Callable[[Handler], AnthropicTransport],
) -> None:
    body = (FIXTURES / "text_with_citation.sse").read_bytes()
    # Some of the stream arrives, then the connection dies. The SDK does not wrap this one.
    cut = body.index(b"event: content_block_stop", body.index(b"text_delta"))

    async def drops() -> AsyncIterator[bytes]:
        yield body[:cut]
        raise httpx2.ReadError("connection reset by peer")

    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=drops())

    transport = make_transport(handler)
    seen: list[ModelEvent] = []

    async def drain() -> None:
        async for event in transport.stream(a_request()):
            seen.append(event)

    with pytest.raises(ModelUnavailable) as raised:
        await drain()

    assert seen
    assert not any(isinstance(event, Finished) for event in seen)
    assert raised.value.status_code is None


@pytest.mark.parametrize(
    "response",
    [
        httpx2.Response(200, content=b"<html>", headers={"content-type": "text/html"}),
        httpx2.Response(200, content=b"", headers={"content-type": "text/event-stream"}),
        httpx2.Response(
            200,
            content=b"event: message_start\ndata: {oops\n\n",
            headers={"content-type": "text/event-stream"},
        ),
        httpx2.Response(
            200,
            content=b'event: content_block_stop\ndata: {"type":"content_block_stop","index":0}\n\n',
            headers={"content-type": "text/event-stream"},
        ),
    ],
    ids=["not_a_stream", "empty_stream", "garbage_event", "events_out_of_order"],
)
async def test_a_response_that_is_not_a_valid_stream_is_model_unavailable(
    make_transport: Callable[[Handler], AnthropicTransport], response: httpx2.Response
) -> None:
    with pytest.raises(ModelUnavailable):
        await collect(make_transport(lambda _request: response))


async def test_a_timeout_is_model_unavailable(
    make_transport: Callable[[Handler], AnthropicTransport],
) -> None:
    def too_slow(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout("timed out", request=request)

    with pytest.raises(ModelUnavailable):
        await collect(make_transport(too_slow))


async def test_an_error_event_in_the_middle_of_the_stream_is_model_unavailable(
    make_transport: Callable[[Handler], AnthropicTransport],
) -> None:
    transport = make_transport(sse("error_mid_stream"))
    seen: list[ModelEvent] = []

    async def drain() -> None:
        async for event in transport.stream(a_request()):
            seen.append(event)

    with pytest.raises(ModelUnavailable) as raised:
        await drain()

    assert seen == [TextDelta("The policy says")]
    # The stream's own status was 200, which says nothing about the failure.
    assert raised.value.status_code is None


async def test_the_consoles_spend_limit_is_its_own_error(
    make_transport: Callable[[Handler], AnthropicTransport],
) -> None:
    transport = make_transport(
        error_response(
            400,
            "invalid_request_error",
            "You have reached your specified API usage limits. You will regain access on"
            " 2026-11-01 at 00:00 UTC.",
        )
    )

    with pytest.raises(SpendLimitReached):
        await collect(transport)


async def test_any_other_bad_request_is_not_mistaken_for_the_spend_limit(
    make_transport: Callable[[Handler], AnthropicTransport],
) -> None:
    transport = make_transport(
        error_response(400, "invalid_request_error", "messages: roles must alternate")
    )

    with pytest.raises(ModelUnavailable) as raised:
        await collect(transport)

    assert raised.value.status_code == 400


# --- The request ------------------------------------------------------------------------------


async def test_the_outgoing_request_carries_the_betas_fallbacks_and_opus_settings(
    make_transport: Callable[[Handler], AnthropicTransport],
) -> None:
    captured: list[httpx2.Request] = []
    served = sse("text_with_citation")

    def handler(request: httpx2.Request) -> httpx2.Response:
        captured.append(request)
        return served(request)

    await collect(make_transport(handler))

    (request,) = captured
    body = json.loads(request.content)
    assert request.url.path == "/v1/messages"
    assert set(BETAS) <= set(request.headers["anthropic-beta"].split(","))
    assert body["stream"] is True
    assert body["model"] == OPUS
    assert body["max_tokens"] == 8000
    assert body["fallbacks"] == "default"
    assert body["thinking"] == {"type": "adaptive", "display": "updates"}
    assert body["output_config"] == {"effort": "low"}
    assert body["cache_control"] == {"type": "ephemeral"}
    assert body["system"] == [{"type": "text", "text": "You are Open Door."}]
    (tool,) = body["tools"]
    assert tool["strict"] is True
    assert tool["eager_input_streaming"] is True
    for forbidden in ("temperature", "top_p", "top_k", "tool_choice", "betas"):
        assert forbidden not in body


# --- The guard --------------------------------------------------------------------------------


def guard_message(
    *,
    text: str | None = '{"category":"sensitive","kind":"pay","injectionSuspected":false}',
    stop_reason: str = "end_turn",
) -> dict[str, Any]:
    content: list[dict[str, Any]] = [
        {"type": "thinking", "thinking": "A pay question.", "signature": "sig-haiku"}
    ]
    if text is not None:
        content.append({"type": "text", "text": text})
    return {
        "id": "msg_01Guard",
        "type": "message",
        "role": "assistant",
        "model": HAIKU,
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": 300,
            "output_tokens": 40,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        },
    }


def json_response(body: dict[str, Any]) -> Callable[[httpx2.Request], httpx2.Response]:
    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json=body)

    return handler


async def test_a_valid_guard_answer_parses_past_a_leading_thinking_block(
    make_transport: Callable[[Handler], AnthropicTransport],
) -> None:
    result = await make_transport(json_response(guard_message())).classify(a_guard_request())

    assert (result.category, result.kind, result.injection_suspected) == ("sensitive", "pay", False)
    assert result.usage == Usage(300, 40, 0, 0)
    assert result.served_by == HAIKU


GUARD_USAGE = Usage(300, 40, 0, 0)


@pytest.mark.parametrize(
    "message",
    [
        guard_message(text=None, stop_reason="refusal"),
        guard_message(stop_reason="max_tokens"),
        guard_message(text="not json at all"),
        guard_message(text='{"category":"ordinary"}'),
        guard_message(text='{"category":"maybe","kind":null,"injectionSuspected":false}'),
        guard_message(text=None),
    ],
    ids=["refusal", "max_tokens", "bad_json", "schema_mismatch", "bad_enum", "no_answer"],
)
async def test_a_guard_answer_that_cannot_be_trusted_is_unavailable_but_still_billed(
    make_transport: Callable[[Handler], AnthropicTransport], message: dict[str, Any]
) -> None:
    with pytest.raises(GuardUnavailable) as raised:
        await make_transport(json_response(message)).classify(a_guard_request())

    # The model ran, so its spend is carried for the budget to settle.
    assert raised.value.usage == GUARD_USAGE


@pytest.mark.parametrize("status", [400, 401, 429, 500, 529])
async def test_a_guard_api_error_is_unavailable_with_no_usage(
    make_transport: Callable[[Handler], AnthropicTransport], status: int
) -> None:
    transport = make_transport(error_response(status, "api_error", "nope"))

    with pytest.raises(GuardUnavailable) as raised:
        await transport.classify(a_guard_request())

    assert raised.value.usage is None


async def test_the_consoles_spend_limit_is_reported_by_the_guard_too(
    make_transport: Callable[[Handler], AnthropicTransport],
) -> None:
    # The guard runs first on every turn, so without this a spent limit would always read as
    # "the guard is unavailable" and hide the real cause.
    transport = make_transport(
        error_response(
            400,
            "invalid_request_error",
            "You have reached your specified API usage limits. You will regain access on"
            " 2026-11-01 at 00:00 UTC.",
        )
    )

    with pytest.raises(SpendLimitReached):
        await transport.classify(a_guard_request())


async def test_any_other_guard_bad_request_is_still_unavailable(
    make_transport: Callable[[Handler], AnthropicTransport],
) -> None:
    transport = make_transport(
        error_response(400, "invalid_request_error", "messages: roles must alternate")
    )

    with pytest.raises(GuardUnavailable):
        await transport.classify(a_guard_request())


@pytest.mark.parametrize(
    "response",
    [
        httpx2.Response(200, json={"unexpected": True}),
        httpx2.Response(200, content=b"<html>", headers={"content-type": "text/html"}),
        httpx2.Response(200, content=b"{oops", headers={"content-type": "application/json"}),
    ],
    ids=["wrong_shape", "not_json", "broken_json"],
)
async def test_a_malformed_guard_response_is_unavailable(
    make_transport: Callable[[Handler], AnthropicTransport], response: httpx2.Response
) -> None:
    with pytest.raises(GuardUnavailable) as raised:
        await make_transport(lambda _request: response).classify(a_guard_request())

    assert raised.value.usage is None


async def test_a_guard_body_that_breaks_while_being_read_is_unavailable(
    make_transport: Callable[[Handler], AnthropicTransport],
) -> None:
    async def breaks() -> AsyncIterator[bytes]:
        yield b'{"id": "msg_1", '
        raise httpx2.ReadError("connection reset by peer")

    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, headers={"content-type": "application/json"}, content=breaks())

    with pytest.raises(GuardUnavailable) as raised:
        await make_transport(handler).classify(a_guard_request())

    assert raised.value.usage is None


async def test_a_guard_connection_error_is_unavailable_with_no_usage(
    make_transport: Callable[[Handler], AnthropicTransport],
) -> None:
    def refuse(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("connection refused", request=request)

    with pytest.raises(GuardUnavailable) as raised:
        await make_transport(refuse).classify(a_guard_request())

    assert raised.value.usage is None


async def test_a_slow_guard_is_unavailable(
    make_transport: Callable[[Handler], AnthropicTransport], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def slow(_request: httpx2.Request) -> httpx2.Response:
        await asyncio.sleep(5)
        return httpx2.Response(200, json=guard_message())

    assert GUARD_TIMEOUT_SECONDS == 4
    monkeypatch.setattr(anthropic_transport, "GUARD_TIMEOUT_SECONDS", 0.05)

    with pytest.raises(GuardUnavailable) as raised:
        await make_transport(slow).classify(a_guard_request())

    assert raised.value.usage is None


async def test_the_outgoing_guard_request_asks_for_structured_output_and_no_sampling(
    make_transport: Callable[[Handler], AnthropicTransport],
) -> None:
    captured: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        captured.append(request)
        return httpx2.Response(200, json=guard_message())

    await make_transport(handler).classify(a_guard_request())

    (request,) = captured
    body = json.loads(request.content)
    assert request.url.path == "/v1/messages"
    assert body["model"] == HAIKU
    assert body["max_tokens"] == 1024
    assert body["system"] == "Classify the message."
    assert body["output_config"]["effort"] == "low"
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert body["output_config"]["format"]["schema"]["additionalProperties"] is False
    for forbidden in ("temperature", "top_p", "top_k", "thinking", "tool_choice", "stream"):
        assert forbidden not in body


# --- The factory ------------------------------------------------------------------------------


def settings_with(key: str | None) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url="postgresql+asyncpg://opendoor:opendoor@127.0.0.1:1/opendoor",
        ai_transport="scripted",
        anthropic_api_key=SecretStr(key) if key else None,
    )


async def test_the_production_client_keeps_two_retries_and_a_bounded_timeout() -> None:
    transport = from_settings(settings_with("sk-ant-test"))

    assert transport.client.max_retries == 2
    timeout = transport.client.timeout
    assert isinstance(timeout, Timeout)
    assert timeout.connect == MODEL_CONNECT_TIMEOUT_SECONDS == 10
    assert timeout.read == MODEL_READ_TIMEOUT_SECONDS == 90
    # Three attempts, each at worst a connect wait and a read wait, must end well inside the ten
    # minutes after which a running turn is treated as abandoned.
    worst_case_seconds = 3 * (MODEL_CONNECT_TIMEOUT_SECONDS + MODEL_READ_TIMEOUT_SECONDS)
    assert worst_case_seconds < 10 * 60
    await transport.client.close()


def test_the_factory_refuses_to_build_without_a_key() -> None:
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        from_settings(settings_with(None))


async def test_canceling_the_stream_still_closes_the_response(
    make_transport: Callable[[Handler], AnthropicTransport],
) -> None:
    import anyio

    body = (FIXTURES / "text_with_citation.sse").read_bytes()
    cut = body.index(b"event: content_block_stop", body.index(b"text_delta"))
    closed: list[bool] = []
    first_chunk_sent = asyncio.Event()

    class HangingBody(httpx2.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield body[:cut]
            first_chunk_sent.set()
            await asyncio.sleep(3600)

        async def aclose(self) -> None:
            # Closing needs a checkpoint, which a canceled, unshielded close would not get.
            await anyio.lowlevel.checkpoint()
            closed.append(True)

    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200, headers={"content-type": "text/event-stream"}, stream=HangingBody()
        )

    transport = make_transport(handler)

    async def drain() -> None:
        async for _ in transport.stream(a_request()):
            pass

    async with asyncio.timeout(5):
        async with anyio.create_task_group() as group:
            group.start_soon(drain)
            await first_chunk_sent.wait()
            await asyncio.sleep(0.05)
            group.cancel_scope.cancel()

    assert closed == [True], "the response stays open, and the upstream call keeps generating"


async def test_a_normal_completion_closes_the_response_once(
    make_transport: Callable[[Handler], AnthropicTransport],
) -> None:
    body = (FIXTURES / "text_with_citation.sse").read_bytes()
    closes: list[bool] = []

    class CountingBody(httpx2.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield body

        async def aclose(self) -> None:
            closes.append(True)

    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200, headers={"content-type": "text/event-stream"}, stream=CountingBody()
        )

    await collect(make_transport(handler))

    assert closes == [True]


async def test_the_guard_call_sends_exactly_what_the_replay_fingerprints(
    make_transport: Callable[[Handler], AnthropicTransport],
) -> None:
    """The replay keys a guard call by `guard_api_kwargs`, so the SDK must be sent that and nothing
    else: a recording of one request has to be the request that was sent."""
    captured: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        captured.append(request)
        return httpx2.Response(200, json=guard_message())

    guard_request = a_guard_request()
    await make_transport(handler).classify(guard_request)

    (request,) = captured
    assert json.loads(request.content) == guard_api_kwargs(guard_request)
