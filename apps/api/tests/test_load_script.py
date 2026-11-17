"""The load test's pieces (`scripts/load/drive.py`): the stream parser, the percentiles, the
visitors' addresses, the API container's settings, the stats parsing, the report, and the
saturation rule. No Docker and no network."""

import asyncio
import importlib.util
import ipaddress
import json
import random
import re
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from types import ModuleType
from typing import Any

import httpx
import pytest

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "load" / "drive.py"
TOUR_SCRIPT = REPO / "apps" / "web" / "src" / "features" / "tour" / "script.ts"


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("load_drive_script", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


drive = load_script()
container = drive.container

DB_URL = "postgresql+asyncpg://od_app_login:secret@db:5432/opendoor"


def env_for(**overrides: object) -> dict[str, str]:
    values: dict[str, object] = {
        "origin": "http://127.0.0.1:8400",
        "port": 8400,
        "database_url": DB_URL,
        "forwarded": "172.18.0.1",
        "real_caps": False,
    }
    values.update(overrides)
    result: dict[str, str] = drive.api_env(**values)
    return result


# --- The event stream ---------------------------------------------------------------------------


def test_the_parser_reads_events_with_their_data() -> None:
    parser = drive.SseParser()
    events = parser.feed('event: turn.started\ndata: {"turnId":"t1"}\n\n')
    assert [(e.name, e.data) for e in events] == [("turn.started", {"turnId": "t1"})]


def test_the_parser_counts_comments_and_ignores_them() -> None:
    parser = drive.SseParser()
    assert parser.feed(": keep-alive\n\n") == []
    assert parser.comments == 1


def test_the_parser_joins_an_event_split_across_chunks() -> None:
    parser = drive.SseParser()
    assert parser.feed("event: text.delta\nda") == []
    assert parser.feed('ta: {"text":"Ab') == []
    events = parser.feed('c"}\n\nevent: turn.comp')
    assert [e.data for e in events] == [{"text": "Abc"}]
    events = parser.feed('leted\ndata: {"turnId":"t1"}\n\n')
    assert [e.name for e in events] == ["turn.completed"]


def test_the_parser_gives_several_events_in_one_chunk_in_order() -> None:
    parser = drive.SseParser()
    chunk = (
        'event: turn.started\ndata: {}\n\nevent: text.delta\ndata: {"text":"a"}\n\n'
        'event: turn.completed\ndata: {"turnId":"t"}\n\n'
    )
    assert [e.name for e in parser.feed(chunk)] == ["turn.started", "text.delta", "turn.completed"]


def test_only_a_completed_or_error_event_closes_a_stream() -> None:
    assert drive.is_closing_event("turn.completed")
    assert drive.is_closing_event("error")
    assert not drive.is_closing_event("text.delta")
    assert not drive.is_closing_event("escalation")


# --- Numbers ------------------------------------------------------------------------------------


def test_percentiles_interpolate_and_handle_small_samples() -> None:
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert drive.percentile(values, 0.5) == 3.0
    assert drive.percentile(values, 0.95) == pytest.approx(4.8)
    assert drive.percentile(values, 1.0) == 5.0
    assert drive.percentile([7.0], 0.95) == 7.0
    assert drive.percentile([], 0.5) is None


def test_a_summary_has_the_count_and_p50_p95_max_in_milliseconds() -> None:
    summary = drive.summarize([0.1, 0.2, 0.3])
    assert summary == {"count": 3, "p50Ms": 200.0, "p95Ms": 290.0, "maxMs": 300.0}
    assert drive.summarize([]) == {"count": 0, "p50Ms": None, "p95Ms": None, "maxMs": None}


# --- Addresses ----------------------------------------------------------------------------------


def test_each_visitor_gets_its_own_address_from_the_benchmarking_range() -> None:
    book = drive.AddressBook()
    addresses = [book.next() for _ in range(5000)]
    assert len(set(addresses)) == 5000
    network = ipaddress.ip_network("198.18.0.0/15")
    assert all(ipaddress.ip_address(a) in network for a in addresses)


def test_the_address_book_never_repeats_across_runs_and_refuses_to_run_out() -> None:
    book = drive.AddressBook()
    first = [book.next() for _ in range(3)]
    second = [book.next() for _ in range(3)]
    assert not set(first) & set(second)
    book = drive.AddressBook(size=2)
    book.next()
    book.next()
    with pytest.raises(RuntimeError):
        book.next()


# --- The API container's settings ---------------------------------------------------------------


def test_the_api_runs_the_scripted_model_at_the_realistic_pace_in_test_mode() -> None:
    env = env_for()
    assert env["APP_ENV"] == "test"
    assert env["AI_TRANSPORT"] == "scripted"
    assert env["SCRIPTED_DELAY_PROFILE"] == "realistic"
    assert env["APP_ORIGIN"] == "http://127.0.0.1:8400"
    assert env["PORT"] == "8400"
    assert env["DATABASE_URL"] == DB_URL
    assert env["ENCRYPTION_KEYRING"]


def test_the_api_has_the_real_start_limits_not_the_test_images_million() -> None:
    env = env_for()
    assert env["SANDBOX_STARTS_PER_HOUR"] == "5"
    assert env["SANDBOX_STARTS_PER_DAY"] == "20"
    assert env["SANDBOX_STARTS_DAILY_TOTAL"] == "500"


def test_the_matrix_runs_with_ai_caps_that_never_bind() -> None:
    """Scripted turns still reserve at the real model's rates, and a long conversation's
    reservation grows with its history, so neither cap may end a size run."""
    env = env_for()
    assert env["AI_DAILY_BUDGET_USD"] == "1000"
    assert env["AI_SANDBOX_BUDGET_USD"] == "1000"


def test_a_long_conversation_run_lifts_only_the_days_start_total() -> None:
    """Its tour slots start tour after tour on one database per size, so the day's 500 would end
    the later runs; the per-address limits stay (each tour has its own address)."""
    env = env_for(long_conversation=True)
    assert env["SANDBOX_STARTS_DAILY_TOTAL"] == "1000000"
    assert env["SANDBOX_STARTS_PER_HOUR"] == "5"
    assert env["SANDBOX_STARTS_PER_DAY"] == "20"
    assert env_for()["SANDBOX_STARTS_DAILY_TOTAL"] == "500"


def test_the_real_caps_run_uses_the_real_ai_limits() -> None:
    env = env_for(real_caps=True)
    assert env["AI_SANDBOX_BUDGET_USD"] == "1"
    assert env["AI_DAILY_BUDGET_USD"] == "3"
    assert env["SANDBOX_STARTS_PER_DAY"] == "20"


def test_the_trusted_proxy_is_exactly_the_address_given() -> None:
    assert env_for(forwarded="172.18.0.1")["FORWARDED_ALLOW_IPS"] == "172.18.0.1"
    # The probe run trusts nobody.
    assert env_for(forwarded="")["FORWARDED_ALLOW_IPS"] == ""


@pytest.mark.parametrize("real_caps", [False, True])
def test_no_run_uses_a_production_value_or_a_paid_key(real_caps: bool) -> None:
    env = env_for(real_caps=real_caps)
    assert env["APP_ENV"] != "production"
    assert env["AI_TRANSPORT"] != "anthropic"
    assert not {"ANTHROPIC_API_KEY", "VOYAGE_API_KEY"} & set(env)
    assert "MIGRATION_DATABASE_URL" not in env
    assert "CLEANUP_DATABASE_URL" not in env


def test_the_api_container_is_limited_and_joins_the_private_network() -> None:
    size = drive.Size(cpus="0.5", memory="1g")
    args = drive.api_run_args(env_for(), port=8400, size=size)
    assert args[args.index("--cpus") + 1] == "0.5"
    assert args[args.index("--memory") + 1] == "1g"
    assert args[args.index("--network") + 1] == drive.NETWORK
    assert args[args.index("--publish") + 1] == "127.0.0.1:8400:8400"
    assert args[-1] == container.PROD_TAG
    # No secret on the command line: each setting is `--env KEY`.
    assert "secret" not in " ".join(args)


def test_the_database_is_private_limited_and_never_published() -> None:
    args = drive.database_args({"POSTGRES_PASSWORD": "pw"})
    assert args[args.index("--cpus") + 1] == "2"
    assert args[args.index("--memory") + 1] == "4g"
    assert "--publish" not in args
    assert "-p" not in args
    assert args[-1] == container.POSTGRES_IMAGE
    assert "pw" not in " ".join(args)


def test_fresh_passwords_every_time() -> None:
    first, second = drive.Passwords.new(), drive.Passwords.new()
    assert first != second
    assert len({first.owner, first.app, first.cleanup}) == 3


# --- Sizes and counts ---------------------------------------------------------------------------


def test_sizes_and_visitor_counts_parse() -> None:
    assert drive.parse_sizes("0.5:1g,1:2g") == [
        drive.Size("0.5", "1g"),
        drive.Size("1", "2g"),
    ]
    assert drive.parse_visitors("10,25,50") == [10, 25, 50]
    with pytest.raises(ValueError, match="size"):
        drive.parse_sizes("1")
    with pytest.raises(ValueError, match="visitor"):
        drive.parse_visitors("0")


def test_the_plan_runs_the_matrix_then_one_real_caps_run_on_a_fresh_database() -> None:
    sizes = drive.parse_sizes("0.5:1g,1:2g")
    plan = drive.make_plan(sizes, [10, 25], real_caps_run=True, real_caps_visitors=25)
    assert [(p.size.label, p.visitors, p.real_caps) for p in plan] == [
        ("0.5cpu-1g", 10, False),
        ("0.5cpu-1g", 25, False),
        ("1cpu-2g", 10, False),
        ("1cpu-2g", 25, False),
        ("1cpu-2g", 25, True),
    ]
    without = drive.make_plan(sizes, [10], real_caps_run=False, real_caps_visitors=25)
    assert not any(p.real_caps for p in without)


def test_report_names_say_the_size_the_count_and_the_caps() -> None:
    size = drive.Size("1", "2g")
    assert drive.report_name(size, 25, real_caps=False) == "1cpu-2g-25v.json"
    assert drive.report_name(size, 25, real_caps=True) == "1cpu-2g-25v-realcaps.json"
    assert (
        drive.report_name(size, 25, real_caps=False, long_conversation=50)
        == "1cpu-2g-25v-long50.json"
    )


def test_the_long_conversation_has_its_own_turn_by_turn_section() -> None:
    long_metrics = drive.Metrics()
    long_metrics.add_turn(position=1, started=0.1, first_text=1.0, total=4.0)
    long_metrics.add_turn(position=2, started=0.3, first_text=1.2, total=5.0)
    long_metrics.add_route("GET /api/v1/assistant/conversations/current", 0.02, 200)
    long_metrics.visitors_completed = 1
    report = drive.build_report(
        size=drive.Size("0.5", "1g"),
        visitors=25,
        real_caps=False,
        wall_seconds=1.0,
        metrics=drive.Metrics(),
        samples=drive.Samples(),
        log_found={},
        baseline_turn_p95_ms=None,
        long_metrics=long_metrics,
        long_questions=2,
    )
    long = report["longConversation"]
    assert long["questions"] == 2
    assert long["turnsAsked"] == 2
    assert long["completed"] is True
    assert long["turnStartedMsByPosition"] == {"1": 100.0, "2": 300.0}
    assert long["turnMsByPosition"] == {"1": 4000.0, "2": 5000.0}
    assert "GET /api/v1/assistant/conversations/current" in long["routes"]
    assert report["turn"]["count"] == 0  # the tour's numbers stay apart
    assert "long=2/2" in drive.summary_line(report)
    assert "longStartedLast=300" in drive.summary_line(report)
    plain = drive.build_report(
        size=drive.Size("0.5", "1g"),
        visitors=25,
        real_caps=False,
        wall_seconds=1.0,
        metrics=drive.Metrics(),
        samples=drive.Samples(),
        log_found={},
        baseline_turn_p95_ms=None,
    )
    assert "longConversation" not in plain


def test_the_long_conversation_alternates_a_search_and_a_card() -> None:
    assert drive.LONG_QUESTIONS == (drive.SICK_DAYS, drive.BOOK_FRIDAY)


def test_a_negative_long_conversation_is_refused(capsys: pytest.CaptureFixture[str]) -> None:
    assert drive.main(["--long-conversation", "-1"]) == 1
    assert "--long-conversation" in capsys.readouterr().err


# --- Reading the machine ------------------------------------------------------------------------


STATS = (
    '{"Name":"open-door-load-api","CPUPerc":"48.25%","MemUsage":"312.4MiB / 1GiB"}\n'
    '{"Name":"open-door-load-db","CPUPerc":"3.10%","MemUsage":"1.5GiB / 4GiB"}\n'
)


def test_docker_stats_lines_become_cpu_and_memory_per_container() -> None:
    stats = drive.parse_docker_stats(STATS)
    assert stats["open-door-load-api"].cpu_percent == 48.25
    assert stats["open-door-load-api"].memory_mb == pytest.approx(312.4)
    assert stats["open-door-load-db"].memory_mb == pytest.approx(1536.0)


@pytest.mark.parametrize(
    ("text", "megabytes"),
    [("512KiB", 0.5), ("2MiB", 2.0), ("1GiB", 1024.0), ("1.5GB", 1500.0), ("10MB", 10.0)],
)
def test_memory_sizes_in_every_unit_docker_prints(text: str, megabytes: float) -> None:
    assert drive.parse_memory_mb(text) == pytest.approx(megabytes)


def test_stats_with_junk_lines_are_skipped() -> None:
    assert drive.parse_docker_stats("\n--\nnot json\n") == {}


def test_cpu_as_a_fraction_of_the_limit() -> None:
    assert drive.cpu_fraction_of_limit(50.0, "0.5") == pytest.approx(1.0)
    assert drive.cpu_fraction_of_limit(50.0, "1") == pytest.approx(0.5)


def test_connections_by_state() -> None:
    assert drive.parse_connections("active,3\nidle,7\nidle in transaction,1\n") == {
        "active": 3,
        "idle": 7,
        "idle in transaction": 1,
    }
    assert drive.parse_connections("") == {}


def test_log_problems_are_counted_by_kind() -> None:
    log = (
        "sqlalchemy.exc.TimeoutError: QueuePool limit of size 5 overflow 10 reached\n"
        "Traceback (most recent call last):\n"
        "Traceback (most recent call last):\n"
        '{"detail":"database-busy"}\n'
        "INFO: all fine\n"
    )
    found = drive.log_problems(log)
    assert found == {"QueuePool limit": 1, "TimeoutError": 1, "database-busy": 1, "Traceback": 2}
    assert drive.pool_timeouts_in(found) == 3


# --- Saturation ---------------------------------------------------------------------------------


def reasons(**overrides: object) -> list[str]:
    values: dict[str, object] = {
        "cpu_fractions": [0.4] * 10,
        "turn_p95_ms": 5000.0,
        "baseline_turn_p95_ms": 5000.0,
        "server_errors": 0,
        "pool_timeouts": 0,
        "client_errors": 0,
        "visitors_failed": 0,
    }
    values.update(overrides)
    result: list[str] = drive.saturation_reasons(**values)
    return result


def test_a_calm_run_is_not_saturated() -> None:
    assert reasons() == []


def test_a_sustained_stretch_at_the_cpu_limit_saturates() -> None:
    assert reasons(cpu_fractions=[0.2, 0.97, 0.99, 1.0, 0.3])
    # One spike is not sustained.
    assert not reasons(cpu_fractions=[0.2, 0.99, 0.2, 0.99, 0.2])


def test_a_turn_p95_more_than_half_again_above_the_baseline_saturates() -> None:
    assert reasons(turn_p95_ms=7600.0)
    assert not reasons(turn_p95_ms=7400.0)
    assert not reasons(turn_p95_ms=99999.0, baseline_turn_p95_ms=None)


def test_any_server_error_or_pool_timeout_saturates() -> None:
    assert reasons(server_errors=1)
    assert reasons(pool_timeouts=1)


# --- The report ---------------------------------------------------------------------------------


def test_the_report_has_the_measurements_the_brief_asks_for() -> None:
    metrics = drive.Metrics()
    metrics.add_route("GET /api/v1/me", 0.05, 200)
    metrics.add_route("GET /api/v1/time-off/requests?scope=waiting", 0.2, 200)
    metrics.add_route("POST /api/v1/sandboxes", 0.3, 201)
    metrics.add_route("POST /api/v1/sandboxes", 0.0, 429, code="sandbox-start-limit")
    metrics.add_turn(position=1, started=0.1, first_text=1.5, total=4.0)
    metrics.add_turn(position=2, started=0.2, first_text=1.6, total=5.0)
    metrics.add_stream_error("budget-daily")
    metrics.visitors_completed = 2
    samples = drive.Samples()
    samples.add(
        {
            "api": drive.Stats(cpu_percent=50.0, memory_mb=300.0),
            "db": drive.Stats(cpu_percent=10.0, memory_mb=900.0),
        },
        {"active": 2, "idle": 3},
    )
    report = drive.build_report(
        size=drive.Size("1", "2g"),
        visitors=2,
        real_caps=False,
        wall_seconds=12.3,
        metrics=metrics,
        samples=samples,
        log_found={"Traceback": 0},
        baseline_turn_p95_ms=None,
    )
    assert report["size"] == {"cpus": "1", "memory": "2g"}
    assert report["visitors"] == {"started": 2, "tours": 0, "completed": 2, "failed": 0}
    assert report["wallSeconds"] == 12.3
    assert report["turn"]["count"] == 2
    assert report["turnStarted"]["count"] == 2
    assert report["firstTextDelta"]["p50Ms"] == pytest.approx(1550.0)
    assert set(report["turnStartedByPosition"]) == {"1", "2"}
    assert report["sandboxCreation"]["count"] == 1
    assert "GET /api/v1/time-off/requests?scope=waiting" in report["routes"]
    assert report["errors"]["statusCounts"] == {"200": 2, "201": 1, "429": 1}
    assert report["errors"]["codes"] == {
        "sandbox-start-limit": 1,
        "stream-error:budget-daily": 1,
    }
    assert report["resources"]["api"]["cpuPercent"]["max"] == 50.0
    assert report["resources"]["api"]["cpuOfLimit"]["max"] == pytest.approx(0.5)
    assert report["resources"]["db"]["memoryMb"]["max"] == 900.0
    assert report["resources"]["appConnections"]["maxTotal"] == 5
    assert report["resources"]["appConnections"]["maxByState"] == {"active": 2, "idle": 3}
    assert report["apiLogProblems"] == {"Traceback": 0}
    assert report["saturated"] is False
    assert json.loads(json.dumps(report)) == report  # plain JSON


def test_the_summary_line_is_one_readable_line() -> None:
    report = {
        "size": {"cpus": "1", "memory": "2g"},
        "visitors": {"started": 10, "completed": 10, "failed": 0},
        "realCaps": False,
        "wallSeconds": 190.4,
        "turn": {"count": 90, "p50Ms": 4000.0, "p95Ms": 7000.0, "maxMs": 9000.0},
        "turnStarted": {"count": 90, "p50Ms": 50.0, "p95Ms": 90.0, "maxMs": 200.0},
        "errors": {"statusCounts": {"200": 5, "500": 1}, "codes": {}},
        "resources": {"api": {"cpuOfLimit": {"max": 0.8, "mean": 0.4}}},
        "saturated": True,
        "saturationReasons": ["server-errors: 1"],
    }
    line = drive.summary_line(report)
    assert "\n" not in line
    assert line.startswith("LOAD RUN END ")
    assert "1cpu-2g" in line
    assert "visitors=10/10" in line
    assert "saturated=yes" in line


# --- Cookies and the visitor's script -----------------------------------------------------------


def test_cookies_are_read_from_set_cookie_headers() -> None:
    headers = [
        "__Host-od_session=abc; Path=/; Secure; HttpOnly; SameSite=Lax",
        "__Host-od_csrf=def; Path=/; Secure; SameSite=Lax",
    ]
    assert drive.cookie_values(headers) == {"__Host-od_session": "abc", "__Host-od_csrf": "def"}


def test_a_session_sends_both_cookies_and_the_csrf_header() -> None:
    session = drive.Session(
        cookie_header="__Host-od_session=abc; __Host-od_csrf=def", csrf="def", tenant_id="t"
    )
    headers = session.headers(origin="http://127.0.0.1:8400", address="198.18.0.1")
    assert headers["Cookie"] == "__Host-od_session=abc; __Host-od_csrf=def"
    assert headers["X-CSRF-Token"] == "def"
    assert headers["X-Forwarded-For"] == "198.18.0.1"


def test_the_visitors_questions_are_the_tours_chips_curly_apostrophes_included() -> None:
    tour = TOUR_SCRIPT.read_text(encoding="utf-8")
    chips = {
        c
        for group in re.findall(r"chips: \[([^\]]*)\]", tour)
        for c in re.findall(r"'([^']*)'", group)
    }
    assert chips
    assert set(drive.TOUR_QUESTIONS) == chips


def test_the_tour_asks_in_the_tours_order() -> None:
    steps = [(step.persona, step.question) for step in drive.QUESTION_STEPS]
    assert steps[0] == ("priya", "How many sick days do I get?")
    assert [persona for persona, _ in steps] == [
        "priya", "priya", "mateo", "marcus", "marcus", "marcus", "priya", "priya", "priya",
    ]  # fmt: skip
    assert all(chr(0x2014) not in question for _, question in steps)


# --- The review's fixes -------------------------------------------------------------------------


def test_on_linux_the_api_binds_every_interface_of_its_bridged_container() -> None:
    """The API is on the load test's own network with a published port, not the host's network,
    so binding the container's loopback would leave the published port unanswered."""
    assert env_for(platform="linux")["HOST"] == "0.0.0.0"  # noqa: S104
    assert "HOST" not in env_for(platform="darwin")


def test_the_plan_runs_each_sizes_smallest_count_first() -> None:
    """The first run of a size is the saturation baseline, so it must be the smallest."""
    sizes = drive.parse_sizes("1:2g")
    plan = drive.make_plan(sizes, [50, 10, 25], real_caps_run=False, real_caps_visitors=25)
    assert [p.visitors for p in plan] == [10, 25, 50]


def _visitor(handler: Any) -> tuple[Any, Any]:
    metrics = drive.Metrics()
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    visitor = drive.Visitor(
        index=0,
        client=client,
        base="http://api.test",
        address="198.18.0.1",
        metrics=metrics,
        rng=random.Random(1),  # noqa: S311
        reading_seconds=(0.0, 0.0),
    )
    return visitor, metrics


async def test_a_turn_with_no_response_is_a_client_error_not_a_200() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    visitor, metrics = _visitor(refuse)
    visitor.conversation_id = "c1"
    turn = await visitor.ask(drive.Ask("priya", drive.SICK_DAYS))
    await visitor.client.aclose()
    assert turn.status == 0
    assert "200" not in metrics.statuses
    assert metrics.turn == []
    assert metrics.codes["client:ConnectError"] == 1
    assert metrics.notes["turn-no-response"] == 1


async def test_a_current_conversation_read_that_isnt_json_costs_one_read() -> None:
    def page(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/conversations/current"):
            return httpx.Response(200, text="<html>busy</html>")
        return httpx.Response(200, json={})

    visitor, metrics = _visitor(page)
    await visitor.open_ask_page()
    await visitor.client.aclose()
    assert metrics.notes["current-not-json"] == 1
    assert metrics.visitors_failed == 0


def test_requests_with_no_answer_and_crashed_visitors_saturate_a_run() -> None:
    """A task that stops accepting connections leaves no status at all: the client's errors and
    the visitors that fell over must still mark the run."""
    assert reasons(client_errors=3) == ["client-errors: 3"]
    assert reasons(visitors_failed=2) == ["visitors-failed: 2"]


async def test_a_stream_cut_after_its_header_is_not_a_finished_turn() -> None:
    def cut(request: httpx.Request) -> httpx.Response:
        class Broken(httpx.AsyncByteStream):
            async def __aiter__(self) -> AsyncIterator[bytes]:
                yield b'event: turn.started\ndata: {"turnId": "t1"}\n\n'
                raise httpx.ReadError("cut", request=request)

        if request.url.path.endswith("/turns"):
            return httpx.Response(200, stream=Broken())
        return httpx.Response(200, json=None)

    visitor, metrics = _visitor(cut)
    visitor.conversation_id = "c1"
    await visitor.ask(drive.Ask("priya", drive.SICK_DAYS))
    await visitor.client.aclose()
    assert metrics.turn == []
    assert "POST /api/v1/assistant/conversations/{id}/turns" not in metrics.routes
    assert metrics.codes["client:ReadError"] == 1
    assert metrics.notes["stream-cut"] == 1


async def test_a_visitor_whose_sandbox_never_starts_is_not_completed() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"type": "sandbox-start-limit"})

    visitor, _metrics = _visitor(refuse)
    assert await visitor.run() is False
    assert await visitor.run_long(3) is False
    await visitor.client.aclose()


