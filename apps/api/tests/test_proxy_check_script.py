"""The proxy check's own judgment, on recorded timelines. No Docker, no API, no network.

`scripts/proxy-check/check.py` runs the stream through nginx; this proves that what it concludes
from what it saw is right, including that each way a proxy can spoil a stream is caught.
"""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "proxy-check" / "check.py"


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("proxy_check_script", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check = load_script()


def event(at: float, name: str = "text.delta") -> object:
    return check.Mark(at, "event", name)


def comment(at: float) -> object:
    return check.Mark(at, "comment", "")


def timeline(marks: list[object], **changes: object) -> object:
    fields: dict[str, object] = {
        "status": 200,
        "content_encoding": None,
        "marks": tuple(marks),
        "ended_cleanly": True,
        "total_seconds": marks[-1].at_seconds if marks else 0.0,  # type: ignore[attr-defined]
    }
    fields.update(changes)
    return check.Timeline(**fields)


def good_pass() -> list[object]:
    """The silence scenario as it should look: it starts at once, a heartbeat every 15 seconds,
    then the answer."""
    return [
        event(0.1, "turn.started"),
        event(0.3, "status"),
        comment(15.4),
        comment(30.4),
        comment(45.4),
        event(45.6, "text.delta"),
        event(45.7, "turn.completed"),
    ]


# --- The pass run -------------------------------------------------------------------------


def test_a_stream_that_arrives_over_time_and_completes_passes() -> None:
    assert check.problems_in_pass_run(timeline(good_pass())) == []


def test_a_cut_stream_fails() -> None:
    marks = [event(0.1, "turn.started"), comment(15.4)]
    problems = check.problems_in_pass_run(timeline(marks, ended_cleanly=False, total_seconds=20.1))
    assert any("turn.completed" in problem for problem in problems)


def test_a_stream_that_ends_without_turn_completed_fails() -> None:
    marks = good_pass()[:-1]
    assert any("turn.completed" in p for p in check.problems_in_pass_run(timeline(marks)))


def test_one_burst_at_the_end_fails() -> None:
    """A proxy that buffers the whole response: nothing for 45 seconds, then everything."""
    marks = [event(45.6, "turn.started"), event(45.6), event(45.7, "turn.completed")]
    problems = check.problems_in_pass_run(timeline(marks))
    assert any("first event" in problem for problem in problems)
    assert any("spread" in problem or "burst" in problem for problem in problems)


def test_a_late_first_event_fails_even_when_the_rest_is_spread_out() -> None:
    marks = [event(3.0, "turn.started"), *good_pass()[1:]]
    problems = check.problems_in_pass_run(timeline(marks))
    assert any("first event" in problem for problem in problems)


def test_events_close_together_but_no_heartbeats_fail() -> None:
    """The first event is on time, then everything arrives together at the end."""
    marks = [event(0.1, "turn.started"), event(45.6), event(45.7, "turn.completed")]
    problems = check.problems_in_pass_run(timeline(marks))
    assert any("keep-alive" in problem for problem in problems)


def test_compression_fails() -> None:
    problems = check.problems_in_pass_run(timeline(good_pass(), content_encoding="gzip"))
    assert any("Content-Encoding" in problem for problem in problems)


def test_an_identity_encoding_is_no_compression() -> None:
    """`Content-Encoding: identity` is how the app tells a compressing proxy to leave it alone."""
    assert check.problems_in_pass_run(timeline(good_pass(), content_encoding="identity")) == []


def test_a_non_200_status_fails() -> None:
    problems = check.problems_in_pass_run(timeline([event(0.1, "error")], status=502))
    assert any("502" in problem for problem in problems)


# --- The control run ----------------------------------------------------------------------


def test_the_control_run_passes_when_nginx_cuts_the_silent_stream_near_20_seconds() -> None:
    marks = [event(0.1, "turn.started"), event(0.3, "status")]
    cut = timeline(marks, ended_cleanly=False, total_seconds=20.3)
    assert check.problems_in_control_run(cut) == []


def test_the_control_run_fails_when_the_stream_completes() -> None:
    """Then the check could not tell a broken proxy from a working one."""
    marks = [event(0.1, "turn.started"), event(20.0, "turn.completed")]
    assert check.problems_in_control_run(timeline(marks, total_seconds=20.0))


def test_the_control_run_fails_when_the_stream_is_cut_at_the_wrong_time() -> None:
    marks = [event(0.1, "turn.started")]
    early = timeline(marks, ended_cleanly=False, total_seconds=2.0)
    late = timeline(marks, ended_cleanly=False, total_seconds=44.0)
    assert check.problems_in_control_run(early)
    assert check.problems_in_control_run(late)


# --- Reading the wire ---------------------------------------------------------------------


def test_the_reader_marks_events_and_comments_when_each_is_complete() -> None:
    reader = check.StreamReader()
    assert reader.feed('event: turn.started\ndata: {"a":1}\n\n: keep-al', at=1.0) == [
        check.Mark(1.0, "event", "turn.started")
    ]
    assert reader.feed("ive\n\nevent: status\ndata: {}\n\n", at=16.0) == [
        check.Mark(16.0, "comment", ""),
        check.Mark(16.0, "event", "status"),
    ]


# --- The buffering control ----------------------------------------------------------------


def test_the_buffering_control_passes_when_the_gzipping_proxy_holds_the_keep_alives() -> None:
    """Compressed bytes arrive but nothing readable: no keep-alive in the listening time."""
    held = timeline([], content_encoding="gzip", ended_cleanly=False, total_seconds=5.0)
    assert check.problems_in_buffering_control(held) == []


def test_the_buffering_control_fails_when_the_keep_alives_still_arrive_on_time() -> None:
    """Then a holding proxy would not have failed the pass run's keep-alive timing check."""
    marks = [event(0.1, "turn.started"), comment(1.0), comment(2.0), comment(3.0)]
    problems = check.problems_in_buffering_control(
        timeline(marks, content_encoding="gzip", ended_cleanly=False, total_seconds=5.0)
    )
    assert any("holds the stream back" in problem for problem in problems)


def test_the_buffering_control_ignores_keep_alives_after_the_listening_time() -> None:
    marks = [event(0.1, "turn.started"), comment(5.5), comment(6.5)]
    held = timeline(marks, content_encoding="gzip", total_seconds=7.0)
    assert check.problems_in_buffering_control(held) == []


def test_the_normal_proxy_reference_needs_keep_alives_in_the_listening_time() -> None:
    on_time = [event(0.1, "turn.started"), comment(1.0), comment(2.0)]
    assert check.problems_in_buffering_reference(timeline(on_time, total_seconds=5.0)) == []
    late = [event(0.1, "turn.started"), comment(5.5), comment(6.5)]
    assert check.problems_in_buffering_reference(timeline(late, total_seconds=7.0))
    assert check.problems_in_buffering_reference(timeline([comment(1.0)], total_seconds=5.0))


# --- What a buffering proxy does to the pass run -------------------------------------------


def test_a_buffering_proxy_fails_the_pass_run_even_though_the_first_chunk_gets_through() -> None:
    """The first event arrives at once with the headers, then everything else, the keep-alives
    too, arrives together when the stream ends."""
    marks = [
        event(0.1, "turn.started"),
        comment(45.5),
        comment(45.5),
        comment(45.5),
        event(45.6, "text.delta"),
        event(45.7, "turn.completed"),
    ]
    problems = check.problems_in_pass_run(timeline(marks))
    assert any("keep-alive" in problem for problem in problems)


# --- The shutdown run ---------------------------------------------------------------------


def test_the_shutdown_run_passes_on_exit_code_0_and_a_stopped_turn() -> None:
    assert check.problems_in_shutdown_run(exit_code=0, turn_statuses=["stopped"]) == []


def test_the_shutdown_run_accepts_uvicorn_ending_by_sigterm_after_a_clean_shutdown() -> None:
    assert check.problems_in_shutdown_run(exit_code=-15, turn_statuses=["stopped"]) == []


def test_the_shutdown_run_fails_on_a_crash_or_a_kill() -> None:
    for code in (1, -9, None):
        problems = check.problems_in_shutdown_run(exit_code=code, turn_statuses=["stopped"])
        assert any("exit code" in problem for problem in problems)


def test_the_shutdown_run_fails_when_the_turn_is_not_stopped() -> None:
    assert check.problems_in_shutdown_run(exit_code=0, turn_statuses=["running"])
    assert check.problems_in_shutdown_run(exit_code=0, turn_statuses=[])


# --- Where the API listens ----------------------------------------------------------------


def test_the_api_binds_to_loopback_on_macos() -> None:
    assert check.bind_host_for("darwin", override=None, bridge_gateway=None) == "127.0.0.1"


def test_the_api_binds_to_the_docker_bridge_gateway_on_linux() -> None:
    assert check.bind_host_for("linux", override=None, bridge_gateway="172.17.0.1") == "172.17.0.1"


def test_an_override_wins_on_any_platform() -> None:
    assert (
        check.bind_host_for("linux", override="10.0.0.5", bridge_gateway="172.17.0.1") == "10.0.0.5"
    )
    assert check.bind_host_for("darwin", override="10.0.0.5", bridge_gateway=None) == "10.0.0.5"


def test_linux_without_a_bridge_gateway_is_an_error_not_a_wide_open_bind() -> None:
    with pytest.raises(check.CheckError, match="PROXY_CHECK_BIND"):
        check.bind_host_for("linux", override=None, bridge_gateway=None)
