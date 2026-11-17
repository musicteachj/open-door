"""Run the `open-door:test` image in the foreground, for Playwright: `E2E_TARGET=image`.

Playwright's `webServer` owns this process. It starts the container (a stale one of the same name
is removed first), keeps the last lines of the container's output (printed to stderr only if the
container exits early, so a passing run stays quiet), and stops the container when it
receives SIGTERM, SIGINT, or SIGHUP, so a stopped or killed launcher never leaves the API running.
The container serves the whole app (the web build with the gallery, and the API) on one origin.

    uv run python ../../scripts/image/serve.py --port 8100 --origin http://localhost:8100

Run it from apps/api (the API's settings supply the database URL).
"""

import argparse
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from types import FrameType
from typing import IO

sys.path.insert(0, str(Path(__file__).resolve().parent))
import container

# uvicorn's 15-second graceful timeout plus the up to 12 seconds it takes to save open streams
# (app/main.py), with room: `docker stop` must not kill it while it is still saving a turn.
STOP_GRACE_SECONDS = 30
# How much of the container's output is kept for an early exit's report.
TAIL_LINES = 200


@dataclass
class LauncherState:
    """What the signal handler and the main thread share."""

    process: subprocess.Popen[bytes] | None = None
    stopping: bool = False


def keep_tail(stream: IO[bytes], tail: deque[bytes]) -> None:
    """Read the container's output to the end (so the pipe never fills), keeping the last lines."""
    for line in stream:
        tail.append(line)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default="open-door-e2e")
    parser.add_argument("--port", type=int, default=8100)
    parser.add_argument("--origin", default="http://localhost:8100")
    parser.add_argument("--heartbeat-seconds")
    parser.add_argument("--daily-budget-usd", default="1000")
    options = parser.parse_args(argv)

    env = container.api_env(
        origin=options.origin,
        port=options.port,
        heartbeat_seconds=options.heartbeat_seconds,
        daily_budget_usd=options.daily_budget_usd,
    )
    state = LauncherState()

    def stop_container() -> None:
        # `docker stop` sends SIGTERM to uvicorn (PID 1), waits for it to drain, then
        # kills it. A signal can arrive after `docker run` started but before the container
        # exists, when `docker stop` finds nothing, so it is retried until `docker run` has exited
        # (or the grace period and a margin pass). `--rm` removes it; `remove` below covers a
        # launcher that dies first.
        process = state.process
        if process is None:
            return
        deadline = time.monotonic() + STOP_GRACE_SECONDS + 10
        while process.poll() is None and time.monotonic() < deadline:
            subprocess.run(  # noqa: S603
                ["docker", "stop", "--time", str(STOP_GRACE_SECONDS), options.name],  # noqa: S607
                check=False,
                capture_output=True,
            )
            if process.poll() is None:
                time.sleep(0.5)

    def stop_in_background() -> None:
        # Off the signal handler, so the main thread keeps waiting on `docker run`.
        threading.Thread(target=stop_container, daemon=True).start()

    def on_signal(_signum: int, _frame: FrameType | None) -> None:
        # A signal before the container exists only sets the flag: the start below sees it.
        already = state.stopping
        state.stopping = True
        if state.process is not None and not already:
            stop_in_background()

    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(signum, on_signal)

    container.remove(options.name)
    # The output is read in a thread and only its tail kept: printed if the container exits early
    # (Playwright shows the launcher's stderr), never on a normal run.
    process = subprocess.Popen(  # noqa: S603
        container.run_args(options.name, env, port=options.port, detach=False),
        env=container.client_env(env),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    state.process = process
    tail: deque[bytes] = deque(maxlen=TAIL_LINES)
    assert process.stdout is not None  # noqa: S101  # stdout=PIPE above.
    reader = threading.Thread(target=keep_tail, args=(process.stdout, tail), daemon=True)
    reader.start()
    if state.stopping:
        stop_in_background()
    try:
        code = process.wait()
    finally:
        container.remove(options.name)
    reader.join(timeout=5)
    if code not in (0, 143) and not state.stopping:
        sys.stderr.buffer.write(b"".join(tail))
        print(f"the {container.TEST_TAG} container exited early with code {code}", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
