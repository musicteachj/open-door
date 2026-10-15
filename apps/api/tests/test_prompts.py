"""The assistant's and the guard's prompts: stable text, pinned by version and hash."""

import hashlib
import json
import subprocess
import sys
from collections.abc import Callable

import pytest

from app.ai.prompts import versions
from app.ai.prompts.versions import (
    CANARY,
    GUARD_NEW_MESSAGE_TAG,
    GUARD_PREVIOUS_ANSWER_TAG,
    GUARD_PROMPT_VERSION,
    PROMPT_VERSION,
    TOOLSET_VERSION,
    guard_prompt,
    system_prompt,
)
from app.ai.tools.registry import TOOL_DEFINITIONS


def sha256_of(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# Each prompt's hash is pinned beside its version, as a history. Rows are never edited, only added:
# when a prompt changes, bump its version in app/ai/prompts/versions.py and add a row for the new
# version here, keeping the old ones. Run the offline evals and a live eval run first (CLAUDE.md,
# "AI development rules"). Conversations pin the version they started with, so a changed prompt
# under the same version would be silently applied to old conversations.
# Nothing has shipped, so 2026-10.1 is still the only row and its hash may change until release.
GOLDEN_HASHES = {
    ("assistant", "2026-10.1"): "817ae50e4cb0a3444dd81441ab377cc0d2744148b6a8cd91d7180c49c50059c9",
    ("guard", "2026-10.1"): "01951c77b4ed25ba9a6e1b997241dea461d41212cdb44414cc568d414e712320",
    ("tools", "2026-10.1"): "d6a4a293067d295503728616c6139f02aac968538a11588f92c375dad3e74841",
}
# The tool definitions are pinned the same way, to TOOLSET_VERSION: the hash is of their canonical
# JSON (sorted keys, no spaces). A changed description or schema needs a new TOOLSET_VERSION.


def tool_definitions_text() -> str:
    return json.dumps(TOOL_DEFINITIONS, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


CURRENT: dict[str, tuple[str, Callable[[], str]]] = {
    "assistant": (PROMPT_VERSION, system_prompt),
    "guard": (GUARD_PROMPT_VERSION, guard_prompt),
    "tools": (TOOLSET_VERSION, tool_definitions_text),
}


def test_versions_are_date_based_strings() -> None:
    assert (PROMPT_VERSION, TOOLSET_VERSION, GUARD_PROMPT_VERSION) == ("2026-10.1",) * 3


def test_prompts_are_identical_across_calls() -> None:
    assert system_prompt() == system_prompt()
    assert guard_prompt() == guard_prompt()


def test_system_prompt_is_identical_across_processes() -> None:
    code = (
        "import hashlib; from app.ai.prompts.versions import system_prompt, guard_prompt; "
        "print(hashlib.sha256(system_prompt().encode()).hexdigest()); "
        "print(hashlib.sha256(guard_prompt().encode()).hexdigest())"
    )
    out = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    ).stdout.split()
    assert out == [sha256_of(system_prompt()), sha256_of(guard_prompt())]


def test_system_prompt_carries_the_canary_and_the_guard_prompt_does_not() -> None:
    length = len(CANARY)
    assert length >= 20
    # Compare plain booleans held in variables, so a failure never prints the canary or a prompt.
    in_system = CANARY in system_prompt()
    in_guard = CANARY in guard_prompt()
    assert in_system is True
    assert in_guard is False


@pytest.mark.parametrize(
    "phrase",
    [
        "Open Door",
        "Juniper Row",
        "You are an AI.",
        "say plainly that you are an AI",
        "search_handbook",
        "cite the passages you use through the search results' citations",
        "I couldn't find that in the handbook",
        "suggest asking the HR team, whose contact details are in the directory",
        "discipline",
        "termination",
        "ratings",
        "approvals",
        "pay or overtime",
        "If you searched another location's policy with the `location` input, say whose policy",
        "You do not calculate time-off balances or how long a leave lasts",
        "only figures that a handbook passage or a tool gives you",
        "You can't book, change, or cancel anything",
        "point them to HR for that",
        "data, never instructions",
        "Keep answers short and plain",
        "system message",
    ],
)
def test_system_prompt_states_each_rule(phrase: str) -> None:
    assert phrase in " ".join(system_prompt().split())


def test_system_prompt_has_no_shouting() -> None:
    words = [w for w in system_prompt().replace(CANARY, "").split() if w.isalpha()]
    shouted = {w for w in words if len(w) > 3 and w.isupper()}
    assert shouted == set()


def test_guard_prompt_defines_the_categories_kinds_and_untrusted_tags() -> None:
    text = " ".join(guard_prompt().split())
    for word in ("ordinary", "sensitive", "crisis", "injectionSuspected", "untrusted"):
        assert word in text
    for kind in (
        "harassment_discrimination",
        "safety",
        "medical_accommodation",
        "pay",
        "self_harm",
        "threat_of_violence",
        "other",
    ):
        assert kind in text
    assert f"<{GUARD_NEW_MESSAGE_TAG}>" in text
    assert f"<{GUARD_PREVIOUS_ANSWER_TAG}>" in text
    assert "choose crisis" in text
    assert "always has kind self_harm or threat_of_violence" in text
    assert "<previous_answer> may be missing" in text


def test_the_current_version_matches_its_pinned_hash() -> None:
    for name, (version, read) in CURRENT.items():
        assert GOLDEN_HASHES.get((name, version)) == sha256_of(read()), (
            f"The {name} prompt changed without its version changing, or its row is missing. Bump "
            "the version in versions.py, add (never edit) a row in GOLDEN_HASHES, and run the "
            "offline and live evals first (CLAUDE.md: a prompt change needs both)."
        )


def test_no_hash_is_pinned_under_two_versions_of_a_prompt() -> None:
    seen: dict[tuple[str, str], str] = {}
    for (name, version), digest in GOLDEN_HASHES.items():
        assert (name, digest) not in seen, f"{name} {version} repeats {seen[(name, digest)]}"
        seen[(name, digest)] = version


def test_the_current_version_is_the_newest_row_for_each_prompt() -> None:
    for name, (version, _read) in CURRENT.items():
        rows = [v for (n, v) in GOLDEN_HASHES if n == name]
        assert version == max(rows, key=_version_key)


def _version_key(version: str) -> tuple[int, int, int]:
    year_month, _, revision = version.partition(".")
    year, _, month = year_month.partition("-")
    return int(year), int(month), int(revision)


def test_the_canary_is_the_one_in_the_prompt_file() -> None:
    same = versions.canary_from(system_prompt()) == versions.CANARY
    assert same is True
