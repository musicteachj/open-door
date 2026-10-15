"""The one interface every model transport answers: the real Anthropic API, the scripted stand-in,
and the replay of recorded runs (ADR 0010).

The loop and the guard talk only to `Transport`, so they run the same code against all three. This
module defines the request, the normalized events, and the errors, and it imports no SDK: the
scripted and replay transports import it too, and they must work without the SDK's types.
"""

import copy
import json
from collections.abc import AsyncIterator, Iterable, Iterator
from dataclasses import dataclass
from typing import Any, Literal, Protocol, get_args

from app.ai.pricing import IterationUsage, Usage
from app.core.config import Settings

# The beta header that `fallbacks` only works with.
FALLBACK_BETA = "server-side-fallback-2026-07-01"

# --- Requests ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelRequest:
    """One call to the assistant model, with everything that goes into it.

    The tuples keep the request from being changed after it is built. `to_api_kwargs` is the one
    place that turns it into what the API receives, so a replay can fingerprint exactly that.
    """

    model: str
    system: tuple[dict[str, Any], ...]
    tools: tuple[dict[str, Any], ...]
    messages: tuple[dict[str, Any], ...]
    effort: str
    max_tokens: int
    betas: tuple[str, ...]
    # "default" asks the API to retry a safety-filter decline on its own fallback model. It only
    # works with the server-side-fallback beta, so the two travel together.
    fallbacks: str | None = "default"

    def __post_init__(self) -> None:
        # Without the beta the API answers every call with a 400, which would read as an outage.
        if self.fallbacks is not None and FALLBACK_BETA not in self.betas:
            raise ValueError(f"fallbacks={self.fallbacks!r} needs the {FALLBACK_BETA} beta")

    def to_api_kwargs(self) -> dict[str, Any]:
        """The keyword arguments for `client.beta.messages.stream`, as plain JSON-able data.

        Pure and deterministic. Opus 5.5 takes no sampling settings, no `thinking: disabled`, and no
        forced `tool_choice`, so none are ever sent; effort is the only control and is always set,
        because the API's own default is higher. Every tool is strict (its input is checked against
        its schema) and streams its input eagerly, which is why the loop validates inputs itself.
        """
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "betas": list(self.betas),
            "thinking": {"type": "adaptive", "display": "updates"},
            "output_config": {"effort": self.effort},
            # Automatic caching: the API puts a breakpoint at the end of the conversation on every
            # call, so a tool loop and a later turn read the history from the cache, not at the
            # full input rate. It is a request parameter, never part of a message, so the stored
            # history stays byte for byte as written. The system block keeps its own breakpoint.
            # The first live proof is Stage 3's smoke run (`usage.cache_read_input_tokens` above
            # zero on later calls).
            "cache_control": {"type": "ephemeral"},
            "system": copy.deepcopy(list(self.system)),
            "tools": [
                {**copy.deepcopy(tool), "strict": True, "eager_input_streaming": True}
                for tool in self.tools
            ],
            "messages": copy.deepcopy(list(self.messages)),
        }
        if self.fallbacks is not None:
            kwargs["fallbacks"] = self.fallbacks
        return kwargs


# The guard sits in front of every message. It gets this long, retries included, and no longer.
GUARD_TIMEOUT_SECONDS = 4
GUARD_MAX_TOKENS = 1024  # Its thinking counts toward this.
# The guard wraps the person's new message in this tag, and the previous answer sits beside it. The
# scripted guard reads only what is inside the tag.
GUARD_NEW_MESSAGE_TAG = "new_message"

GuardCategory = Literal["ordinary", "sensitive", "crisis"]
GuardKind = Literal[
    "harassment_discrimination",
    "safety",
    "medical_accommodation",
    "pay",
    "self_harm",
    "threat_of_violence",
    "other",
]
_CATEGORIES: tuple[str, ...] = get_args(GuardCategory)
_KINDS: tuple[str, ...] = get_args(GuardKind)

GUARD_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": list(_CATEGORIES)},
        "kind": {"anyOf": [{"type": "string", "enum": list(_KINDS)}, {"type": "null"}]},
        "injectionSuspected": {"type": "boolean"},
    },
    "required": ["category", "kind", "injectionSuspected"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class GuardRequest:
    """The guard's one call, ready to send. The prompt and the wrapping of the untrusted text are
    built by the guard (app/ai/guard.py), not here."""

    model: str
    system: str
    messages: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class GuardResult:
    category: GuardCategory
    kind: GuardKind | None
    injection_suspected: bool
    usage: Usage
    served_by: str


# --- Events -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class SearchResultCitation:
    """A citation the model made to one block range of one `search_result` it was sent."""

    # 0-based among every search_result block in the request, across messages and tool results.
    search_result_index: int
    start_block_index: int
    # Exclusive: a citation of only block 0 is start 0, end 1.
    end_block_index: int
    source: str
    title: str | None
    cited_text: str


@dataclass(frozen=True)
class StatusNote:
    """A short progress note from the model ("Looking up the sick leave policy")."""

    text: str


@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class TextBlockEnd:
    """A text block ended. The citations are the ones its text carries, so a marker can be placed at
    the end of the cited text rather than somewhere in the middle of a sentence."""

    citations: tuple[SearchResultCitation, ...]


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]


