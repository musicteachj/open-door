"""Put trial 1's summaries of the seeded cases into `seed_data.py`.

A paid case-summary run (`make eval-live SET=case-summary YES=1`) writes a `-seeded.json` file
beside its scoreboard: for each seeded case, the summary the model wrote in trial 1, with the model
and the prompt version. This script checks each one and rewrites the block between the
`BEGIN SEEDED SUMMARIES` and `END SEEDED SUMMARIES` markers in `app/modules/sandbox/seed_data.py`.
Nothing else in the file changes.

    uv run python scripts/apply_seeded_summaries.py <the run's -seeded.json>
    uv run python scripts/apply_seeded_summaries.py <file> --check   # print the block only

Each summary must pass `summary_problem` against its own case's words, the model and prompt
version must be real (not the placeholder's), and the case must be one of the seeded four. The
summary is the owner's to read before this runs: it becomes what every new demo sandbox shows HR.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from app.ai.case_summary import summary_problem
from app.modules.sandbox.seed_data import (
    CASES,
    SEEDED_SUMMARY_MODEL,
    SEEDED_SUMMARY_PROMPT_VERSION,
    SeededSummary,
)

BEGIN = "# BEGIN SEEDED SUMMARIES\n"
END = "# END SEEDED SUMMARIES\n"
SEED_DATA = Path(__file__).resolve().parents[1] / "app/modules/sandbox/seed_data.py"
_PLACEHOLDER_VALUES = {SEEDED_SUMMARY_MODEL, SEEDED_SUMMARY_PROMPT_VERSION, ""}


class ApplyError(Exception):
    """The run's file can't be put into the seed. The message says why."""


def read_run(path: Path) -> dict[str, SeededSummary]:
    """The run's seeded summaries, checked. Raises `ApplyError` naming each problem."""
    try:
        data: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ApplyError(f"{path}: can't be read ({type(error).__name__})") from error
    entries = data.get("summaries") if isinstance(data, dict) else None
    if not isinstance(entries, dict) or not entries:
        raise ApplyError(f"{path}: has no summaries")
    words = {case.key: case.text for case in CASES}
    found: dict[str, SeededSummary] = {}
    problems: list[str] = []
    for key, entry in entries.items():
        if key not in words:
            problems.append(f"{key}: not a seeded case")
            continue
        if not isinstance(entry, dict) or {"text", "model", "promptVersion"} - set(entry):
            problems.append(f"{key}: needs text, model, and promptVersion")
            continue
        text, model, version = entry["text"], entry["model"], entry["promptVersion"]
        if not all(isinstance(v, str) for v in (text, model, version)):
            problems.append(f"{key}: text, model, and promptVersion must be strings")
        elif model in _PLACEHOLDER_VALUES or version in _PLACEHOLDER_VALUES:
            problems.append(f"{key}: the model and prompt version must be the real ones")
        elif (found_problem := summary_problem(text, words[key])) is not None:
            problems.append(f"{key}: the summary fails the check ({found_problem})")
        else:
            found[key] = SeededSummary(text, model, version)
    # A run that lacks a seeded case would silently drop that case's approved summary.
    problems += [
        f"{key}: the run has no summary for this seeded case" for key in words if key not in entries
    ]
    if problems:
        raise ApplyError("\n".join(problems))
    return found


# Each summary is written as adjacent string pieces, so no line passes the 100-character limit.
_PIECE_CHARACTERS = 80


def _pieces(text: str) -> list[str]:
    """`text` cut after spaces into pieces of at most about `_PIECE_CHARACTERS`, which join back to
    exactly `text`."""
    pieces: list[str] = []
    current = ""
    # Each chunk is a word with the spaces after it, so every character lands in a piece.
    for chunk in re.findall(r"[^ ]* *", text):
        if current and len((current + chunk).rstrip(" ")) > _PIECE_CHARACTERS:
            pieces.append(current)
            current = chunk
        else:
            current += chunk
    if current:
        pieces.append(current)
    return pieces


def render_block(summaries: dict[str, SeededSummary]) -> str:
    """The Python for `SEEDED_SUMMARIES`, in the seeded cases' own order."""
    lines = ["SEEDED_SUMMARIES: Mapping[str, SeededSummary] = {\n"]
    for case in CASES:
        summary = summaries.get(case.key)
        if summary is None:
            continue
        lines += [
            f"    {case.key!r}: SeededSummary(\n",
            "        text=(\n",
            *(f"            {piece!r}\n" for piece in _pieces(summary.text)),
            "        ),\n",
            f"        model={summary.model!r},\n",
            f"        prompt_version={summary.prompt_version!r},\n",
            "    ),\n",
        ]
    lines.append("}\n")
    return "".join(lines)


def apply(run_file: Path, seed_data: Path = SEED_DATA) -> bool:
    """Rewrite the marked block. Returns whether the file changed."""
    block = render_block(read_run(run_file))
    source = seed_data.read_text(encoding="utf-8")
    head, found_begin, rest = source.partition(BEGIN)
    _, found_end, tail = rest.partition(END)
    if not found_begin or not found_end:
        raise ApplyError(f"{seed_data}: the BEGIN and END SEEDED SUMMARIES markers are missing")
    updated = head + BEGIN + block + END + tail
    if updated == source:
        return False
    seed_data.write_text(updated, encoding="utf-8")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    parser.add_argument("run_file", type=Path, help="the case-summary run's -seeded.json")
    parser.add_argument("--check", action="store_true", help="print the block and change nothing")
    args = parser.parse_args(argv)
    try:
        if args.check:
            print(render_block(read_run(args.run_file)), end="")
            return 0
        changed = apply(args.run_file)
    except ApplyError as error:
        print(f"Can't apply: {error}", file=sys.stderr)
        return 1
    print("seed_data.py updated." if changed else "seed_data.py already holds these summaries.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
