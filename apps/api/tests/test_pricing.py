"""Prices and costs: money is Decimal, and a reservation never undercounts the real cost."""

import json
import logging
from decimal import ROUND_CEILING, Decimal

import pytest

from app.ai import pricing
from app.ai.pricing import (
    PRICES,
    IterationUsage,
    Price,
    Usage,
    cost_usd,
    dearer_model,
    estimate_input_tokens,
    estimate_request_tokens,
    reservation_usd,
    total_usage,
    turn_call_cost,
)

OPUS = "claude-opus-5-5"
SONNET = "claude-sonnet-5-5"
HAIKU = "claude-haiku-5-5"
# The models a declined Opus 5.5 request falls back to.
OPUS_5 = "claude-opus-5"
OPUS_4_8 = "claude-opus-4-8"


def test_the_hand_worked_example_is_exact() -> None:
    # 10,000 x $4.00 + 2,000 x $0.20 + 500 x $20.00, per million tokens.
    usage = Usage(
        input_tokens=10_000, output_tokens=500, cache_read_tokens=2_000, cache_write_tokens=0
    )

    assert cost_usd(OPUS, usage) == Decimal("0.0504")


def test_cache_writes_are_priced_at_the_cache_write_rate() -> None:
    usage = Usage(input_tokens=0, output_tokens=0, cache_read_tokens=0, cache_write_tokens=100_000)

    assert cost_usd(OPUS, usage) == Decimal("0.50")
    assert cost_usd(SONNET, usage) == Decimal("0.25")
    assert cost_usd(HAIKU, usage) == Decimal("0.0125")


def test_a_fallbacks_attempts_are_each_priced_at_their_own_model() -> None:
    usage = Usage(
        input_tokens=1_000_000, output_tokens=100_000, cache_read_tokens=0, cache_write_tokens=0
    )

    cost = turn_call_cost([IterationUsage(OPUS, usage), IterationUsage(SONNET, usage)])

    # Opus: $4.00 + $2.00. Sonnet: $2.00 + $1.00.
    assert cost == Decimal("9.00")


def test_a_turn_with_no_attempts_costs_nothing() -> None:
    assert turn_call_cost([]) == Decimal(0)


def test_an_unknown_model_raises() -> None:
    usage = Usage(input_tokens=1, output_tokens=1, cache_read_tokens=0, cache_write_tokens=0)

    with pytest.raises(ValueError, match="claude-opus-9"):
        cost_usd("claude-opus-9", usage)
    with pytest.raises(ValueError, match="claude-opus-9"):
        reservation_usd("claude-opus-9", estimated_input_tokens=1, max_tokens=1)


def test_a_haiku_prompt_at_exactly_the_limit_is_priced_at_the_low_rate() -> None:
    usage = Usage(input_tokens=100_000, output_tokens=0, cache_read_tokens=0, cache_write_tokens=0)

    assert cost_usd(HAIKU, usage) == Decimal("0.01")
    assert reservation_usd(HAIKU, estimated_input_tokens=100_000, max_tokens=0) == Decimal("0.0125")


def test_a_haiku_prompt_over_the_limit_is_priced_at_the_high_tier() -> None:
    # The prompt is everything sent: plain input, cache reads, and cache writes. Over 100,000 of
    # them, the whole call is priced at $0.50 input, $0.625 cache write, $0.05 cache read, and
    # $2.50 output.
    usage = Usage(
        input_tokens=60_000,
        output_tokens=1_000,
        cache_read_tokens=30_000,
        cache_write_tokens=10_001,
    )

    # 60,000 x 0.50 + 10,001 x 0.625 + 30,000 x 0.05 + 1,000 x 2.50, per million.
    # $0.040250625 exactly, rounded to the ledgers' six places.
    assert cost_usd(HAIKU, usage) == Decimal("0.040251")
    # The reservation prices the input at the dearer cache-write rate: 100,001 x 0.625 + 10 x 2.50,
    # which is $0.062525625, rounded up to the ledgers' six places.
    assert reservation_usd(HAIKU, estimated_input_tokens=100_001, max_tokens=10) == Decimal(
        "0.062526"
    )