@dataclass(frozen=True)
class Finished:
    """The call is over. `message` is the assistant message to send back unchanged.

    For a `refusal` or `max_tokens` stop, `message` may hold no content at all, partial text, or a
    `tool_use` block with a truncated input. No `ToolCall` is emitted for it, and the transport does
    not decide what to store: the loop does.
    """

    message: dict[str, Any]
    stop_reason: str
    # Why the model refused, when it did. Information for the audit trail; it is never shown.
    stop_details: dict[str, Any] | None
    # The attempt that produced this message, not the whole call: a declined attempt before a
    # fallback is only in `iterations`. The next reservation passes this `Usage` itself to
    # `estimate_input_tokens`, never `.input_tokens` alone, which leaves out the cached tokens.
    usage: Usage
    # Each attempt in the call, at the model that served it, so a fallback is priced correctly.
    # This is the source of truth for what the call spent (see `pricing.total_usage`).
    iterations: tuple[IterationUsage, ...]
    served_by: str
    # True when the API itself signaled a fallback (a `fallback_message` iteration or a `fallback`
    # block), never from comparing model names. The loop records it on the turn.
    fell_back: bool = False


ModelEvent = StatusNote | TextDelta | TextBlockEnd | ToolCall | Finished


# --- Errors -----------------------------------------------------------------------------------


class ModelUnavailable(Exception):  # noqa: N818
    """The model could not be reached or kept failing, after the SDK's own retries.

    No usage is reported with it. The cost is unknown (the call may have been billed before it
    failed), so the caller keeps the reservation and doesn't settle it to zero.
    """

    def __init__(
        self, message: str, *, status_code: int | None = None, request_id: str | None = None
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.request_id = request_id


class SpendLimitReached(Exception):  # noqa: N818
    """The spend limit set in the Anthropic Console has been reached."""


class InvalidToolInput(Exception):  # noqa: N818
    """The model's tool input was JSON that could not be parsed at all.

    It is raised from the middle of the stream: events before it may already have been yielded (text
    the person has seen), and no `Finished` follows, so nothing of this call is complete or stored.
    """


class GuardUnavailable(Exception):  # noqa: N818
    """The guard gave no usable answer: an error, a refusal, a timeout, or output off the schema.

    `usage` is what the model used when it did answer but the answer was unusable (a refusal, a
    cut-off, bad JSON, or output off the schema), so the budget can settle that spend.

    `usage` is None when the cost is unknown (an error or a timeout, possibly after the call was
    billed). The caller keeps the reservation and doesn't settle it to zero.
    """

    def __init__(self, message: str, *, usage: Usage | None = None) -> None:
        super().__init__(message)
        self.usage = usage


# --- The guard's answer -----------------------------------------------------------------------


def parse_guard_output(text: str, *, usage: Usage, served_by: str) -> GuardResult:
    """Read the guard's JSON, strictly. Every transport uses this, so they judge alike.

    Anything off the schema is `GuardUnavailable`: a guard that answers badly is not a guard that
    can be trusted to have passed the message.
    """

    def unusable(reason: str) -> GuardUnavailable:
        # The guard ran and was billed, so its usage goes with the failure.
        return GuardUnavailable(reason, usage=usage)

    try:
        data = json.loads(text)
    except ValueError:
        raise unusable("the guard's answer was not JSON") from None
    if not isinstance(data, dict) or set(data) != {"category", "kind", "injectionSuspected"}:
        raise unusable("the guard's answer did not have exactly its three fields")
    category, kind, injection = data["category"], data["kind"], data["injectionSuspected"]
    if category not in _CATEGORIES:
        raise unusable("the guard's category was not one it may give")
    if kind is not None and kind not in _KINDS:
        raise unusable("the guard's kind was not one it may give")
    if not isinstance(injection, bool):
        raise unusable("the guard's injectionSuspected was not true or false")
    return GuardResult(
        category=category,
        kind=kind,
        injection_suspected=injection,
        usage=usage,
        served_by=served_by,
    )


# --- The interface ----------------------------------------------------------------------------


class Transport(Protocol):
    def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        """Stream one assistant-model call as normalized events, ending with `Finished`."""
        ...

    async def classify(self, request: GuardRequest) -> GuardResult:
        """The guard's one call. Raises `GuardUnavailable` when it can't give a usable answer."""
        ...


# --- Search results ---------------------------------------------------------------------------


def iter_search_results(content: str | Iterable[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    """The `search_result` blocks in a message's content, in the order the API counts them.

    The search tool's results sit in a `tool_result` block's own `content` list, so looking only at
    the message's top-level blocks would find none. This is the one walk: counting, finding the
    first result, and the scripted model all use it. A message's content may also be a plain string,
    which holds no blocks and so no results.
    """
    if isinstance(content, str):
        return
    for block in content:
        if block.get("type") == "search_result":
            yield block
        elif block.get("type") == "tool_result" and isinstance(block.get("content"), list):
            yield from iter_search_results(block["content"])


def count_search_results(content: str | Iterable[dict[str, Any]]) -> int:
    """How many `search_result` blocks a message holds, including those inside its tool results."""
    return sum(1 for _ in iter_search_results(content))


# --- Startup ----------------------------------------------------------------------------------


def require_a_transport_fit_for(settings: Settings) -> None:
    """Refuse to start in production with a stand-in transport.

    The API calls this at startup, before it builds the transport. It is not a rule on `Settings`,
    because alembic, the setup scripts, and the cleanup job build `Settings` in production too and
    never call the model. Raises ValueError.
    """
    if settings.app_env == "production" and settings.ai_transport != "anthropic":
        raise ValueError(
            f"AI_TRANSPORT must be anthropic when APP_ENV=production, not {settings.ai_transport}:"
            " the scripted and replay transports are for development, tests, and evals"
        )
