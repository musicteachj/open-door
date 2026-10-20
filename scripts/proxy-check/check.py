"""Prove the turn stream survives a strict reverse proxy: `make proxy-check`.

Run it with `make proxy-check`, after `make db` (locally) or the E2E job's setup (in CI): it
uses the seeded database.

It starts the API itself on :8200 (no reload, the scripted model), puts nginx in front of it on
:8201 and :8202 (`compose.yaml`, `nginx.conf`), starts a sandbox as a browser would, and runs four
checks. Two of them are controls that show an assertion can fail:

1. The pass run asks the scripted 45-second-silence question. The stream must complete, start
   within 2 seconds, arrive spread over time with keep-alive comments in the quiet, and not be
   compressed. nginx is told to compress `text/event-stream` (by default it compresses only
   `text/html`, so the assertion could not fail). With that setting and no app header, nginx
   gzipped the stream and held every event back for the full 45 seconds; the app now sends
   `Content-Encoding: identity`, which nginx leaves alone, and the run shows no compression.
2. The heartbeat control turns the heartbeat off. nginx must cut the silent stream at about 20
   seconds. It proves the read-timeout half of the pass run: that the keep-alives are what keep
   the stream alive.
3. The holding control runs the API with a one-second heartbeat and listens for 5 seconds. Through
   the normal nginx (:8201) at least 2 keep-alives must arrive; through the second server (:8202),
   which hides the app's `Content-Encoding: identity` so nginx gzips the stream, none may, and
   nothing readable may arrive in time. It proves the pass run's timing assertions can fail.
   (`proxy_buffering on` alone does not hold a small stream in nginx: see `nginx.conf`.) The runs
   disconnect after 5 seconds, which stops their turns.
4. The shutdown run sends SIGTERM to the API in the middle of a silent stream. It must exit cleanly
   (code 0, or ended by SIGTERM after uvicorn's shutdown) within its grace period, and the turn
   must be saved as `stopped`.

Everything it starts is stopped at the end, even on failure, and the sandbox and daily-ledger rows
its turns added are deleted. The judgment (`problems_in_*`) is plain functions on recorded
timelines, tested offline in `apps/api/tests/test_proxy_check_script.py`.
"""

import asyncio
import codecs
import os
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

API_PORT = 8200
NGINX_PORT = 8201
BUFFERED_PORT = 8202
NGINX_ORIGIN = f"http://127.0.0.1:{NGINX_PORT}"
BUFFERED_ORIGIN = f"http://127.0.0.1:{BUFFERED_PORT}"
API_ORIGIN = f"http://127.0.0.1:{API_PORT}"
# The buffering control listens this long for a first event, then disconnects.
BUFFERING_LISTEN_SECONDS = 5.0
HERE = Path(__file__).resolve().parent
API_DIR = HERE.parents[1] / "apps" / "api"

# The scripted model's silent scenario: no events for 45 seconds, then an answer.
SILENCE_QUESTION = "scripted silence: how much paid sick leave do I get?"
SILENCE_SECONDS = 45

# What a good stream looks like through the proxy.
FIRST_EVENT_LIMIT_SECONDS = 2.0
# The first and last event are at least this far apart (the silence is 45 seconds).
SPREAD_MINIMUM_SECONDS = 30.0
# Keep-alives that arrive while the stream is still quiet (before this many seconds from the end of
# the silence). A proxy that buffers delivers them all together when the stream ends.
KEEP_ALIVES_MINIMUM = 2
KEEP_ALIVES_BY_SECONDS = SILENCE_SECONDS - 5
# nginx's proxy_read_timeout is 20 seconds; with no heartbeat it cuts a silent stream there.
CONTROL_CUT_BETWEEN_SECONDS = (15.0, 30.0)