def test_a_long_haiku_prompt_never_stops_a_settle() -> None:
    usage = Usage(
        input_tokens=150_000, output_tokens=500, cache_read_tokens=0, cache_write_tokens=0
    )

    assert turn_call_cost([IterationUsage(HAIKU, usage)]) == cost_usd(HAIKU, usage)
    assert turn_call_cost([IterationUsage(HAIKU, usage)]) == Decimal("0.07625")


def test_the_reservation_is_the_input_at_the_dearest_rate_plus_the_full_output() -> None:
    # Opus: the cache-write rate ($5.00) is above the input rate ($4.00), so the input is
    # reserved at $5.00. 20,000 x $5.00 + 8,000 x $20.00, per million.
    assert reservation_usd(OPUS, estimated_input_tokens=20_000, max_tokens=8_000) == Decimal("0.26")


@pytest.mark.parametrize("model", sorted(PRICES))
@pytest.mark.parametrize(
    ("plain_share", "read_share", "write_share"),
    [(1, 0, 0), (0, 1, 0), (0, 0, 1), (1, 1, 1), (2, 1, 5), (0, 1, 1), (1, 0, 3)],
)
def test_the_reservation_never_undercounts_however_the_input_is_cached(
    model: str, plain_share: int, read_share: int, write_share: int
) -> None:
    estimated = 50_000
    max_tokens = 8_000
    total_shares = plain_share + read_share + write_share
    read = estimated * read_share // total_shares
    write = estimated * write_share // total_shares
    # The plain input takes the rounding, so the three parts add up to the estimate.
    usage = Usage(
        input_tokens=estimated - read - write,
        output_tokens=max_tokens,
        cache_read_tokens=read,
        cache_write_tokens=write,
    )

    reserved = reservation_usd(model, estimated_input_tokens=estimated, max_tokens=max_tokens)

    assert cost_usd(model, usage) <= reserved


def test_a_reservation_that_priced_input_at_the_plain_rate_would_undercount() -> None:
    # Guards the reason for the rule: all of the prompt written to the cache costs more than
    # all of it sent as plain input.
    price = PRICES[OPUS]
    assert price.cache_write_5m_usd_per_mtok > price.input_usd_per_mtok
    written = Usage(input_tokens=0, output_tokens=0, cache_read_tokens=0, cache_write_tokens=1000)
    plain_rate_reservation = reservation_usd(OPUS, estimated_input_tokens=1000, max_tokens=0)

    assert cost_usd(OPUS, written) == plain_rate_reservation
    assert plain_rate_reservation > Decimal(1000) * price.input_usd_per_mtok / 1_000_000


def previous_call(*, plain: int = 0, read: int = 0, write: int = 0, output: int = 0) -> Usage:
    return Usage(
        input_tokens=plain,
        output_tokens=output,
        cache_read_tokens=read,
        cache_write_tokens=write,
    )


@pytest.mark.parametrize(
    ("previous", "text", "expected"),
    [
        (None, "", 0),
        (None, "a", 1),
        (None, "ab", 1),
        (None, "abc", 2),
        (previous_call(plain=1_000), "abcd", 1_002),
        # Counted as two UTF-8 bytes a token, so text that costs more tokens per character
        # (accented letters, Japanese, emoji) is not undercounted.
        (previous_call(plain=1_000), "é" * 5, 1_005),
        (None, "日本語のテキスト", 12),
        (None, "🙂", 2),
    ],
)
def test_the_input_estimate_rounds_up_at_two_bytes_a_token(
    previous: Usage | None, text: str, expected: int
) -> None:
    assert estimate_input_tokens(previous, text) == expected


def test_a_mostly_cached_previous_call_still_counts_its_whole_prompt() -> None:
    # The plain input is about 50 tokens: the rest of the 30,000-token prompt was cached. Passing
    # only the plain figure would reserve for a sliver of the real prompt.
    previous = previous_call(plain=50, read=29_000, write=950)

    assert previous.prompt_tokens == 30_000
    assert estimate_input_tokens(previous, "next question") >= 30_000


@pytest.mark.parametrize("fallback_model", [OPUS_5, OPUS_4_8])
def test_an_opus_fallback_attempt_is_priced_at_the_fallback_rates(fallback_model: str) -> None:
    usage = Usage(
        input_tokens=100_000,
        output_tokens=10_000,
        cache_read_tokens=100_000,
        cache_write_tokens=100_000,
    )

    cost = turn_call_cost([IterationUsage(OPUS, usage), IterationUsage(fallback_model, usage)])

    # Opus 5.5: $0.40 + $0.50 + $0.02 + $0.20. The fallback: $0.50 + $0.625 + $0.05 + $0.25.
    assert cost_usd(fallback_model, usage) == Decimal("1.425")
    assert cost == Decimal("1.12") + Decimal("1.425")


