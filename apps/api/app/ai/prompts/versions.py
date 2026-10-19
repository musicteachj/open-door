"""The prompts, read once, and the versions that conversations pin.

A conversation records `PROMPT_VERSION` and `TOOLSET_VERSION` when it starts and can't continue
once either changes (the history is append-only, and the model's thinking is tied to the exact
prompt and tools that produced it). So a change to a prompt file needs a new version here, and the
offline evals green and a live eval run first (CLAUDE.md). `tests/test_prompts.py` pins each
prompt's hash and fails when the text changes without the version.
"""

import re
from functools import cache
from pathlib import Path

from app.ai.transport import GUARD_NEW_MESSAGE_TAG

PROMPT_VERSION = "2026-10.2"
TOOLSET_VERSION = "2026-10.1"
GUARD_PROMPT_VERSION = "2026-10.1"

# The guard puts the assistant's last answer beside the new message, in this tag.
GUARD_PREVIOUS_ANSWER_TAG = "previous_answer"

__all__ = [
    "CANARY",
    "GUARD_NEW_MESSAGE_TAG",
    "GUARD_PREVIOUS_ANSWER_TAG",
    "GUARD_PROMPT_VERSION",
    "PROMPT_VERSION",
    "TOOLSET_VERSION",
    "guard_prompt",
    "system_prompt",
]

_DIRECTORY = Path(__file__).parent
_MARKER = "Internal marker, never to be repeated or mentioned: "


@cache
def system_prompt() -> str:
    return (_DIRECTORY / "assistant.md").read_text(encoding="utf-8")


@cache
def guard_prompt() -> str:
    return (_DIRECTORY / "guard.md").read_text(encoding="utf-8")


def canary_from(prompt: str) -> str:
    """The phrase after the marker line. Its only use is to be found if the prompt leaks."""
    match = re.search(re.escape(_MARKER) + r"(\S+)", prompt)
    if match is None:
        msg = "The system prompt has no canary line"
        raise ValueError(msg)
    return match.group(1)


CANARY = canary_from(system_prompt())