# uvicorn waits this long for open requests before it cancels them. ECS waits 30 seconds by default
# before it kills a container, and after uvicorn's timeout the app needs up to about 12 seconds to
# save the streams still open (see `app/main.py`), so 15 + 12 fits inside the 30 with room to spare.
GRACEFUL_SHUTDOWN_SECONDS = 15
SHUTDOWN_EXIT_LIMIT_SECONDS = 40.0


# --- The judgment: plain functions on what was seen ---------------------------------------


@dataclass(frozen=True)
class Mark:
    """One thing that arrived on the stream: an event (with its name) or a comment."""

    at_seconds: float
    kind: str  # "event" or "comment"
    name: str


@dataclass(frozen=True)
class Timeline:
    status: int
    content_encoding: str | None
    marks: tuple[Mark, ...]
    # False when the connection was cut before the response ended properly.
    ended_cleanly: bool
    total_seconds: float

    @property
    def events(self) -> list[Mark]:
        return [mark for mark in self.marks if mark.kind == "event"]

    @property
    def completed(self) -> bool:
        return any(mark.name == "turn.completed" for mark in self.events)


class StreamReader:
    """Splits the text of an event stream into marks as each event or comment is complete."""

    def __init__(self) -> None:
        self._buffer = ""

    def feed(self, text: str, at: float) -> list[Mark]:
        self._buffer += text
        marks: list[Mark] = []
        while "\n\n" in self._buffer:
            block, self._buffer = self._buffer.split("\n\n", 1)
            lines = [line for line in block.split("\n") if line]
            if not lines:
                continue
            if all(line.startswith(":") for line in lines):
                marks.append(Mark(at, "comment", ""))
            elif lines[0].startswith("event: "):
                marks.append(Mark(at, "event", lines[0].removeprefix("event: ")))
        return marks


def problems_in_pass_run(timeline: Timeline) -> list[str]:
    problems: list[str] = []
    if timeline.status != 200:
        problems.append(f"The stream answered {timeline.status}, not 200.")
    if timeline.content_encoding and timeline.content_encoding.lower() != "identity":
        problems.append(
            f"The stream has Content-Encoding: {timeline.content_encoding}. An event stream "
            "must not be compressed: a compressor holds events back."
        )
    events = timeline.events
    if not events:
        problems.append("No event arrived.")
        return problems
    if not timeline.completed:
        how = "was cut" if not timeline.ended_cleanly else "ended"
        problems.append(f"The stream {how} without turn.completed.")
    first, last = events[0].at_seconds, events[-1].at_seconds
    if first > FIRST_EVENT_LIMIT_SECONDS:
        problems.append(
            f"The first event arrived after {first:.1f} s, not within "
            f"{FIRST_EVENT_LIMIT_SECONDS:.0f} s: the proxy is holding the response back."
        )
    if last - first < SPREAD_MINIMUM_SECONDS:
        problems.append(
            f"The events were not spread over time: the first and last were {last - first:.1f} s "
            f"apart, and the silent question takes {SILENCE_SECONDS} s. They arrived in one burst."
        )
    keep_alives = sum(
        1
        for mark in timeline.marks
        if mark.kind == "comment" and mark.at_seconds <= KEEP_ALIVES_BY_SECONDS
    )
    if keep_alives < KEEP_ALIVES_MINIMUM:
        problems.append(
            f"Only {keep_alives} keep-alive comments arrived during the silence (before "
            f"{KEEP_ALIVES_BY_SECONDS} s); at least {KEEP_ALIVES_MINIMUM} were expected."
        )
    return problems


def keep_alives_in(timeline: Timeline, seconds: float) -> int:
    return sum(1 for m in timeline.marks if m.kind == "comment" and m.at_seconds <= seconds)


def problems_in_control_run(timeline: Timeline) -> list[str]:
    if timeline.completed:
        return [
            "With the heartbeat off, the silent stream still completed, so this check cannot "
            "tell a proxy that cuts quiet streams from one that doesn't."
        ]
    low, high = CONTROL_CUT_BETWEEN_SECONDS
    if not low <= timeline.total_seconds <= high:
        return [
            f"With the heartbeat off, the stream ended after {timeline.total_seconds:.1f} s; "
            f"nginx should cut it at about 20 s (between {low:.0f} and {high:.0f})."
        ]
    return []


