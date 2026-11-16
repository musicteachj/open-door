"""Record the walkthrough video: `make walkthrough` (Phase 8, Task 45).

PAID with the real model: about $0.25 a take. The production image runs on its own database
(`make prod-local`), and the recording drives the guided tour through it at a reading pace
(apps/web/e2e/walkthrough/record.ts). The whole recording has one cap, $2 by default: each take's
AI budgets (the day's and the sandbox's, enforced by the app) are set to the cap less what the
earlier takes spent, measured from the run's own ledger and kept in `takes.json` beside the takes.

    uv run python ../../scripts/walkthrough/record.py --dry-run         # free: the scripted model
    uv run python ../../scripts/walkthrough/record.py --yes             # one paid take
    uv run python ../../scripts/walkthrough/record.py --install DIR     # put a reviewed take in

Each take leaves walkthrough.mp4, walkthrough-poster.jpg, and walkthrough.json in its folder under
--takes (default /tmp/od-walkthrough). Nothing goes into the app until a person has watched the
take and runs --install. Run from apps/api (the API's settings supply the keys and the keyring).
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from decimal import ROUND_DOWN, Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
WEB = REPO / "apps" / "web"
sys.path.insert(0, str(HERE.parent / "prod-local"))
sys.path.insert(0, str(HERE.parent / "image"))
import container  # noqa: E402  (scripts/image/container.py)
import start  # noqa: E402  (scripts/prod-local/start.py)

DEFAULT_TAKES = Path("/tmp/od-walkthrough")  # noqa: S108  # a person's own scratch folder
DEFAULT_CAP_USD = Decimal("2.00")
# The least a take can run with: a turn first reserves its worst case (about $0.20 for Opus).
SMALLEST_TAKE_USD = Decimal("0.30")
LEDGER = "takes.json"
FILES = ("walkthrough.json", "walkthrough.mp4", "walkthrough-poster.jpg")
DRY_RUN_MODEL = "Scripted model (dry run)"
CENT = Decimal("0.01")


class RecordError(Exception):
    """Something stops the recording; the message is for a person."""


# --- the cap -------------------------------------------------------------------------------------


def _ledger(takes: Path) -> dict[str, str]:
    path = takes / LEDGER
    return json.loads(path.read_text()) if path.exists() else {}


def spent_usd(takes: Path) -> Decimal:
    """What the earlier takes spent, as measured after each."""
    return sum((Decimal(v) for v in _ledger(takes).values()), Decimal(0))


def note_take(takes: Path, name: str, spent: Decimal) -> None:
    takes.mkdir(parents=True, exist_ok=True)
    ledger = _ledger(takes)
    ledger[name] = str(spent)
    (takes / LEDGER).write_text(json.dumps(ledger, indent=2) + "\n")


def cap_left_usd(takes: Path, cap: Decimal) -> Decimal:
    left = cap - spent_usd(takes)
    if left < SMALLEST_TAKE_USD:
        raise RecordError(
            f"The recording's cap of ${cap} is used (${spent_usd(takes)} spent): another take"
            " needs the owner's OK for a new cap."
        )
    return left


def budgets_for(left: Decimal) -> dict[str, str]:
    amount = str(left.quantize(CENT, rounding=ROUND_DOWN))
    return {"daily": amount, "sandbox": amount}


def model_id(*, dry_run: bool) -> str:
    if dry_run:
        return "scripted"
    from app.ai.conversations import CURRENT_PINS  # needs apps/api on the path

    return CURRENT_PINS.model


# --- a take's files ------------------------------------------------------------------------------


def set_duration(take: Path, seconds: float) -> None:
    path = take / "walkthrough.json"
    data = json.loads(path.read_text())
    data["durationSeconds"] = round(seconds)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def video_seconds(video: Path) -> float:
    result = subprocess.run(  # noqa: S603
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",  # noqa: S607
         str(video)],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    try:
        return float(result.stdout.strip())
    except ValueError:
        msg = f"ffprobe couldn't read the video's length ({result.stderr.strip()}): {video}"
        raise RecordError(msg) from None


def install(take: Path, *, web_root: Path = WEB) -> None:
    """Copy a watched and approved take into the app: the transcript beside the page, the video and
    poster where the image serves them."""
    for name in FILES:
        if not (take / name).is_file():
            raise RecordError(f"{take} has no {name}: it is not a finished take.")
    if json.loads((take / "walkthrough.json").read_text()).get("model") == DRY_RUN_MODEL:
        raise RecordError("That is a dry run with the scripted model: it is never installed.")
    transcript = web_root / "src" / "features" / "walkthrough"
    media = web_root / "public" / "media"
    transcript.mkdir(parents=True, exist_ok=True)
    media.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(take / "walkthrough.json", transcript / "walkthrough.json")
    shutil.copyfile(take / "walkthrough.mp4", media / "walkthrough.mp4")
    shutil.copyfile(take / "walkthrough-poster.jpg", media / "walkthrough-poster.jpg")


# --- one take ------------------------------------------------------------------------------------


# What a failed take keeps for reading its cause once the containers are gone: each turn's status
# and error code (never its words, which are sealed anyway), and the API's log.
FAILED_TURNS_SQL = (
    "SELECT started_at, status, coalesce(error_code, ''), served_by_models::text"
    " FROM ai_turns ORDER BY started_at"
)


def save_failure(take: Path) -> None:
    take.mkdir(parents=True, exist_ok=True)
    (take / "turns.txt").write_text(start.query(FAILED_TURNS_SQL) + "\n")
    logs = start.docker("logs", start.API_NAME, check=False)
    (take / "api.log").write_text(logs.stdout + logs.stderr)


SPENT_SQL = "SELECT coalesce(sum(amount_usd), 0) FROM ai_spend_daily"
ENCODING_TOOLS = ("ffmpeg", "ffprobe")


def require_encoding_tools() -> None:
    """Checked before a take starts: a paid take that can't be encoded would be money wasted."""
    missing = [tool for tool in ENCODING_TOOLS if shutil.which(tool) is None]
    if missing:
        raise RecordError(
            f"{' and '.join(missing)} not found: install ffmpeg (brew install ffmpeg), then retry."
        )


