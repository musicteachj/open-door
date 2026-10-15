"""What a model call costs, at list price, in dollars.

Prices are per million tokens and pinned here, per model, because the budget caps are about money
and the models' prices differ by twentyfold (ADR 0011). Money is `Decimal`, never `float`.

Source: Anthropic, "Pricing", platform.claude.com/docs/en/about-claude/pricing, read on 2026-10-14.
The Opus 5.5, Sonnet 5.5, and Haiku 5.5 rows were read again that day and match.

This module defines its own small usage types and imports no SDK. The transport
(app/ai/transport.py) converts the SDK's usage into these.
"""

import logging
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_HALF_EVEN, Decimal
from types import MappingProxyType

logger = logging.getLogger(__name__)

TOKENS_PER_MTOK = Decimal(1_000_000)
# Both ledgers are numeric(12, 6). Amounts have exactly these places, so what a reservation and its
# settle add up to in the database is exactly the cost, with no rounding left to the database.
LEDGER_PLACES = Decimal("0.000001")

# Haiku 5.5 costs more above this many prompt tokens (input, cache reads, and cache writes). The
# guard's prompts are tiny, so crossing it means something is wrong, but the call has been billed
# by then, so it is priced at the higher tier, never refused.
HAIKU_PROMPT_LIMIT_TOKENS = 100_000
HAIKU = "claude-haiku-5-5"
# The scripted stand-in for Claude (ADR 0010), which makes no paid call.
SCRIPTED_MODEL = "scripted"
OPUS_5 = "claude-opus-5"
OPUS_4_8 = "claude-opus-4-8"


@dataclass(frozen=True)
class Price:
    """Dollars per million tokens."""

    input_usd_per_mtok: Decimal
    cache_write_5m_usd_per_mtok: Decimal
    cache_read_usd_per_mtok: Decimal
    output_usd_per_mtok: Decimal


# Claude Haiku 5.5 "for prompts over 100,000 tokens". Source: the pricing page named above, read on
# 2026-10-14.
HAIKU_LONG_PROMPT_PRICE = Price(
    input_usd_per_mtok=Decimal("0.50"),
    cache_write_5m_usd_per_mtok=Decimal("0.625"),
    cache_read_usd_per_mtok=Decimal("0.05"),
    output_usd_per_mtok=Decimal("2.50"),
)

_OPUS_5_PRICE = Price(
    input_usd_per_mtok=Decimal("5.00"),
    cache_write_5m_usd_per_mtok=Decimal("6.25"),
    cache_read_usd_per_mtok=Decimal("0.50"),
    output_usd_per_mtok=Decimal("25.00"),
)

PRICES: Mapping[str, Price] = MappingProxyType(
    {
        "claude-opus-5-5": Price(
            input_usd_per_mtok=Decimal("4.00"),
            cache_write_5m_usd_per_mtok=Decimal("5.00"),
            cache_read_usd_per_mtok=Decimal("0.20"),
            output_usd_per_mtok=Decimal("20.00"),
        ),
        "claude-sonnet-5-5": Price(
            input_usd_per_mtok=Decimal("2.00"),
            cache_write_5m_usd_per_mtok=Decimal("2.50"),
            # $0.10 per the pricing page read on 2026-10-14; the claude-api skill's cached table
            # says $0.20, which is out of date.
            cache_read_usd_per_mtok=Decimal("0.10"),
            output_usd_per_mtok=Decimal("10.00"),
        ),
        # Prompts up to 100,000 tokens; HAIKU_LONG_PROMPT_PRICE covers the rest.
        HAIKU: Price(
            input_usd_per_mtok=Decimal("0.10"),
            cache_write_5m_usd_per_mtok=Decimal("0.125"),
            cache_read_usd_per_mtok=Decimal("0.01"),
            output_usd_per_mtok=Decimal("0.50"),
        ),
        # The fallback targets when Opus 5.5 declines a request (`fallbacks: "default"`). They are
        # priced alike, and a declined attempt is billed, so settle must know the price.
        OPUS_5: _OPUS_5_PRICE,
        OPUS_4_8: _OPUS_5_PRICE,
        # The spec prices the scripted model at $0, so the budget is tested with configured caps.
        # A reservation still uses the request's real model, so it reserves real money and settles
        # back to nothing.
        SCRIPTED_MODEL: Price(
            input_usd_per_mtok=Decimal(0),
            cache_write_5m_usd_per_mtok=Decimal(0),
            cache_read_usd_per_mtok=Decimal(0),
            output_usd_per_mtok=Decimal(0),
        ),
    }
)


