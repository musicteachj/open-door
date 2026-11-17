"""The live check through the production image (Phase 8, Task 46): how
`scripts/prod-local/live_check.py` judges what the run left in its database. No Docker, no model."""

import contextlib
import importlib.util
import json
import subprocess
import sys
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "prod-local" / "live_check.py"
sys.path.insert(0, str(REPO / "scripts" / "image"))
sys.path.insert(0, str(REPO / "scripts" / "prod-local"))


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("prod_local_live_check_script", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


live = load_script()


def row(**overrides: object) -> object:
    values: dict[str, object] = {
        "status": "completed",
        "input_tokens": 3100,
        "output_tokens": 240,
        "cache_read_tokens": 2900,
        "cost_usd": Decimal("0.031"),
        "served_by": ["claude-opus-5-5"],
    }
    values.update(overrides)
    return live.TurnRow(**values)


def test_two_good_turns_pass() -> None:
    assert live.problems([row(), row()], plaintext_rows=0, sealed_turns=2, dry_run=False) == []


def test_it_needs_both_questions_answered() -> None:
    found = live.problems([row()], plaintext_rows=0, sealed_turns=1, dry_run=False)

    assert any("2 completed turns" in p for p in found)


@pytest.mark.parametrize(
    ("field", "value", "said"),
    [
        ("input_tokens", 0, "input tokens"),
        ("output_tokens", 0, "output tokens"),
        ("cache_read_tokens", 0, "cache reads"),
        ("cost_usd", Decimal(0), "cost"),
        ("served_by", [], "served_by"),
    ],
)
def test_each_figure_must_be_recorded(field: str, value: object, said: str) -> None:
    found = live.problems(
        [row(), row(**{field: value})], plaintext_rows=0, sealed_turns=2, dry_run=False
    )

    assert any(said in p for p in found), found


def test_a_dry_run_has_no_cost_and_no_cache_and_that_is_fine() -> None:
    # The scripted model is priced at $0 and has no prompt cache.
    scripted = row(cost_usd=Decimal(0), cache_read_tokens=0, served_by=["scripted"])

    assert live.problems([scripted, scripted], plaintext_rows=0, sealed_turns=2, dry_run=True) == []


def test_the_real_run_must_be_served_by_a_real_model() -> None:
    found = live.problems(
        [row(), row(served_by=["scripted"])], plaintext_rows=0, sealed_turns=2, dry_run=False
    )

    assert any("served_by" in p for p in found)


def test_a_question_found_in_plain_text_fails() -> None:
    found = live.problems([row(), row()], plaintext_rows=1, sealed_turns=2, dry_run=False)

    assert any("plain text" in p for p in found)


def test_every_turn_must_have_its_question_sealed() -> None:
    found = live.problems([row(), row()], plaintext_rows=0, sealed_turns=1, dry_run=False)

    assert any("encrypted" in p for p in found)


def test_the_plaintext_query_looks_in_every_conversation_table() -> None:
    sql = live.plaintext_sql()

    for table in ("ai_turns", "ai_messages", "ai_console_turns"):
        assert table in sql
    for phrase in live.PHRASES:
        assert phrase.lower() in sql.lower()


def test_every_phrase_searched_for_is_one_the_browser_pass_sends() -> None:
    """A phrase the browser never typed can't be found, so the plaintext check would pass empty."""
    sent = (REPO / "apps" / "web" / "e2e" / "live" / "check.ts").read_text(encoding="utf-8")

    for phrase in live.PHRASES:
        assert f"'{phrase}" in sent, phrase


def test_an_earlier_runs_browser_report_never_stands_in_for_this_ones(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The browser fails before writing its report, so this run's report has none."""
    (tmp_path / "browser.json").write_text('{"violations": []}')

    @contextlib.contextmanager
    def running(*args: object, **kwargs: object) -> Iterator[str]:
        yield "http://localhost:8300"

    monkeypatch.setattr(live.start, "read_secrets", lambda: None)
    monkeypatch.setattr(live.start, "running", running)
    monkeypatch.setattr(live.start, "query", lambda sql: "" if sql == live.TURNS_SQL else "0")
    monkeypatch.setattr(live.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 1))

    assert live.run(dry_run=True, port=8300, out=tmp_path) == 1

    report = json.loads((tmp_path / "live-check.json").read_text())
    assert report["browser"] is None
    assert "the browser part failed (see its output above)" in report["problems"]


def test_the_turn_query_parses_the_psql_output() -> None:
    line = "completed|3100|240|2900|0.031000|{claude-opus-5-5,claude-haiku-4-5}"

    parsed = live.parse_turn(line)

    assert parsed.cost_usd == Decimal("0.031")
    assert parsed.served_by == ["claude-opus-5-5", "claude-haiku-4-5"]
    assert live.parse_turn("failed|0|0|0|0|{}").served_by == []


def test_the_check_has_no_em_dash() -> None:
    assert "\u2014" not in SCRIPT.read_text(encoding="utf-8")
