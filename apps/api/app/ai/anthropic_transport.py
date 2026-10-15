"""The real transport: streams the assistant model and runs the guard through the Anthropic SDK.

This is the only module that turns the SDK's types into the transport's (app/ai/transport.py). The
rest of the API sees `StatusNote`, `TextDelta`, `TextBlockEnd`, `ToolCall`, and `Finished`, and the
typed errors, and never an SDK object.

The SDK is built on httpx2, not httpx: anything handed to it (a client, a transport, a timeout)
must come from httpx2.
"""

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable
from typing import Any, cast

import httpx2
from anthropic import (
    APIConnectionError,
    APIError,
    APIResponseValidationError,
    APIStatusError,
    AsyncAnthropic,
    BadRequestError,
    Timeout,
)
from anthropic.lib.streaming import ParsedBetaMessageStreamEvent
from anthropic.types import MessageParam, OutputConfigParam
from anthropic.types import Usage as ApiUsage
from anthropic.types.beta import (
    BetaFallbackMessageIterationUsage,
    BetaMessageIterationUsage,
    BetaUsage,
)
from anthropic.types.beta.parsed_beta_message import ParsedBetaMessage

from app.ai.pricing import IterationUsage, Usage, dearer_model
from app.ai.transport import (
    GUARD_MAX_TOKENS,
    GUARD_OUTPUT_SCHEMA,
    GUARD_TIMEOUT_SECONDS,
    Finished,
    GuardRequest,
    GuardResult,
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
    parse_guard_output,
)
from app.core.config import Settings

# The SDK's default timeout is 10 minutes, and with two retries a stalled call could run about 30
# minutes. A turn running longer than 10 minutes is treated as abandoned and a second one may start
# while the first is still billing, so every wait is bounded. The read timeout is the longest gap
# between stream events we tolerate. It resets with each event, so it bounds a stall, not a long
# answer: a call that fails to connect or stalls gives up within 3 attempts x (10 s connect + 90 s
# read) = 300 s, but a slow, steady stream has no total limit here. The turn's own deadline, below
# the 10 minutes, is what bounds the whole turn (Stage 2's loop).
MODEL_MAX_RETRIES = 2
MODEL_CONNECT_TIMEOUT_SECONDS = 10
MODEL_READ_TIMEOUT_SECONDS = 90
MODEL_WRITE_TIMEOUT_SECONDS = 30
MODEL_POOL_TIMEOUT_SECONDS = 10

_GUARD_OUTPUT_CONFIG: OutputConfigParam = {
    "effort": "low",
    "format": {"type": "json_schema", "schema": GUARD_OUTPUT_SCHEMA},
}

# A spend limit set in the Console arrives as a 400 whose message starts like this.
SPEND_LIMIT_MESSAGE_PREFIX = "You have reached your specified API usage limits"
# Error texts are fixed, never the SDK's own message: that can quote the raw tool input or response
# body, which can hold the person's words, and nothing logs a question, an answer, or a tool result.
# The SDK's message stays on the chained cause. Only exception types, status codes, and request IDs
# go into the text.
INVALID_TOOL_INPUT_TEXT = "the model's tool input was not valid JSON"
UNREADABLE_RESPONSE_TEXT = "the model API sent a response that could not be read"
SPEND_LIMIT_TEXT = "the Anthropic Console spend limit has been reached"
# When a response stops at max_tokens, the API leaves this in place of the unfinished work.
INTERRUPTED_NOTE = "This part of the response was interrupted before it finished."
# What the SDK says when it can't parse a tool input at all (anthropic 1.x, lib/streaming).
UNPARSABLE_TOOL_INPUT_PREFIX = "Unable to parse tool parameter JSON"
# Blocks that can't be echoed back once a fallback model has taken over: they are tied to the
# model that wrote them, and the API refuses a request that carries them across the boundary.
_NOT_ECHOED_BEFORE_A_FALLBACK = frozenset({"thinking", "redacted_thinking", "tool_use"})