@dataclass(frozen=True)
class Usage:
    """Tokens one model call used. `input_tokens` is the plain input: it does not include the
    tokens read from or written to the cache, which the API reports separately."""

    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int

    @property
    def prompt_tokens(self) -> int:
        return self.input_tokens + self.cache_read_tokens + self.cache_write_tokens


@dataclass(frozen=True)
class IterationUsage:
    """One attempt in a fallback chain: the model that served it and what it used."""

    model: str
    usage: Usage


def price_of(model: str, prompt_tokens: int = 0) -> Price:
    """The pinned price of a model for a prompt of this many tokens. Raises for an unknown model."""
    try:
        price = PRICES[model]
    except KeyError:
        raise ValueError(f"no price is pinned for the model {model!r}") from None
    if model == HAIKU and prompt_tokens > HAIKU_PROMPT_LIMIT_TOKENS:
        return HAIKU_LONG_PROMPT_PRICE
    return price


def cost_usd(model: str, usage: Usage) -> Decimal:
    """The cost of one model's usage, exactly. Raises for a model with no pinned price."""
    return _cost_at(price_of(model, usage.prompt_tokens), usage)


def _cost_at(price: Price, usage: Usage) -> Decimal:
    """The cost to the ledgers' six places, rounding a half to the even digit."""
    exact = (
        Decimal(usage.input_tokens) * price.input_usd_per_mtok
        + Decimal(usage.cache_write_tokens) * price.cache_write_5m_usd_per_mtok
        + Decimal(usage.cache_read_tokens) * price.cache_read_usd_per_mtok
        + Decimal(usage.output_tokens) * price.output_usd_per_mtok
    ) / TOKENS_PER_MTOK
    return exact.quantize(LEDGER_PLACES, rounding=ROUND_HALF_EVEN)


def turn_call_cost(iterations: Sequence[IterationUsage]) -> Decimal:
    """The cost of a call that may have fallen back: each attempt at its own model's price.

    The call has been billed by the time this runs, so a served model with no pinned price must
    not stop the settle. It is priced at the dearest row instead, which counts more, never less,
    and a warning names it so the table gets updated.
    """
    total = Decimal(0)
    for item in iterations:
        if item.model in PRICES:
            total += cost_usd(item.model, item.usage)
        else:
            logger.warning(
                "No price is pinned for the served model %s; counting it at the dearest price",
                item.model,
            )
            total += _cost_at(_dearest_price(), item.usage)
    return total


def dearer_model(first: str, second: str) -> str:
    """Whichever of two models costs more, for pricing a doubtful attempt without undercounting it.

    Compared by output rate, then input rate (output dominates what a call costs); a tie gives the
    first. A model with no pinned price counts as the dearer, as it does when settling
    (`turn_call_cost` prices it at the dearest row). No single row need be dearest on all four
    rates, so this picks one model by its most expensive rates and cannot be exact on every field.
    """
    if second not in PRICES:
        return second
    if first not in PRICES:
        return first

    def rank(model: str) -> tuple[Decimal, Decimal]:
        price = PRICES[model]
        return (price.output_usd_per_mtok, price.input_usd_per_mtok)

    return second if rank(second) > rank(first) else first


