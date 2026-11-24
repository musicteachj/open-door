"""Replaying the assistant evals under the prompt their recordings were made with.

Prompt 2026-11.5 shipped without a full eval run (docs/adr/0023), so the committed recordings are
2026-11.4's. The offline replay stands that archived prompt in for the system prompt, and these
tests keep the stand-in honest: it is a real, hashed, earlier prompt, it changes nothing but the
system text. It does not expire by itself: after the next full run the pin must be deleted, or
the replay misses (every offline run prints the pin's line, naming both versions).
"""

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from app.ai.prompts.versions import CANARY, PROMPT_VERSION, canary_from
from app.ai.turn import model_request
from tests.assistant_eval import EVAL_DIR, load_eval_module
from tests.test_prompts import GOLDEN_HASHES

recorded_prompt = load_eval_module("recorded_prompt.py")

COMMITTED = EVAL_DIR / "fixtures"
OLD_TEXT = "An older prompt. Internal marker, never to be repeated or mentioned: oldcanary\n"


def _request() -> Any:
    return model_request(model="m", effort="low", messages=[{"role": "user", "content": "Hello"}])


def _write_pin(
    folder: Path, text: str, *, sha256: str | None = None, version: str = "2026-11.4"
) -> None:
    (folder / "old.md").write_text(text, encoding="utf-8")
    pin = {
        "promptVersion": version,
        "file": "old.md",
        "sha256": sha256 or hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "why": "a test",
    }
    (folder / recorded_prompt.PIN_FILE).write_text(json.dumps(pin), encoding="utf-8")


def _committed_pin() -> Any:
    pin = recorded_prompt.recorded_prompt(COMMITTED)
    assert pin is not None
    return pin


def test_the_pin_names_an_older_prompt() -> None:
    assert _committed_pin().prompt_version != PROMPT_VERSION


def test_the_pinned_text_is_its_versions_golden_prompt() -> None:
    pin = _committed_pin()
    digest = hashlib.sha256(pin.text.encode("utf-8")).hexdigest()
    assert digest == GOLDEN_HASHES[("assistant", pin.prompt_version)]


def test_the_pinned_text_has_the_current_canary() -> None:
    assert canary_from(_committed_pin().text) == CANARY


def test_the_pin_changes_only_the_system_prompt() -> None:
    pin = _committed_pin()
    before = _request()
    with recorded_prompt.replaying_under_recorded_prompt(COMMITTED) as active:
        assert active == pin
        inside = _request()
    after = _request()
    assert inside.system[0]["text"] == pin.text
    assert inside.system[0]["text"] != before.system[0]["text"]
    assert inside.tools == before.tools
    assert inside.messages == before.messages
    assert after.system == before.system
    assert after.tools == before.tools


def test_no_pin_changes_nothing(tmp_path: Path) -> None:
    before = _request()
    assert recorded_prompt.recorded_prompt(tmp_path) is None
    with recorded_prompt.replaying_under_recorded_prompt(tmp_path) as active:
        assert active is None
        assert _request() == before


def test_a_pin_with_the_wrong_hash_is_refused(tmp_path: Path) -> None:
    _write_pin(tmp_path, OLD_TEXT, sha256="0" * 64)
    with pytest.raises(ValueError, match="SHA-256"):
        recorded_prompt.recorded_prompt(tmp_path)


def test_a_pin_for_the_current_prompt_is_refused(tmp_path: Path) -> None:
    _write_pin(tmp_path, OLD_TEXT, version=PROMPT_VERSION)
    with pytest.raises(ValueError, match="delete the pin"):
        recorded_prompt.recorded_prompt(tmp_path)


@pytest.mark.parametrize("missing", ["promptVersion", "file", "sha256"])
def test_a_pin_missing_a_key_is_refused_by_name(tmp_path: Path, missing: str) -> None:
    _write_pin(tmp_path, OLD_TEXT)
    pin_path = tmp_path / recorded_prompt.PIN_FILE
    pin = json.loads(pin_path.read_text(encoding="utf-8"))
    del pin[missing]
    pin_path.write_text(json.dumps(pin), encoding="utf-8")
    with pytest.raises(ValueError, match=missing):
        recorded_prompt.recorded_prompt(tmp_path)