def problems_in_buffering_reference(timeline: Timeline) -> list[str]:
    """Through the well-behaved proxy, a one-second heartbeat shows up as keep-alive comments within
    the listening time. Without this, the buffering control's silence would prove nothing."""
    seen = keep_alives_in(timeline, BUFFERING_LISTEN_SECONDS)
    if seen < KEEP_ALIVES_MINIMUM:
        return [
            f"Through the normal proxy only {seen} keep-alive(s) arrived in "
            f"{BUFFERING_LISTEN_SECONDS:.0f} s of a one-second heartbeat; the buffering control "
            "would have nothing to compare with."
        ]
    return []


def problems_in_buffering_control(timeline: Timeline) -> list[str]:
    """Through the second nginx, which gzips (and so holds back) the stream, no keep-alive may
    arrive in the listening time. (gzip holds even the response headers, so often nothing at all
    arrives.) If keep-alives arrive, the pass run's timing assertions could not tell a holding
    proxy from a good one. A status that does arrive must be 200: an error response (a 502 from
    the proxy, a 429 from the API) has no keep-alives either, and would pass for a holding proxy."""
    problems: list[str] = []
    if timeline.status not in (0, 200):
        problems.append(
            f"Through the holding proxy the response status was {timeline.status}, not 200, so "
            "the control did not hold a working stream."
        )
    seen = keep_alives_in(timeline, BUFFERING_LISTEN_SECONDS)
    if seen >= KEEP_ALIVES_MINIMUM:
        problems.append(
            f"Through the holding proxy {seen} keep-alives still arrived in "
            f"{BUFFERING_LISTEN_SECONDS:.0f} s, so the pass run's keep-alive timing check cannot "
            "detect a proxy that holds the stream back."
        )
    return problems


def problems_in_shutdown_run(*, exit_code: int | None, turn_statuses: list[str]) -> list[str]:
    problems: list[str] = []
    # uvicorn finishes its shutdown and then re-raises the signal, so a clean stop ends the process
    # by SIGTERM itself (Python reports -15; a shell reports 143). A crash is 1, a kill is -9.
    if exit_code not in (0, -signal.SIGTERM):
        problems.append(
            f"The API's exit code after SIGTERM was {exit_code}; a clean stop is 0 or "
            f"{-signal.SIGTERM} (ended by SIGTERM itself, after uvicorn finished shutting down)."
        )
    if turn_statuses != ["stopped"]:
        problems.append(
            f"After SIGTERM the turn should be saved as stopped; the conversation shows "
            f"{turn_statuses}."
        )
    return problems


def bind_host_for(platform: str, *, override: str | None, bridge_gateway: str | None) -> str:
    """Where the API listens so that nginx in Docker can reach it, and nothing wider.

    Docker Desktop (macOS) forwards `host.docker.internal` to the host's loopback. On Linux,
    `host-gateway` is the docker bridge's gateway address, so the API listens only there.
    `PROXY_CHECK_BIND` overrides either."""
    if override:
        return override
    if platform == "darwin":
        return "127.0.0.1"
    if bridge_gateway:
        return bridge_gateway
    raise CheckError(
        "Could not find the docker bridge gateway for the API to listen on. "
        "Set PROXY_CHECK_BIND to an address nginx in Docker can reach."
    )


# --- Talking to the stream ----------------------------------------------------------------


