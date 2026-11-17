"""The live check through the production image (Phase 8, Task 46).

PAID with the real model: about $0.25, capped at $1 by the app's own AI budgets for the run. The
production image runs on its own database (`make prod-local`), and a browser (Chromium, through
apps/web/e2e/live/check.ts) starts a sandbox with Cloudflare's always-pass test key, asks a policy
question and waits for its cited answer, books a day off and confirms the card, and listens for
any Content Security Policy violation (nothing on the server receives CSP reports, so the page is
where they show). Then the run's database is read: every turn has its tokens, cost, cache reads,
and the model that served it, each question is stored encrypted, and neither question appears as
plain text in the conversation tables.

    uv run python ../../scripts/prod-local/live_check.py --dry-run   # free: the scripted model
    uv run python ../../scripts/prod-local/live_check.py --yes       # paid: the real model

Run from apps/api. The result is printed and written to --out as JSON.
"""

import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
WEB = REPO / "apps" / "web"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "image"))
import container  # noqa: E402  (scripts/image/container.py)
import start  # noqa: E402  (scripts/prod-local/start.py)

CAP_USD = "1.00"
DEFAULT_OUT = Path("/tmp/od-live-check")  # noqa: S108  # a person's own scratch folder
# The two questions the browser asks (apps/web/e2e/live/check.ts), as written there.
PHRASES = ("How many sick days do I get", "Book this Friday off")
QUESTIONS_ASKED = 2


@dataclass(frozen=True)
class TurnRow:
    status: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cost_usd: Decimal
    served_by: list[str]


TURNS_SQL = (
    "SELECT status, input_tokens, output_tokens, cache_read_tokens, cost_usd, served_by_models"
    " FROM ai_turns ORDER BY started_at"
)
SEALED_SQL = "SELECT count(*) FROM ai_turns WHERE question_ciphertext IS NOT NULL"
SPENT_SQL = "SELECT coalesce(sum(amount_usd), 0) FROM ai_spend_daily"


def plaintext_sql() -> str:
    """How many rows of the conversation tables hold either question as plain text. The phrases
    are this file's constants, never input."""
    tests = " OR ".join(f"row::text ILIKE '%{phrase}%'" for phrase in PHRASES)
    counts = (
        f"(SELECT count(*) FROM {table} AS row WHERE {tests})"  # noqa: S608
        for table in ("ai_turns", "ai_messages", "ai_console_turns")
    )
    return "SELECT " + " + ".join(counts)


def parse_turn(line: str) -> TurnRow:
    status, inputs, outputs, cache_reads, cost, served = line.split("|")
    models = [m for m in served.strip("{}").split(",") if m]
    return TurnRow(status, int(inputs), int(outputs), int(cache_reads), Decimal(cost), models)


def problems(
    turns: list[TurnRow], *, plaintext_rows: int, sealed_turns: int, dry_run: bool
) -> list[str]:
    """What is wrong with the run, in words; empty when it passed."""
    found: list[str] = []
    completed = [t for t in turns if t.status == "completed"]
    if len(completed) != QUESTIONS_ASKED:
        found.append(
            f"expected {QUESTIONS_ASKED} completed turns, found {len(completed)}"
            f" (statuses: {[t.status for t in turns]})"
        )
    for number, turn in enumerate(completed, start=1):
        if turn.input_tokens <= 0:
            found.append(f"turn {number} has no input tokens")
        if turn.output_tokens <= 0:
            found.append(f"turn {number} has no output tokens")
        if not dry_run and turn.cache_read_tokens <= 0:
            found.append(f"turn {number} has no cache reads")
        if not dry_run and turn.cost_usd <= 0:
            found.append(f"turn {number} has no cost")
        real = [m for m in turn.served_by if m.startswith("claude-")]
        if not turn.served_by or (not dry_run and not real):
            found.append(f"turn {number} has no real model in served_by: {turn.served_by}")
    if sealed_turns != len(turns) or not turns:
        found.append(f"only {sealed_turns} of {len(turns)} turns have their question encrypted")
    if plaintext_rows:
        found.append(f"{plaintext_rows} conversation rows hold a question in plain text")
    return found


def run(*, dry_run: bool, port: int, out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    # An earlier run's browser report must never stand in for this run's.
    (out / "browser.json").unlink(missing_ok=True)
    secrets_ = start.read_secrets()
    budgets = (
        {"daily": "1000", "sandbox": "1000"} if dry_run else {"daily": CAP_USD, "sandbox": CAP_USD}
    )
    print(
        "Live check, dry run (scripted model, free)"
        if dry_run
        else f"Live check with the real model, capped at ${CAP_USD}",
        flush=True,
    )
    with start.running(secrets_, port, scripted=dry_run, budgets_usd=budgets) as origin:
        env = {**os.environ, "LIVE_BASE_URL": origin, "LIVE_OUT": str(out)}
        try:
            browser_code = subprocess.run(
                ["npx", "playwright", "test", "--config", "playwright.live.config.ts"],  # noqa: S607
                cwd=WEB, env=env, check=False,
            ).returncode  # fmt: skip
        except OSError as error:  # npx isn't there, say
            print(f"The browser part could not start: {error}", file=sys.stderr)
            browser_code = 1
        # Read after the browser, not in a `finally`: a database error here must not hide the
        # browser's own failure, which is already printed above.
        spent = start.query(SPENT_SQL)
        turns = [parse_turn(line) for line in start.query(TURNS_SQL).splitlines() if line]
        plaintext = int(start.query(plaintext_sql()))
        sealed = int(start.query(SEALED_SQL))
    found = problems(turns, plaintext_rows=plaintext, sealed_turns=sealed, dry_run=dry_run)
    if browser_code != 0:
        found.insert(0, "the browser part failed (see its output above)")
    report = {
        "dryRun": dry_run,
        "spentUsd": spent,
        "turns": [{**asdict(t), "cost_usd": str(t.cost_usd)} for t in turns],
        "plaintextRows": plaintext,
        "sealedTurns": sealed,
        "browser": json.loads((out / "browser.json").read_text())
        if (out / "browser.json").exists()
        else None,
        "problems": found,
    }
    (out / "live-check.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    print("Live check passed." if not found else "Live check FAILED:\n- " + "\n- ".join(found))
    return 0 if not found else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--dry-run", action="store_true", help="the scripted model: free")
    parser.add_argument("--yes", action="store_true", help="the real model (the owner said yes)")
    parser.add_argument("--port", type=int, default=start.DEFAULT_PORT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    options = parser.parse_args(argv)
    if not options.dry_run and not options.yes:
        print(
            "The live check with the real model is paid (about $0.25, cap $1). Pass --yes once the"
            " owner has agreed, or --dry-run for a free run.",
            file=sys.stderr,
        )
        return 1
    try:
        port = start.check_port(options.port)
        return run(dry_run=options.dry_run, port=port, out=options.out)
    except (start.LaunchError, container.ContainerError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