def test_an_unknown_served_model_is_priced_at_the_dearest_row_and_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # The call was already billed, so settlement must not crash: it counts more, never less.
    usage = Usage(
        input_tokens=1_000, output_tokens=1_000, cache_read_tokens=1_000, cache_write_tokens=1_000
    )
    dearest = max(PRICES.values(), key=lambda price: price.output_usd_per_mtok)

    with caplog.at_level(logging.WARNING, logger="app.ai.pricing"):
        cost = turn_call_cost([IterationUsage("claude-opus-9-9", usage)])

    expected = (
        Decimal(1_000)
        * (
            dearest.input_usd_per_mtok
            + dearest.cache_write_5m_usd_per_mtok
            + dearest.cache_read_usd_per_mtok
            + dearest.output_usd_per_mtok
        )
        / 1_000_000
    )
    assert cost == expected
    assert cost >= max(cost_usd(model, usage) for model in PRICES)
    assert "claude-opus-9-9" in caplog.text


def test_the_requested_models_cost_and_reservation_still_refuse_an_unknown_model() -> None:
    usage = Usage(input_tokens=1, output_tokens=1, cache_read_tokens=0, cache_write_tokens=0)

    with pytest.raises(ValueError, match="claude-opus-9-9"):
        cost_usd("claude-opus-9-9", usage)
    with pytest.raises(ValueError, match="claude-opus-9-9"):
        reservation_usd("claude-opus-9-9", estimated_input_tokens=1, max_tokens=1)


def test_total_usage_adds_up_every_attempt_declined_ones_included() -> None:
    declined = Usage(input_tokens=100, output_tokens=0, cache_read_tokens=20, cache_write_tokens=30)
    served = Usage(input_tokens=1, output_tokens=2, cache_read_tokens=3, cache_write_tokens=4)

    total = total_usage([IterationUsage(OPUS, declined), IterationUsage(OPUS_5, served)])

    assert total == Usage(
        input_tokens=101, output_tokens=2, cache_read_tokens=23, cache_write_tokens=34
    )
    assert total_usage([]) == Usage(0, 0, 0, 0)


def test_the_previous_calls_output_counts_because_it_is_sent_back_as_input() -> None:
    # The assistant's last message (its thinking and tool calls included) is part of the next
    # prompt, so a call that wrote 6,000 tokens adds 6,000 to the next one's input.
    previous = previous_call(plain=500, read=1_000, write=500, output=6_000)

    assert previous.prompt_tokens == 2_000
    assert estimate_input_tokens(previous, "") == 8_000
    assert estimate_input_tokens(previous, "next question") >= 8_000 + len("next question") // 2