class AnthropicTransport:
    def __init__(self, client: AsyncAnthropic) -> None:
        self.client = client

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        # Tool calls are held until the stream ends. One that comes before a fallback block was
        # written by the model that declined, and it is not in the message we store (see
        # `_echoable_content`), so running it would answer a call the history never made.
        pending_tools: list[ToolCall] = []
        try:
            async with self.client.beta.messages.stream(**request.to_api_kwargs()) as stream:
                events = aiter(stream)
                while True:
                    try:
                        raw = await _sdk_read(anext(events))
                    except StopAsyncIteration:
                        break
                    except ValueError as error:
                        # This try wraps only the SDK reading the stream, so every ValueError here
                        # is the SDK's, never ours. Unparsable tool JSON is the one the loop can
                        # recover from; any other (an event that fails to decode, say) means the
                        # stream was not readable, and the typed API errors are caught below.
                        if str(error).startswith(UNPARSABLE_TOOL_INPUT_PREFIX):
                            raise InvalidToolInput(INVALID_TOOL_INPUT_TEXT) from error
                        raise ModelUnavailable(
                            f"{UNREADABLE_RESPONSE_TEXT} ({type(error).__name__})"
                        ) from error
                    for event in _translate(raw, pending_tools):
                        yield event
                final = await _sdk_read(stream.get_final_message())
        except APIStatusError as error:
            raise _unavailable_or_spend_limit(error) from error
        except APIConnectionError as error:
            # A timeout is a connection error to the SDK.
            raise ModelUnavailable(
                f"the model API could not be reached ({type(error).__name__})"
            ) from error
        except httpx2.HTTPError as error:
            # The SDK wraps errors from opening the request, but not one raised while reading an
            # open stream (a dropped connection behind a proxy), which arrives as httpx2's own.
            raise ModelUnavailable(
                f"the model API stream broke ({type(error).__name__})"
            ) from error
        except APIError as error:
            # Any other error the SDK raises while opening or reading the stream.
            raise ModelUnavailable(f"the model API failed ({type(error).__name__})") from error
        # A call that stopped for any other reason (max_tokens, refusal) may hold a tool_use with a
        # truncated input. It is never handed on, so it can't be run.
        if final.stop_reason == "tool_use":
            for call in pending_tools:
                yield call
        yield _finished(final, requested_model=request.model)

    async def classify(self, request: GuardRequest) -> GuardResult:
        try:
            async with asyncio.timeout(GUARD_TIMEOUT_SECONDS):
                response = await self.client.messages.create(
                    model=request.model,
                    max_tokens=GUARD_MAX_TOKENS,
                    output_config=_GUARD_OUTPUT_CONFIG,
                    system=request.system,
                    # Plain role/content dicts, which is what the API takes.
                    messages=cast(list[MessageParam], list(request.messages)),
                )
        except TimeoutError:
            raise GuardUnavailable("the guard did not answer in time") from None
        except APIStatusError as error:
            # The same limit the assistant call reports, so it isn't hidden as a broken guard.
            if isinstance(error, BadRequestError) and _is_spend_limit(error.body):
                raise SpendLimitReached(SPEND_LIMIT_TEXT) from error
            raise GuardUnavailable(
                f"the guard's call failed (status {error.status_code}, {error.type})"
            ) from error
        except (APIError, httpx2.HTTPError, json.JSONDecodeError) as error:
            # Connection errors, a body that failed validation, and a 200 whose body is broken JSON
            # all leave the guard with no answer. Nothing was reported, so there is no usage.
            raise GuardUnavailable(f"the guard's call failed ({type(error).__name__})") from error
        try:
            # Haiku has no fallback, so a refusal is final. A response can begin with thinking
            # blocks, so the answer is found by type, never by position.
            usage = _usage(response.usage)
            if response.stop_reason != "end_turn":
                raise GuardUnavailable(
                    f"the guard stopped with {response.stop_reason!r}", usage=usage
                )
            answer = "".join(block.text for block in response.content if block.type == "text")
            served_by = response.model
        except (AttributeError, TypeError) as error:
            # A 200 that isn't a message at all (an error page): the SDK hands back the raw text.
            raise GuardUnavailable(
                f"the guard's response could not be read ({type(error).__name__})"
            ) from error
        return parse_guard_output(answer, usage=usage, served_by=served_by)


