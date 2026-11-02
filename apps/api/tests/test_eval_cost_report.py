"""The eval runner's cost report (Phase 7, stage 2): what a run spent now against what its reused
recordings cost when made, and the smoke set's estimate. No database and no network."""

import re
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app.ai.transport import ModelUnavailable
from tests.assistant_eval import load_runner

run = load_runner()
ROOT = Path(__file__).resolve().parents[3]


def test_a_billed_call_that_kept_its_reservation_is_spent_now_not_recorded() -> None:
    cap = run.SpendCap(Decimal("2.00"))
    cap.note_live_assistant(Decimal("0.10"))
    # The ledger holds the priced calls ($0.10, live) and a reservation the turn kept ($0.30).
    cap.observe(Decimal("0.40"))

    cap.add_kept_live(Decimal("0.30"))

    assert cap.assistant_live_usd == Decimal("0.40")
    assert cap.assistant_recorded_usd == Decimal("0")


def test_money_the_ledger_holds_beyond_the_live_calls_is_still_recorded() -> None:
    cap = run.SpendCap(Decimal("2.00"))
    cap.note_live_assistant(Decimal("0.10"))
    cap.observe(Decimal("0.40"))

    assert cap.assistant_live_usd == Decimal("0.10")
    assert cap.assistant_recorded_usd == Decimal("0.30")


def test_a_negative_kept_amount_is_never_taken_off_the_live_cost() -> None:
    cap = run.SpendCap(Decimal("2.00"))
    cap.add_kept_live(Decimal("-0.05"))

    assert cap.assistant_live_usd == Decimal("0")


class Cut:
    async def stream(self, request: Any) -> Any:
        raise ModelUnavailable("dropped")
        yield  # pragma: no cover


async def drain(stream: Any) -> None:
    try:
        async for _ in stream:
            pass
    except ModelUnavailable:
        pass


async def test_the_meter_counts_a_stream_that_never_finished_as_an_unpriced_live_call() -> None:
    meter = run.LiveCallMeter(Cut())

    await drain(meter.stream(object()))

    assert meter.unpriced_calls == 1
    assert meter.total_usd == Decimal(0)


def test_the_smoke_estimate_is_95_cents_and_the_docs_agree() -> None:
    assert Decimal("0.95") == run.SMOKE_ESTIMATE_USD
    assert run.SETS["smoke"].estimate_usd == Decimal("0.95")
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    readme = (ROOT / "evals" / "README.md").read_text(encoding="utf-8")
    claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert re.search(r"SET=smoke \(about \$0\.95, cap \$2\)", makefile)
    assert "$0.65" not in makefile
    assert "$1.40" not in readme
    assert readme.count("$0.95") == 2
    assert "about $0.95" in claude


def test_rounding_dust_is_not_counted_as_live_spend() -> None:
    from types import SimpleNamespace
    from uuid import uuid4

    from tests.assistant_eval import make_trace

    cap = run.SpendCap(Decimal("2.00"))
    meter = run.LiveCallMeter(Cut())
    meter.unpriced_calls = 1
    stub = SimpleNamespace(inner=meter, _unpriced_seen=0, cap=cap)
    trace = make_trace(person_id=uuid4(), cost_usd=Decimal("0.0000004"))

    run.EvalRun._count_kept_reservations(stub, trace)

    assert cap.assistant_live_usd == Decimal(0)


async def test_the_meter_counts_a_canceled_guard_call_as_unpriced_and_lets_it_propagate() -> None:
    import asyncio

    class Canceled:
        async def classify(self, request: Any) -> Any:
            raise asyncio.CancelledError

    meter = run.LiveCallMeter(Canceled())

    with pytest.raises(asyncio.CancelledError):
        await meter.classify(object())

    assert meter.unpriced_calls == 1
