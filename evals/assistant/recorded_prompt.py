"""Replay the assistant's recordings under the prompt they were made with.

Prompt 2026-11.5 shipped without a full eval run, so the committed recordings are an older
prompt's, and a replay of the current prompt would miss every request. A pin file in the fixtures
folder names that older prompt and holds a copy of its text, checked against its SHA-256. An
offline run then uses that text as the system prompt for the block, and nothing else changes.

This tests the plumbing and the graders on the old recordings. It does not test the new prompt.
The next full `FRESH=1 PRUNE=1` live run records the current prompt, and the pin must be deleted
in the same change: the pin still names the older version then, so nothing refuses it, and the
replay misses until it is deleted (the line printed above the misses names the pin).

Under the pin, the eval sandbox's turn and audit rows still record the current PROMPT_VERSION while
the older text is in use. That is harmless: offline runs write no board.
"""

import hashlib
import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

from app.ai.prompts.versions import PROMPT_VERSION

PIN_FILE = "recorded-under.json"


@dataclass(frozen=True)
class RecordedPrompt:
    prompt_version: str
    text: str


def recorded_prompt(fixtures_dir: Path) -> RecordedPrompt | None:
    """The pinned prompt, or None when the folder has no pin.

    Raises ValueError when the pin lacks a key, when the text's SHA-256 differs from the pin's, or
    when the pin names the current prompt (a pin left behind after the prompt version was set back,
    or rewritten to name the current version)."""
    pin_path = fixtures_dir / PIN_FILE
    if not pin_path.is_file():
        return None
    pin = json.loads(pin_path.read_text(encoding="utf-8"))
    for key in ("promptVersion", "file", "sha256"):
        if not isinstance(pin, dict) or key not in pin:
            msg = f"{pin_path} has no {key!r} key"
            raise ValueError(msg)
    version = pin["promptVersion"]
    if version == PROMPT_VERSION:
        msg = (
            f"{pin_path} pins prompt {version}, which is the current prompt."
            " A pin is for an older prompt: delete the pin."
        )
        raise ValueError(msg)
    text = (fixtures_dir / pin["file"]).read_text(encoding="utf-8")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if digest != pin["sha256"]:
        msg = f"{pin['file']} has SHA-256 {digest}, but {pin_path} pins {pin['sha256']}"
        raise ValueError(msg)
    return RecordedPrompt(prompt_version=version, text=text)


@contextmanager
def replaying_under_recorded_prompt(fixtures_dir: Path) -> Iterator[RecordedPrompt | None]:
    """For the block, `app.ai.turn.system_prompt` (its one caller is `model_request`) returns the
    pinned text. With no pin, nothing changes."""
    pinned = recorded_prompt(fixtures_dir)
    if pinned is None:
        yield None
        return
    print(
        f"Replaying under recorded prompt {pinned.prompt_version}"
        f" (current prompt {PROMPT_VERSION}); the pin in {fixtures_dir / PIN_FILE} is deleted"
        " after the next full FRESH=1 PRUNE=1 run."
    )
    with patch("app.ai.turn.system_prompt", lambda: pinned.text):
        yield pinned