def from_settings(settings: Settings) -> AnthropicTransport:
    if settings.anthropic_api_key is None:
        raise ValueError("the anthropic transport needs ANTHROPIC_API_KEY")
    # Two retries is the SDK's default, spelled out: it covers 408, 409, 429, 5xx, and connection
    # errors, so a transient failure never reaches the person asking.
    return AnthropicTransport(
        AsyncAnthropic(
            api_key=settings.anthropic_api_key.get_secret_value(),
            max_retries=MODEL_MAX_RETRIES,
            timeout=Timeout(
                connect=MODEL_CONNECT_TIMEOUT_SECONDS,
                read=MODEL_READ_TIMEOUT_SECONDS,
                write=MODEL_WRITE_TIMEOUT_SECONDS,
                pool=MODEL_POOL_TIMEOUT_SECONDS,
            ),
        )
    )


async def _sdk_read[T](read: Awaitable[T]) -> T:
    """Await one read of the SDK's stream, and only that.

    A 200 that is not a stream we can read (a proxy's error page, an empty body, an event the SDK
    can't decode, or events out of order) fails in the SDK with errors it doesn't type. They are
    caught around its reads alone: a RuntimeError or AssertionError from our own code must stay what
    it is, not be reported to the person as the model being down.
    """
    try:
        return await read
    except (
        APIResponseValidationError,
        json.JSONDecodeError,
        RuntimeError,
        AssertionError,
    ) as error:
        raise ModelUnavailable(f"{UNREADABLE_RESPONSE_TEXT} ({type(error).__name__})") from error


def _unavailable_or_spend_limit(error: APIStatusError) -> Exception:
    if isinstance(error, BadRequestError) and _is_spend_limit(error.body):
        return SpendLimitReached(SPEND_LIMIT_TEXT)
    # An `event: error` partway through a stream is raised with the stream's own 200 status, which
    # says nothing about the failure, so only a real error status is reported.
    status = error.status_code if error.status_code >= 400 else None
    return ModelUnavailable(
        f"the model API failed ({status or 'in the stream'}, {error.type or 'unknown error'})",
        status_code=status,
        request_id=error.request_id,
    )


def _is_spend_limit(body: object) -> bool:
    if not isinstance(body, dict):
        return False
    detail = body.get("error")
    if not isinstance(detail, dict):
        return False
    message = detail.get("message")
    return isinstance(message, str) and message.startswith(SPEND_LIMIT_MESSAGE_PREFIX)


def _translate(
    raw: ParsedBetaMessageStreamEvent, pending_tools: list[ToolCall]
) -> list[ModelEvent]:
    """One SDK event as zero or more of ours.

    Text streams from the helper's `text` events. Everything else waits for its block to stop, when
    the SDK's accumulated block is complete: a progress note is a whole thinking block, and a
    citation is on the text block it belongs to.
    """
    if raw.type == "text":
        return [TextDelta(raw.text)]
    if raw.type == "content_block_start":
        if raw.content_block.type == "fallback":
            # Everything the declined model wrote before this point is gone from the history.
            pending_tools.clear()
        return []
    if raw.type != "content_block_stop":
        return []
    block = raw.content_block
    if block.type == "thinking":
        note = block.thinking.strip()
        # Empty thinking is reasoning, kept but never shown. The interrupted sentence is the API's
        # stand-in for unfinished work, not something the model said.
        if note and note != INTERRUPTED_NOTE:
            return [StatusNote(note)]
    elif block.type == "text":
        return [TextBlockEnd(tuple(_search_result_citations(block.citations or [])))]
    elif block.type == "tool_use":
        pending_tools.append(ToolCall(block.id, block.name, dict(block.input)))
    return []