def test_a_long_conversation_stopped_early_is_not_completed() -> None:
    metrics = drive.Metrics()
    metrics.add_turn(position=1, started=0.1, first_text=1.0, total=4.0)
    metrics.visitors_completed = 0
    long = drive.long_report(metrics, questions=50)
    assert long["completed"] is False
    assert long["turnsAsked"] == 1


def test_the_report_counts_the_tours_run_apart_from_the_slots() -> None:
    metrics = drive.Metrics()
    metrics.tours_started = 5
    metrics.visitors_completed = 4
    metrics.visitors_failed = 1
    report = drive.build_report(
        size=drive.Size("0.5", "1g"),
        visitors=2,
        real_caps=False,
        wall_seconds=1.0,
        metrics=metrics,
        samples=drive.Samples(),
        log_found={},
        baseline_turn_p95_ms=None,
    )
    assert report["visitors"] == {"started": 2, "tours": 5, "completed": 4, "failed": 1}
    assert "visitors=4/5" in drive.summary_line(report)


async def test_a_tour_slot_that_cant_start_stops_instead_of_retrying_at_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With a long conversation the slots begin tour after tour; one whose tour never got a
    sandbox must stop, not send start after start until the conversation ends."""
    tours = {"count": 0}

    async def no_sandbox(self: Any) -> bool:
        tours["count"] += 1
        await asyncio.sleep(0)  # Yield, so a retrying slot can't starve the long conversation.
        return False

    async def long_one(self: Any, questions: int) -> bool:
        await asyncio.sleep(0.05)
        return True

    monkeypatch.setattr(drive.Visitor, "run", no_sandbox)
    monkeypatch.setattr(drive.Visitor, "run_long", long_one)
    metrics, long_metrics = drive.Metrics(), drive.Metrics()
    await drive.run_visitors(
        count=2,
        base="http://api.test",
        addresses=drive.AddressBook(),
        metrics=metrics,
        seed=1,
        ramp_seconds=0.0,
        long_conversation=3,
        long_metrics=long_metrics,
    )
    assert tours["count"] == 2
    assert metrics.visitors_failed == 2


async def test_a_stream_that_ends_with_no_closing_event_is_not_a_finished_turn() -> None:
    def unclosed(request: httpx.Request) -> httpx.Response:
        class Unclosed(httpx.AsyncByteStream):
            async def __aiter__(self) -> AsyncIterator[bytes]:
                yield b'event: turn.started\ndata: {"turnId": "t1"}\n\n'

        if request.url.path.endswith("/turns"):
            return httpx.Response(200, stream=Unclosed())
        return httpx.Response(200, json=None)

    visitor, metrics = _visitor(unclosed)
    visitor.conversation_id = "c1"
    await visitor.ask(drive.Ask("priya", drive.SICK_DAYS))
    await visitor.client.aclose()
    assert metrics.turn == []
    assert metrics.notes["stream-closings-0"] == 1
    assert metrics.client_errors == 1


async def test_a_sandbox_answer_without_a_tenant_is_a_start_that_failed() -> None:
    def no_tenant(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"tenant": None})

    visitor, _metrics = _visitor(no_tenant)
    assert await visitor.start_sandbox("priya") is False
    await visitor.client.aclose()


async def test_an_error_body_without_a_type_is_counted_by_its_status() -> None:
    def plain(request: httpx.Request) -> httpx.Response:
        return httpx.Response(405, json={"detail": "Method Not Allowed"})

    visitor, metrics = _visitor(plain)
    await visitor.call("GET", "/api/v1/me")
    await visitor.client.aclose()
    assert metrics.codes == {"http-405": 1}


async def test_a_card_of_an_unexpected_shape_is_missing_not_a_crash() -> None:
    visitor, metrics = _visitor(lambda request: httpx.Response(200, json={}))
    turn = drive.Turn(status=200, closings=1, cards=[{"card": None}, {"card": {"kind": "request"}}])
    await visitor.preview_and_confirm(
        drive.Ask("priya", drive.BOOK_FRIDAY, confirm="request"), turn
    )
    await visitor.client.aclose()
    assert metrics.notes["card-missing-request"] == 1


def test_a_repeated_visitor_count_runs_once() -> None:
    assert drive.parse_visitors("10,10,25") == [10, 25]