def test_the_first_calls_estimate_covers_the_whole_serialized_request() -> None:
    # With no previous call, the only figure to go on is the request itself: the system prompt and
    # the tools are most of it. Counting just the question would reserve for a sliver.
    question = "How does sick leave work in California?"
    request = {
        "system": [
            {
                "type": "text",
                "text": "人事のアシスタントです。Café … naïve résumé. " * 200,
            }
        ],
        "tools": [
            {
                "name": "search_handbook",
                "description": "Search the handbook for passages. " * 20,
                "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
            }
        ],
        "messages": [{"role": "user", "content": [{"type": "text", "text": question}]}],
    }
    request_text = json.dumps(request, ensure_ascii=False)

    estimate = estimate_request_tokens(request_text)

    assert estimate == -(-len(request_text.encode("utf-8")) // 2)
    assert estimate > 100 * estimate_request_tokens(question)
    # It is the same rule as the next-call estimate with nothing before it.
    assert estimate_input_tokens(None, request_text) == estimate


LEDGER_PLACES = Decimal("0.000001")


@pytest.mark.parametrize(
    ("estimated_input_tokens", "max_tokens"), [(1, 1), (3, 7), (12_345, 8_000), (99_999, 1)]
)
@pytest.mark.parametrize("model", [HAIKU, SONNET, OPUS])
def test_a_reservation_fits_the_ledgers_six_places_and_rounds_up(
    model: str, estimated_input_tokens: int, max_tokens: int
) -> None:
    price = PRICES[model]
    input_rate = max(price.input_usd_per_mtok, price.cache_write_5m_usd_per_mtok)
    unrounded = (
        Decimal(estimated_input_tokens) * input_rate
        + Decimal(max_tokens) * price.output_usd_per_mtok
    ) / 1_000_000

    reserved = reservation_usd(
        model, estimated_input_tokens=estimated_input_tokens, max_tokens=max_tokens
    )

    assert reserved == reserved.quantize(LEDGER_PLACES)
    assert reserved >= unrounded
    assert reserved == unrounded.quantize(LEDGER_PLACES, rounding=ROUND_CEILING)


def test_a_reservation_of_a_fraction_of_a_micro_dollar_rounds_up_to_one() -> None:
    # 1 x $0.125 + 1 x $0.50 per million is $0.000000625.
    assert reservation_usd(HAIKU, estimated_input_tokens=1, max_tokens=1) == Decimal("0.000001")


def test_a_cost_is_rounded_half_to_even_at_six_places() -> None:
    def haiku_input(tokens: int) -> Decimal:
        usage = Usage(
            input_tokens=tokens, output_tokens=0, cache_read_tokens=0, cache_write_tokens=0
        )
        return cost_usd(HAIKU, usage)

    # 5 tokens at $0.10 per million is exactly half a micro-dollar: it goes to the even 0.
    assert haiku_input(5) == Decimal("0")
    # 15 tokens is one and a half: it goes to the even 2.
    assert haiku_input(15) == Decimal("0.000002")
    assert haiku_input(15) == haiku_input(15).quantize(LEDGER_PLACES)
    assert turn_call_cost(
        [
            IterationUsage(
                HAIKU,
                Usage(input_tokens=15, output_tokens=0, cache_read_tokens=0, cache_write_tokens=0),
            )
        ]
    ) == Decimal("0.000002")


def test_the_fallback_price_takes_the_dearest_of_each_rate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The dearest input and the dearest output are on different rows. Picking one row by its output
    # rate would undercount the input of a model that is dear on input.
    dear_input = Price(
        input_usd_per_mtok=Decimal(900),
        cache_write_5m_usd_per_mtok=Decimal(10),
        cache_read_usd_per_mtok=Decimal(10),
        output_usd_per_mtok=Decimal(100),
    )
    dear_output = Price(
        input_usd_per_mtok=Decimal(100),
        cache_write_5m_usd_per_mtok=Decimal(800),
        cache_read_usd_per_mtok=Decimal(700),
        output_usd_per_mtok=Decimal(1000),
    )
    monkeypatch.setattr(pricing, "PRICES", {"a": dear_input, "b": dear_output})
    usage = Usage(
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        cache_read_tokens=1_000_000,
        cache_write_tokens=1_000_000,
    )

    cost = turn_call_cost([IterationUsage("never-heard-of-it", usage)])

    # $900 input + $800 cache write + $700 cache read + $1,000 output.
    assert cost == Decimal(3400)


def test_the_dearer_model_is_the_one_with_the_higher_output_rate_in_either_order() -> None:
    assert dearer_model(OPUS, SONNET) == OPUS
    assert dearer_model(SONNET, OPUS) == OPUS
    assert dearer_model(SONNET, HAIKU) == SONNET
    assert dearer_model(HAIKU, SONNET) == SONNET


def test_models_priced_alike_give_the_first() -> None:
    assert PRICES[OPUS_4_8] == PRICES[OPUS_5]
    assert dearer_model(OPUS_4_8, OPUS_5) == OPUS_4_8
    assert dearer_model(OPUS_5, OPUS_4_8) == OPUS_5


def test_a_model_with_no_pinned_price_is_the_dearer_as_it_is_when_settling() -> None:
    assert dearer_model(OPUS, "claude-future-9") == "claude-future-9"
    assert dearer_model("claude-future-9", OPUS) == "claude-future-9"


def test_a_pinned_name_is_priced_and_a_dated_snapshot_is_not() -> None:
    from app.ai.pricing import is_priced

    assert is_priced("claude-haiku-5-5")
    assert is_priced("scripted")
    assert not is_priced("claude-haiku-5-5-20261001")