def _dearest_price() -> Price:
    """The highest of each rate across every pinned price, so an unknown model is never undercounted
    on any of them, even if no single row is the dearest on all four."""
    prices = (*PRICES.values(), HAIKU_LONG_PROMPT_PRICE)
    return Price(
        input_usd_per_mtok=max(price.input_usd_per_mtok for price in prices),
        cache_write_5m_usd_per_mtok=max(price.cache_write_5m_usd_per_mtok for price in prices),
        cache_read_usd_per_mtok=max(price.cache_read_usd_per_mtok for price in prices),
        output_usd_per_mtok=max(price.output_usd_per_mtok for price in prices),
    )


def total_usage(iterations: Sequence[IterationUsage]) -> Usage:
    """Every attempt's tokens added up: what the call used in all, declined attempts included.

    A response's own top-level usage covers only the attempt that produced the message, so the
    iterations are the source of truth for what a turn spent.
    """
    return Usage(
        input_tokens=sum(item.usage.input_tokens for item in iterations),
        output_tokens=sum(item.usage.output_tokens for item in iterations),
        cache_read_tokens=sum(item.usage.cache_read_tokens for item in iterations),
        cache_write_tokens=sum(item.usage.cache_write_tokens for item in iterations),
    )


def reservation_usd(model: str, *, estimated_input_tokens: int, max_tokens: int) -> Decimal:
    """The most a call could cost, reserved before it is made.

    The input is priced at the dearer of the plain and the cache-write rate. Writing the prompt to
    the cache costs more than sending it as plain input ($5.00 against $4.00 a million on Opus), so
    a prompt that is written to the cache entirely would cost more than the plain rate reserved.
    A cache read is cheaper than either, so this bounds every split of the same input. The output
    is priced in full at `max_tokens`. The result is rounded up to the ledgers' six places.
    """
    price = price_of(model, estimated_input_tokens)
    input_rate = max(price.input_usd_per_mtok, price.cache_write_5m_usd_per_mtok)
    exact = (
        Decimal(estimated_input_tokens) * input_rate
        + Decimal(max_tokens) * price.output_usd_per_mtok
    ) / TOKENS_PER_MTOK
    # Rounded up, so that fitting the ledgers' six places never makes it undercount.
    return exact.quantize(LEDGER_PLACES, rounding=ROUND_CEILING)


def estimate_request_tokens(request_text: str) -> int:
    """The tokens in a request's text, at two UTF-8 bytes a token.

    For the first call of a conversation, where there is no earlier call to measure: pass the
    whole request serialized, meaning its `system`, `tools`, and `messages`, because the system
    prompt and the tool list are most of it. English runs at about four bytes a token, so two
    doesn't undercount it, and text that costs more tokens per character (CJK, emoji) is counted
    by its bytes, which is closer. It is an estimate: the reservation is a ceiling for the call,
    and settle brings the ledger to the real cost whatever the difference.
    """
    return math.ceil(len(request_text.encode("utf-8")) / 2)


def estimate_input_tokens(previous: Usage | None, new_text: str) -> int:
    """What the next call's prompt will hold: the previous call's prompt and output, plus the new
    text (`estimate_request_tokens`).

    The previous prompt is its plain input, cache reads, and cache writes together
    (`Usage.prompt_tokens`): the plain input alone leaves out whatever was cached. Its output
    counts too, because the assistant's last message (thinking and tool calls included) is sent
    back as input. With a previous call, `new_text` is only what was added since: the new user
    message and its tool results.

    With no previous call in the conversation, nothing measured covers the system prompt and the
    tools, so `new_text` must be the whole request's text: the serialized `system`, `tools`, and
    `messages`. Prefer `estimate_request_tokens` for that case.
    """
    previous_tokens = 0 if previous is None else previous.prompt_tokens + previous.output_tokens
    return previous_tokens + estimate_request_tokens(new_text)
