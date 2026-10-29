"""The Anthropic case summarizer, against hand-written responses served by a mock.

Nothing here reaches the network. The words in these tests are a canary, and no error text may hold
them: a summary call's failures carry names, never the person's words or the model's text.
"""

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx2
import pytest
from anthropic import AsyncAnthropic

from app.ai.anthropic_transport import AnthropicSummarizer
from app.ai.case_summary import (
    SummaryRefused,
    SummaryUnavailable,
    build_summary_request,
    summary_api_kwargs,
)
from app.ai.pricing import Usage
from app.ai.prompts.versions import CASE_SUMMARY_PROMPT_VERSION
from app.ai.transport import SpendLimitReached

CANARY = "ZEBRA-CANARY-7731"
WORDS = f"My lead moved my shift on Tuesday and did not tell me. {CANARY}"
SUMMARY = "The person says their lead moved their shift on Tuesday without telling them."
Handler = Callable[[httpx2.Request], httpx2.Response]


def message(
    text: str | None = json.dumps({"summary": SUMMARY}), stop_reason: str = "end_turn"
) -> dict[str, Any]:
    content: list[dict[str, Any]] = [{"type": "thinking", "thinking": "", "signature": "sig"}]
    if text is not None:
        content.append({"type": "text", "text": text})
    return {
        "id": "msg_01Summary",
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-5-5",
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": 500,
            "output_tokens": 90,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        },
    }


def respond(body: dict[str, Any]) -> Handler:
    return lambda _request: httpx2.Response(200, json=body)


def error_response(status: int, message_text: str = "nope") -> Handler:
    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            status,
            headers={"request-id": "req_011TEST"},
            json={
                "type": "error",
                "error": {"type": "invalid_request_error", "message": message_text},
            },
        )

    return handler


@pytest.fixture
async def make() -> AsyncIterator[Callable[[Handler], AnthropicSummarizer]]:
    clients: list[AsyncAnthropic] = []

    def build(handler: Handler) -> AnthropicSummarizer:
        client = AsyncAnthropic(
            api_key="test-key",
            http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
            max_retries=0,
        )
        clients.append(client)
        return AnthropicSummarizer(client)

    yield build
    for client in clients:
        await client.close()


async def test_a_good_answer_is_the_summary_with_its_model_version_and_usage(
    make: Callable[[Handler], AnthropicSummarizer],
) -> None:
    answer = await make(respond(message())).summarize(build_summary_request("pay", WORDS))

    assert answer.text == SUMMARY
    assert (answer.model, answer.prompt_version) == ("claude-opus-5-5", CASE_SUMMARY_PROMPT_VERSION)
    assert answer.usage == Usage(500, 90, 0, 0)


async def test_the_call_sent_is_exactly_what_the_replay_fingerprints(
    make: Callable[[Handler], AnthropicSummarizer],
) -> None:
    sent: list[dict[str, Any]] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        sent.append(json.loads(request.content))
        return httpx2.Response(200, json=message())

    request = build_summary_request("pay", WORDS)
    await make(handler).summarize(request)

    kwargs = summary_api_kwargs(request)
    assert sent == [json.loads(json.dumps(kwargs))]
    assert "tools" not in sent[0]
    assert sent[0]["output_config"]["effort"] == "low"
    assert "temperature" not in sent[0]
    assert "<case_words>" in sent[0]["messages"][0]["content"]


@pytest.mark.parametrize(
    ("body", "error"),
    [
        (message(text=None, stop_reason="refusal"), SummaryRefused),
        (message(stop_reason="max_tokens"), SummaryUnavailable),
        (message(text="not json at all"), SummaryUnavailable),
        (message(text="[]"), SummaryUnavailable),
        (message(text='{"summary": 3}'), SummaryUnavailable),
        (message(text='{"summary": "a", "extra": "b"}'), SummaryUnavailable),
        (message(text='{"other": "a"}'), SummaryUnavailable),
        (message(text=None), SummaryUnavailable),
    ],
    ids=[
        "refusal",
        "max_tokens",
        "bad_json",
        "not_an_object",
        "wrong_type",
        "extra_key",
        "wrong_key",
        "no_answer",
    ],
)
async def test_an_answer_that_cannot_be_used_is_a_typed_error_that_still_carries_its_cost(
    make: Callable[[Handler], AnthropicSummarizer], body: dict[str, Any], error: type[Exception]
) -> None:
    with pytest.raises(error) as raised:
        await make(respond(body)).summarize(build_summary_request("pay", WORDS))

    assert type(raised.value) is error
    assert raised.value.usage == Usage(500, 90, 0, 0)  # type: ignore[attr-defined]


@pytest.mark.parametrize("status", [400, 401, 429, 500, 529])
async def test_an_api_error_is_unavailable_with_no_usage_and_does_not_quote_the_body(
    make: Callable[[Handler], AnthropicSummarizer], status: int
) -> None:
    with pytest.raises(SummaryUnavailable) as raised:
        await make(error_response(status, f"bad input {CANARY}")).summarize(
            build_summary_request("pay", WORDS)
        )

    assert raised.value.usage is None
    assert CANARY not in str(raised.value)


async def test_the_consoles_spend_limit_is_its_own_error(
    make: Callable[[Handler], AnthropicSummarizer],
) -> None:
    handler = error_response(
        400, "You have reached your specified API usage limits. You will regain access soon."
    )

    with pytest.raises(SpendLimitReached):
        await make(handler).summarize(build_summary_request("pay", WORDS))


@pytest.mark.parametrize(
    "response",
    [
        httpx2.Response(200, json={"unexpected": True}),
        httpx2.Response(200, content=b"<html>", headers={"content-type": "text/html"}),
        httpx2.Response(200, content=b"{oops", headers={"content-type": "application/json"}),
    ],
    ids=["wrong_shape", "not_json", "broken_json"],
)
async def test_a_response_that_is_not_a_message_is_unavailable(
    make: Callable[[Handler], AnthropicSummarizer], response: httpx2.Response
) -> None:
    with pytest.raises(SummaryUnavailable) as raised:
        await make(lambda _request: response).summarize(build_summary_request("pay", WORDS))

    assert raised.value.usage is None


async def test_a_dropped_connection_is_unavailable(
    make: Callable[[Handler], AnthropicSummarizer],
) -> None:
    def refuse(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("connection refused", request=request)

    with pytest.raises(SummaryUnavailable) as raised:
        await make(refuse).summarize(build_summary_request("pay", WORDS))

    assert raised.value.usage is None


async def test_the_sdks_own_timeout_is_a_timeout_not_unavailable(
    make: Callable[[Handler], AnthropicSummarizer],
) -> None:
    def too_slow(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout("read timed out", request=request)

    with pytest.raises(TimeoutError):
        await make(too_slow).summarize(build_summary_request("pay", WORDS))


async def test_the_summarizer_has_no_time_limit_of_its_own(
    make: Callable[[Handler], AnthropicSummarizer],
) -> None:
    # `generate_summary` bounds the call (tests/integration/test_case_summary_task.py); a second
    # limit here would only be a copy of it.
    async def slow(_request: httpx2.Request) -> httpx2.Response:
        await asyncio.sleep(0.2)
        return httpx2.Response(200, json=message())

    request = build_summary_request("pay", WORDS)
    object.__setattr__(request, "timeout_seconds", 0.05)

    answer = await make(slow).summarize(request)  # type: ignore[arg-type]

    assert answer.text