def read_stream(
    client: httpx.Client,
    url: str,
    *,
    headers: dict[str, str],
    body: dict[str, Any],
    on_mark: Callable[[Mark], None] | None = None,
    stop_after_seconds: float | None = None,
) -> Timeline:
    """POST and read the response as it arrives, noting when each event and comment came."""
    started = time.monotonic()
    reader = StreamReader()
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    marks: list[Mark] = []
    ended_cleanly = True
    status = 0
    encoding: str | None = None
    try:
        with client.stream("POST", url, headers=headers, json=body) as response:
            status = response.status_code
            encoding = response.headers.get("content-encoding")
            # Raw bytes: the check should see the encoding, not have it undone.
            for chunk in response.iter_raw():
                now = time.monotonic() - started
                if stop_after_seconds is not None and now > stop_after_seconds:
                    ended_cleanly = False
                    break
                for mark in reader.feed(decoder.decode(chunk), now):
                    marks.append(mark)
                    if on_mark is not None:
                        on_mark(mark)
    except (httpx.RemoteProtocolError, httpx.ReadError, httpx.ReadTimeout):
        ended_cleanly = False
    return Timeline(
        status=status,
        content_encoding=encoding,
        marks=tuple(marks),
        ended_cleanly=ended_cleanly,
        total_seconds=time.monotonic() - started,
    )


@dataclass
class Session:
    """A signed-in browser: the cookies are set by hand because `__Host-` cookies are Secure, and
    an HTTP client's cookie jar will not send them over plain http."""

    tenant_id: str
    cookie_header: str
    csrf: str

    def headers(self) -> dict[str, str]:
        return {
            "Cookie": self.cookie_header,
            "X-CSRF-Token": self.csrf,
            "Origin": NGINX_ORIGIN,
            "Sec-Fetch-Site": "same-origin",
        }


def start_sandbox(client: httpx.Client) -> Session:
    response = client.post(
        f"{NGINX_ORIGIN}/api/v1/sandboxes",
        json={},
        headers={"Origin": NGINX_ORIGIN, "Sec-Fetch-Site": "same-origin"},
    )
    response.raise_for_status()
    session = response.cookies.get("__Host-od_session")
    csrf = response.cookies.get("__Host-od_csrf")
    if not session or not csrf:
        raise CheckError("Starting a sandbox did not set the session cookies.")
    return Session(
        tenant_id=response.json()["tenant"]["id"],
        cookie_header=f"__Host-od_session={session}; __Host-od_csrf={csrf}",
        csrf=csrf,
    )


def new_conversation(client: httpx.Client, session: Session) -> str:
    response = client.post(
        f"{NGINX_ORIGIN}/api/v1/assistant/conversations", json={}, headers=session.headers()
    )
    response.raise_for_status()
    return str(response.json()["id"])


def turns_url(conversation_id: str, origin: str = NGINX_ORIGIN) -> str:
    return f"{origin}/api/v1/assistant/conversations/{conversation_id}/turns"


class CheckError(Exception):
    """The proxy check found something wrong; the message is for a person."""


# --- Processes ----------------------------------------------------------------------------


class Api:
    """The API under test: uvicorn without reload, as production runs it."""

    def __init__(self, log: Path, host: str) -> None:
        self.log = log
        self.host = host
        self.process: subprocess.Popen[bytes] | None = None

    def start(self, **extra_env: str) -> None:
        env = {
            **os.environ,
            "AI_TRANSPORT": "scripted",
            "APP_ORIGIN": NGINX_ORIGIN,
            **extra_env,
        }
        command = [
            sys.executable,
            "-m",
            "uvicorn",
            "--factory",
            "app.main:create_app",
            "--host",
            self.host,
            "--port",
            str(API_PORT),
            "--timeout-graceful-shutdown",
            str(GRACEFUL_SHUTDOWN_SECONDS),
        ]
        with self.log.open("ab") as log:
            self.process = subprocess.Popen(  # noqa: S603
                command, cwd=API_DIR, env=env, stdout=log, stderr=subprocess.STDOUT
            )
        self._wait_until_healthy()

    def _wait_until_healthy(self) -> None:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if self.process is not None and self.process.poll() is not None:
                raise CheckError(f"The API exited at startup. Its log:\n{self.tail()}")
            try:
                if (
                    httpx.get(f"http://{self.host}:{API_PORT}/api/v1/health", timeout=2).status_code
                    == 200
                ):
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.5)
        raise CheckError(f"The API did not start within 60 s. Its log:\n{self.tail()}")

    def stop(self) -> None:
        process = self.process
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=SHUTDOWN_EXIT_LIMIT_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

    def tail(self, lines: int = 40) -> str:
        if not self.log.exists():
            return ""
        return "\n".join(self.log.read_text(errors="replace").splitlines()[-lines:])


