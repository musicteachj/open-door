"""Build the boards of run files that were written before boards existed (ADR 0017).

Run it from apps/api, naming the run files:

    uv run python ../../evals/backfill_boards.py RUN_FILE [RUN_FILE ...]

Each board is built by the same `board_of` the live runners use and named the same way
(`evals/scoreboards/<run file stem>.json`), so a backfilled board equals the one a live run would
have written. The run files are only read: nothing is written beside them. A smoke run and a file
whose name carries no stamp are refused. No network and no database.
"""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

# The board writer is the package `assistant` under evals/; this script lives in evals/, so that
# folder is already first on the path when it runs as a script. Say so for any other way in.
EVALS_ROOT = Path(__file__).resolve().parent
if str(EVALS_ROOT) not in sys.path:
    sys.path.insert(0, str(EVALS_ROOT))

from assistant import boards  # noqa: E402


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build run boards from saved run files.")
    parser.add_argument("run_files", nargs="+", type=Path, metavar="RUN_FILE")
    parser.add_argument(
        "--boards-dir",
        type=Path,
        default=boards.SCOREBOARDS_DIR,
        help="where the boards go (default: evals/scoreboards)",
    )
    args = parser.parse_args(argv)

    documents = []
    for path in args.run_files:
        document = json.loads(path.read_text(encoding="utf-8"))
        reason = boards.skip_reason(path, document)
        if reason is not None:
            print(f"{path.name}: no board, because {reason}.")
            return 2
        documents.append((path, document))

    for path, document in documents:
        target = boards.write_boards(path, document, args.boards_dir, beside=False)
        print(f"Wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