def _search_result_citations(citations: list[Any]) -> list[SearchResultCitation]:
    """Our `search_result_location` citations. Any other kind isn't ours and is ignored."""
    return [
        SearchResultCitation(
            search_result_index=citation.search_result_index,
            start_block_index=citation.start_block_index,
            end_block_index=citation.end_block_index,
            source=citation.source,
            title=citation.title,
            cited_text=citation.cited_text,
        )
        for citation in citations
        if citation.type == "search_result_location"
    ]


def _finished(final: ParsedBetaMessage[Any], *, requested_model: str) -> Finished:
    if final.stop_reason is None:
        raise ModelUnavailable("the model API ended the stream without a stop reason")
    blocks = [
        block.model_dump(mode="json", exclude_none=True, by_alias=True) for block in final.content
    ]
    usage = _usage(final.usage)
    entries = [
        item
        for item in final.usage.iterations or ()
        # Compaction and advisor entries don't occur here, and aren't this call's model usage.
        if isinstance(item, BetaMessageIterationUsage | BetaFallbackMessageIterationUsage)
    ]
    # Only the API's own signals say a fallback happened: a `fallback_message` entry (it names the
    # model that served) or a `fallback` block. Comparing model names would call the same model in
    # another form (a dated snapshot ID) a fallback.
    served = [item.model for item in entries if isinstance(item, BetaFallbackMessageIterationUsage)]
    fell_back = bool(served) or any(block["type"] == "fallback" for block in blocks)
    serving_model = served[-1] if served else final.model
    # A `message` entry may name no model, which means the requested one. After a fallback the SDK
    # does not say whether the serving hop's earlier loop iterations name theirs, so one with no
    # name could be either model. It is counted at the dearer: better to count too much than too
    # little.
    unlabeled = dearer_model(requested_model, serving_model) if fell_back else requested_model
    iterations = tuple(
        IterationUsage(item.model or unlabeled, _usage(item)) for item in entries
    ) or (
        # No breakdown: the whole call is one attempt. It is priced as asked unless the API
        # signaled a fallback, because the model name it echoes can be a dated ID that has no
        # pinned price, and that would be charged at the dearest rates.
        IterationUsage(serving_model if fell_back else requested_model, usage),
    )
    stop_details = (
        final.stop_details.model_dump(
            mode="json", exclude_none=True, exclude={"fallback_credit_token"}
        )
        if final.stop_details is not None
        else None
    )
    return Finished(
        message={"role": "assistant", "content": _echoable_content(blocks)},
        stop_reason=final.stop_reason,
        stop_details=stop_details,
        usage=usage,
        iterations=iterations,
        served_by=serving_model,
    )


def _echoable_content(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The content to store and send back, after a fallback and without blank text.

    When a fallback model finishes what another began, the thinking and tool calls written before
    the last fallback block can't go back to the API. Text before it stays, and everything after it
    is kept as written. The fallback blocks are only markers and are dropped. This is applied once,
    here, because the history is append-only and a stored message can't be fixed later.

    A text block that is blank (the model can write two newlines before a tool call) carries
    nothing, and the API refuses it when it is sent back, so it is dropped here too. Thinking
    blocks are not text: an empty, signed one is normal and must be kept as it is.
    """
    boundary = max((i for i, block in enumerate(blocks) if block["type"] == "fallback"), default=-1)
    return [
        block
        for index, block in enumerate(blocks)
        if block["type"] != "fallback"
        and not (block["type"] == "text" and not str(block.get("text", "")).strip())
        and not (index < boundary and block["type"] in _NOT_ECHOED_BEFORE_A_FALLBACK)
    ]


def _usage(
    usage: ApiUsage | BetaUsage | BetaMessageIterationUsage | BetaFallbackMessageIterationUsage,
) -> Usage:
    return Usage(
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cache_read_tokens=usage.cache_read_input_tokens or 0,
        cache_write_tokens=usage.cache_creation_input_tokens or 0,
    )