def compose(*arguments: str) -> None:
    try:
        subprocess.run(  # noqa: S603
            ["docker", "compose", "-f", str(HERE / "compose.yaml"), *arguments],  # noqa: S607
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as error:
        raise CheckError(
            f"`docker compose {' '.join(arguments)}` failed ({error}). Is Docker running?"
        ) from None


def docker_bridge_gateway() -> str | None:
    result = subprocess.run(
        [  # noqa: S607
            "docker",
            "network",
            "inspect",
            "bridge",
            "-f",
            "{{(index .IPAM.Config 0).Gateway}}",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    gateway = result.stdout.strip()
    return gateway if result.returncode == 0 and gateway else None


def refuse_if_in_use(host: str) -> None:
    """A server already on these ports would be checked instead of the one this starts."""
    for name, address, port in (
        ("the API", host, API_PORT),
        ("the API", "127.0.0.1", API_PORT),
        ("nginx", "127.0.0.1", NGINX_PORT),
        ("the buffering nginx", "127.0.0.1", BUFFERED_PORT),
    ):
        with socket.socket() as probe:
            probe.settimeout(1)
            if probe.connect_ex((address, port)) == 0:
                raise CheckError(
                    f"Something already answers on {address}:{port}, where the check starts "
                    f"{name}. Stop it first (a leftover `docker compose -p open-door-proxy-check "
                    "down`, or a stray uvicorn)."
                )


def wait_for_nginx() -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            # Any answer, even a 404 from the API, shows nginx is up and reaching the API.
            if all(
                httpx.get(f"{origin}/api/v1/health", timeout=2).status_code == 200
                for origin in (NGINX_ORIGIN, BUFFERED_ORIGIN)
            ):
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    raise CheckError("Both nginx servers did not come up and reach the API within 30 s.")


# --- The database: leave it as it was found -----------------------------------------------


def owner_database_url() -> str:
    os.chdir(API_DIR)  # So the settings find apps/api/.env.
    sys.path.insert(0, str(API_DIR))
    from app.core.config import Settings

    settings = Settings()
    url = settings.migration_database_url
    if url is None:
        raise CheckError("MIGRATION_DATABASE_URL is not set, so the check cannot clean up.")
    return str(url)


async def database_now(url: str) -> Any:
    """The database's own clock, so the cleanup window does not depend on this machine's."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            return await connection.scalar(text("SELECT now()"))
    finally:
        await engine.dispose()


async def clean_up_database(url: str, tenant_ids: list[str], started_at: Any) -> None:
    """Delete the sandboxes this run created (their rows go with them) and exactly the daily-ledger
    rows its own turns wrote.

    The daily ledger has no tenant, so nothing cascades. Like `evals/assistant/run.py`, this reads
    the sandbox's own `ai_spend` rows, then deletes one daily row for each, of the same kind and
    amount and the same instant, and the sandboxes, in one transaction (the shared
    `app.db.spend_cleanup`). A row is taken only if it is also no older than the run's start.
    Another sandbox's row would need the same kind, amount, and microsecond."""
    from uuid import UUID

    from sqlalchemy.ext.asyncio import create_async_engine

    from app.db.spend_cleanup import remove_sandboxes, spend_rows_of

    ids = [UUID(tenant_id) for tenant_id in tenant_ids]
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            rows = await spend_rows_of(connection, ids, not_before=started_at) if ids else []
        await remove_sandboxes(engine, ids, rows, not_before=started_at)
    finally:
        await engine.dispose()


# --- The runs -----------------------------------------------------------------------


def pass_run(client: httpx.Client, session: Session) -> None:
    print(f"Pass run: the {SILENCE_SECONDS}-second silence through nginx (takes about a minute)...")
    timeline = read_stream(
        client,
        turns_url(new_conversation(client, session)),
        headers=session.headers(),
        body={"question": SILENCE_QUESTION},
    )
    describe(timeline)
    fail_on(problems_in_pass_run(timeline), "pass run")


def listen(session: Session, origin: str) -> Timeline:
    """Ask the silent question and listen for a few seconds, then disconnect: no bytes for that long
    ends the read, which closes the connection, so the turn is stopped."""
    timeout = httpx.Timeout(90, connect=10, read=BUFFERING_LISTEN_SECONDS)
    deadline = BUFFERING_LISTEN_SECONDS
    with httpx.Client(timeout=timeout) as quick:
        conversation_id = new_conversation(quick, session)
        return read_stream(
            quick,
            turns_url(conversation_id, origin),
            headers=session.headers(),
            body={"question": SILENCE_QUESTION},
            stop_after_seconds=deadline,
        )


def buffering_control_run(session: Session) -> None:
    print(
        "Holding control: a one-second heartbeat, "
        f"{BUFFERING_LISTEN_SECONDS:.0f} s through each nginx..."
    )
    normal = listen(session, NGINX_ORIGIN)
    describe(normal)
    fail_on(problems_in_buffering_reference(normal), "holding reference (normal nginx)")
    buffered = listen(session, BUFFERED_ORIGIN)
    describe(buffered)
    fail_on(problems_in_buffering_control(buffered), "holding control (gzipping nginx)")
    time.sleep(1)  # Let the API save the stopped turns before anything restarts it.


def control_run(client: httpx.Client, session: Session) -> None:
    print("Heartbeat control: the heartbeat off; nginx must cut the silent stream at about 20 s...")
    timeline = read_stream(
        client,
        turns_url(new_conversation(client, session)),
        headers=session.headers(),
        body={"question": SILENCE_QUESTION},
    )
    describe(timeline)
    fail_on(problems_in_control_run(timeline), "heartbeat control")


def shutdown_run(client: httpx.Client, session: Session, api: Api) -> None:
    print("Shutdown run: SIGTERM in the middle of a silent stream...")
    conversation_id = new_conversation(client, session)
    started = threading.Event()
    result: list[Timeline] = []

    def read() -> None:
        # Its own client: the main thread's is not shared across threads.
        with httpx.Client(timeout=httpx.Timeout(90, connect=10)) as own:
            result.append(
                read_stream(
                    own,
                    turns_url(conversation_id),
                    headers=session.headers(),
                    body={"question": SILENCE_QUESTION},
                    on_mark=lambda mark: started.set(),
                )
            )

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    if not started.wait(timeout=10):
        raise CheckError("The silent stream did not start within 10 s.")
    time.sleep(1)  # Into the silence.
    process = api.process
    if process is None:
        raise CheckError("The API is not running.")
    sent = time.monotonic()
    process.send_signal(signal.SIGTERM)
    try:
        process.wait(timeout=SHUTDOWN_EXIT_LIMIT_SECONDS)
    except subprocess.TimeoutExpired:
        raise CheckError(
            f"The API was still running {SHUTDOWN_EXIT_LIMIT_SECONDS:.0f} s after SIGTERM "
            f"(the graceful timeout is {GRACEFUL_SHUTDOWN_SECONDS} s plus about 12 s to save "
            f"streams)."
        ) from None
    print(
        f"  the API exited {time.monotonic() - sent:.1f} s after SIGTERM,"
        f" exit code {process.returncode}"
    )
    reader.join(timeout=10)

    api.start()  # Fresh, as a replacement container would be.
    response = client.get(
        f"{NGINX_ORIGIN}/api/v1/assistant/conversations/current", headers=session.headers()
    )
    response.raise_for_status()
    current = response.json()
    turns = current["turns"] if current else []
    statuses = [turn["status"] for turn in turns]
    print(f"  the conversation's turn is now: {statuses}")
    problems = problems_in_shutdown_run(exit_code=process.returncode, turn_statuses=statuses)
    if not current or current["id"] != conversation_id:
        problems.append("The current conversation is not the one the shutdown run asked in.")
    fail_on(problems, "shutdown run")


def describe(timeline: Timeline) -> None:
    events = timeline.events
    keep_alives = sum(1 for mark in timeline.marks if mark.kind == "comment")
    first = f"{events[0].at_seconds:.1f}" if events else "-"
    print(
        f"  status {timeline.status}, {len(events)} events (first at {first} s), "
        f"{keep_alives} keep-alives, "
        f"{'ended' if timeline.ended_cleanly else 'cut'} at {timeline.total_seconds:.1f} s, "
        f"Content-Encoding: {timeline.content_encoding or 'none'}, "
        f"turn.completed: {'yes' if timeline.completed else 'no'}"
    )


def fail_on(problems: list[str], name: str) -> None:
    if problems:
        raise CheckError(f"The {name} failed:\n- " + "\n- ".join(problems))
    print(f"  {name}: ok")


def main() -> int:
    sys.stdout.reconfigure(line_buffering=True)  # type: ignore[union-attr]
    started_at = time.monotonic()
    tenant_ids: list[str] = []
    log = Path(tempfile.mkdtemp(prefix="od-proxy-check-")) / "api.log"
    failed = False
    api: Api | None = None
    url: str | None = None
    db_started: Any = None
    try:
        url = owner_database_url()
        host = bind_host_for(
            sys.platform,
            override=os.environ.get("PROXY_CHECK_BIND"),
            bridge_gateway=docker_bridge_gateway() if sys.platform != "darwin" else None,
        )
        refuse_if_in_use(host)
        api = Api(log, host)
        db_started = asyncio.run(database_now(url))
        compose("up", "--detach", "--wait")
        api.start()
        wait_for_nginx()
        with httpx.Client(timeout=httpx.Timeout(90, connect=10)) as client:
            session = start_sandbox(client)
            tenant_ids.append(session.tenant_id)
            pass_run(client, session)

            api.stop()
            api.start(AI_HEARTBEAT_SECONDS="1")
            buffering_control_run(session)

            api.stop()
            api.start(AI_HEARTBEAT_SECONDS="0")
            control_run(client, session)

            api.stop()
            api.start()
            shutdown_run(client, session, api)
    except CheckError as error:
        failed = True
        print(f"\nPROXY CHECK FAILED\n{error}", file=sys.stderr)
    except Exception as error:
        failed = True
        print(
            f"\nPROXY CHECK FAILED unexpectedly: {type(error).__name__}: {error}", file=sys.stderr
        )
    finally:
        if api is not None:
            api.stop()
            if failed:
                print(f"\nThe API's log (last lines):\n{api.tail()}", file=sys.stderr)
        try:
            compose("down", "--remove-orphans")
        except CheckError as error:
            print(f"Could not stop nginx: {error}", file=sys.stderr)
        if url is not None and db_started is not None:
            try:
                asyncio.run(clean_up_database(url, tenant_ids, db_started))
            except Exception as error:
                print(
                    f"Could not clean up the database ({type(error).__name__}: {error}). "
                    f"Sandbox(es) {tenant_ids} and their daily ledger rows may be left.",
                    file=sys.stderr,
                )
    if failed:
        return 1
    print(f"\nProxy check passed in {time.monotonic() - started_at:.0f} s.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