def settle_take(
    takes: Path, name: str, take: Path, left: Decimal, *, dry_run: bool, failed: bool
) -> None:
    """Notes what a take cost (reservations not yet settled count in full) and keeps a failed
    take's turns and log, without hiding the take's own error. If its database can't be read, all
    the cap had left is noted as spent, so the cap is never under-counted."""
    try:
        spent = Decimal(start.query(SPENT_SQL))
    except start.LaunchError as error:
        if dry_run:
            print(f"Couldn't read the dry run's database ({error}).", file=sys.stderr)
        else:
            spent = left
            print(f"Couldn't read what this take cost ({error}); noting ${left}, all the cap had"
                  " left.", file=sys.stderr)  # fmt: skip
            note_take(takes, name, spent)
            print(f"The recording so far: ${spent_usd(takes)}.")
    else:
        if not dry_run:
            note_take(takes, name, spent)
        print(f"This take spent ${spent} (the recording so far: ${spent_usd(takes)}).")
    if failed:
        try:
            save_failure(take)
        except (start.LaunchError, OSError) as error:
            print(f"Couldn't keep the failed take's turns and log: {error}", file=sys.stderr)


def run_take(*, takes: Path, cap: Decimal, dry_run: bool, port: int) -> int:
    name = ("dry-" if dry_run else "take-") + time.strftime("%Y%m%dT%H%M%S")
    take = takes / name
    left = Decimal("1000") if dry_run else cap_left_usd(takes, cap)
    require_encoding_tools()
    secrets_ = start.read_secrets()
    env = {
        **os.environ,
        "WALKTHROUGH_OUT": str(take),
        "WALKTHROUGH_MODEL_ID": model_id(dry_run=dry_run),
    }
    print(
        f"{'Dry run (scripted model, free)' if dry_run else f'Paid take, capped at ${left}'}:"
        f" {take}",
        flush=True,
    )
    with start.running(secrets_, port, scripted=dry_run, budgets_usd=budgets_for(left)) as origin:
        env["WALKTHROUGH_BASE_URL"] = origin
        returncode = 1
        try:
            returncode = subprocess.run(
                ["npx", "playwright", "test", "--config", "playwright.walkthrough.config.ts"],  # noqa: S607
                cwd=WEB, env=env, check=False,
            ).returncode  # fmt: skip
        except OSError as error:  # npx isn't there, say
            print(f"The browser could not start: {error}", file=sys.stderr)
        finally:
            settle_take(takes, name, take, left, dry_run=dry_run, failed=returncode != 0)
    if returncode != 0:
        print(
            "The take did not finish; nothing was encoded."
            f" Its turns and the API's log are in {take}.",
            file=sys.stderr,
        )
        return returncode
    timing = json.loads((take / "take.json").read_text())
    encoded = subprocess.run(  # noqa: S603
        ["bash", str(HERE / "encode.sh"), str(take / "raw.webm"), str(timing["startSeconds"]),  # noqa: S607
         str(take / "poster.png"), str(take)],
        check=False,
    )  # fmt: skip
    if encoded.returncode != 0:
        # The take itself is kept: encode.sh can be run again on it by hand.
        raise RecordError(f"Encoding failed (see above). The recorded take is kept in {take}.")
    set_duration(take, video_seconds(take / "walkthrough.mp4"))
    print(f"Done. Watch {take / 'walkthrough.mp4'}; after approval, --install {take}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--dry-run", action="store_true", help="the scripted model: free")
    parser.add_argument("--yes", action="store_true", help="a paid take (the owner said yes)")
    parser.add_argument("--install", type=Path, help="copy a reviewed take into the app")
    parser.add_argument("--takes", type=Path, default=DEFAULT_TAKES)
    parser.add_argument("--cap-usd", type=Decimal, default=DEFAULT_CAP_USD)
    parser.add_argument("--port", type=int, default=start.DEFAULT_PORT)
    options = parser.parse_args(argv)
    try:
        if options.install:
            install(options.install)
            print(f"Installed {options.install} into {WEB}")
            return 0
        if not options.dry_run and not options.yes:
            raise RecordError(
                "A take with the real model is paid (about $0.25). Pass --yes (make walkthrough"
                " YES=1) once the owner has agreed, or --dry-run for a free run."
            )
        port = start.check_port(options.port)
        return run_take(
            takes=options.takes, cap=options.cap_usd, dry_run=options.dry_run, port=port
        )
    except (RecordError, start.LaunchError, container.ContainerError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
