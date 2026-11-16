"""`make walkthrough`: the recording's launcher (Phase 8, Task 45). No Docker, no model: it judges
the cap, the files a take leaves, and the install step of `scripts/walkthrough/record.py`, and
runs `encode.sh` on a short generated clip when ffmpeg is there."""

import importlib.util
import json
import shutil
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "walkthrough" / "record.py"
ENCODE = REPO / "scripts" / "walkthrough" / "encode.sh"
sys.path.insert(0, str(REPO / "scripts" / "image"))


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("walkthrough_record_script", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


record = load_script()


def test_the_first_take_may_use_the_whole_cap(tmp_path: Path) -> None:
    assert record.spent_usd(tmp_path) == Decimal(0)
    assert record.cap_left_usd(tmp_path, Decimal("2.00")) == Decimal("2.00")


def test_each_take_lowers_what_the_next_may_spend(tmp_path: Path) -> None:
    record.note_take(tmp_path, "take-1", Decimal("0.27"))
    record.note_take(tmp_path, "take-2", Decimal("0.31"))

    assert record.spent_usd(tmp_path) == Decimal("0.58")
    assert record.cap_left_usd(tmp_path, Decimal("2.00")) == Decimal("1.42")


def test_no_take_starts_once_the_cap_is_used(tmp_path: Path) -> None:
    record.note_take(tmp_path, "take-1", Decimal("1.95"))

    with pytest.raises(record.RecordError, match="cap"):
        record.cap_left_usd(tmp_path, Decimal("2.00"))


def test_the_cap_left_is_written_as_the_apps_budgets(tmp_path: Path) -> None:
    record.note_take(tmp_path, "take-1", Decimal("0.25"))

    assert record.budgets_for(Decimal("1.75")) == {"daily": "1.75", "sandbox": "1.75"}
    # Rounded down to the cent, so the app's cap is never above what is left.
    assert record.budgets_for(Decimal("1.756")) == {"daily": "1.75", "sandbox": "1.75"}


def test_the_dry_run_names_no_model_and_the_real_take_the_pinned_one() -> None:
    from app.ai.conversations import CURRENT_PINS

    assert record.model_id(dry_run=True) == "scripted"
    assert record.model_id(dry_run=False) == CURRENT_PINS.model


def test_install_copies_the_three_files_into_the_app(tmp_path: Path) -> None:
    take = tmp_path / "take-1"
    take.mkdir()
    (take / "walkthrough.json").write_text('{"model": "Claude Opus 5.5"}\n')
    (take / "walkthrough.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42")
    (take / "walkthrough-poster.jpg").write_bytes(b"\xff\xd8\xff")
    app = tmp_path / "app"

    record.install(take, web_root=app)

    assert (app / "src/features/walkthrough/walkthrough.json").read_text().startswith('{"model"')
    assert (app / "public/media/walkthrough.mp4").read_bytes().startswith(b"\x00\x00\x00\x18ftyp")
    assert (app / "public/media/walkthrough-poster.jpg").read_bytes() == b"\xff\xd8\xff"


def test_install_refuses_a_dry_run(tmp_path: Path) -> None:
    take = tmp_path / "dry"
    take.mkdir()
    (take / "walkthrough.json").write_text(json.dumps({"model": "Scripted model (dry run)"}))
    (take / "walkthrough.mp4").write_bytes(b"x")
    (take / "walkthrough-poster.jpg").write_bytes(b"x")

    with pytest.raises(record.RecordError, match="dry run"):
        record.install(take, web_root=tmp_path / "app")


def test_install_refuses_a_take_with_a_file_missing(tmp_path: Path) -> None:
    take = tmp_path / "take-1"
    take.mkdir()
    (take / "walkthrough.json").write_text("{}")

    with pytest.raises(record.RecordError, match=r"walkthrough\.mp4"):
        record.install(take, web_root=tmp_path / "app")


def test_the_length_goes_into_the_transcript(tmp_path: Path) -> None:
    (tmp_path / "walkthrough.json").write_text(json.dumps({"durationSeconds": 1, "steps": []}))

    record.set_duration(tmp_path, 151.6)

    assert json.loads((tmp_path / "walkthrough.json").read_text())["durationSeconds"] == 152


def test_a_failed_take_keeps_its_turns_and_the_apis_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Once the take ends the containers are gone, so a failure's cause is saved first."""
    asked: list[object] = []

    def query(sql: str) -> str:
        asked.append(sql)
        return "2026-11-16 15:33:01|failed|model_unavailable|{}"

    def docker(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        asked.append(args)
        return subprocess.CompletedProcess(args, 0, stdout="api out\n", stderr="api err\n")

    monkeypatch.setattr(record.start, "query", query)
    monkeypatch.setattr(record.start, "docker", docker)
    take = tmp_path / "take-1"

    record.save_failure(take)

    assert asked == [record.FAILED_TURNS_SQL, ("logs", record.start.API_NAME)]
    assert "error_code" in record.FAILED_TURNS_SQL
    assert "ciphertext" not in record.FAILED_TURNS_SQL
    assert (take / "turns.txt").read_text() == "2026-11-16 15:33:01|failed|model_unavailable|{}\n"
    assert (take / "api.log").read_text() == "api out\napi err\n"


def test_a_take_notes_what_it_spent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(record.start, "query", lambda sql: "0.231")

    record.settle_take(tmp_path, "take-1", tmp_path / "take-1", Decimal("1.50"), dry_run=False,
                       failed=False)  # fmt: skip

    assert record.spent_usd(tmp_path) == Decimal("0.231")


def test_a_take_whose_spend_cant_be_read_counts_as_the_whole_cap_left(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The cap is never under-counted, and the take's own error isn't replaced by this one."""

    def broken(sql: str) -> str:
        raise record.start.LaunchError("The query failed: no such container")

    monkeypatch.setattr(record.start, "query", broken)
    monkeypatch.setattr(record, "save_failure", broken)

    record.settle_take(tmp_path, "take-1", tmp_path / "take-1", Decimal("1.50"), dry_run=False,
                       failed=True)  # fmt: skip

    assert record.spent_usd(tmp_path) == Decimal("1.50")
    err = capsys.readouterr().err
    assert "noting $1.50" in err
    assert "Couldn't keep the failed take's turns and log" in err


def test_a_dry_run_notes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(record.start, "query", lambda sql: "0")

    record.settle_take(tmp_path, "dry-1", tmp_path / "dry-1", Decimal(1000), dry_run=True,
                       failed=False)  # fmt: skip

    assert record.spent_usd(tmp_path) == Decimal(0)


@pytest.mark.parametrize("missing", ["ffmpeg", "ffprobe"])
def test_a_take_refuses_to_start_without_the_encoding_tools(
    missing: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Checked before the paid part: a take that can't be encoded would be money for nothing."""
    monkeypatch.setattr(record.shutil, "which", lambda tool: None if tool == missing else "/bin/x")

    with pytest.raises(record.RecordError, match=missing):
        record.require_encoding_tools()


def test_a_take_starts_with_the_encoding_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(record.shutil, "which", lambda tool: f"/usr/bin/{tool}")

    record.require_encoding_tools()


def test_the_recorder_labels_a_dry_run_the_way_install_refuses() -> None:
    """Two copies of one label: if they drifted, a dry run could be installed as the recording."""
    recorder = (REPO / "apps" / "web" / "e2e" / "walkthrough" / "record.ts").read_text()

    assert f"'{record.DRY_RUN_MODEL}'" in recorder


def test_a_video_ffprobe_cant_read_is_a_clear_error(tmp_path: Path) -> None:
    if shutil.which("ffprobe") is None:
        pytest.skip("ffprobe is not installed")
    broken = tmp_path / "walkthrough.mp4"
    broken.write_bytes(b"not a video")

    with pytest.raises(record.RecordError, match="couldn't read the video's length"):
        record.video_seconds(broken)


def test_the_launcher_has_no_em_dash() -> None:
    for path in (SCRIPT, ENCODE):
        assert "\u2014" not in path.read_text(encoding="utf-8")


FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"
BASH = shutil.which("bash") or "/bin/bash"
ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is not installed")


def make_take(directory: Path) -> tuple[Path, Path]:
    raw, poster = directory / "raw.webm", directory / "poster.png"
    subprocess.run(  # noqa: S603
        [FFMPEG, "-loglevel", "error", "-y", "-f", "lavfi", "-i",
         "testsrc2=size=1440x900:rate=25:duration=3", "-c:v", "libvpx", str(raw)],
        check=True,
    )  # fmt: skip
    subprocess.run(  # noqa: S603
        [FFMPEG, "-loglevel", "error", "-y", "-f", "lavfi", "-i",
         "color=c=white:s=1440x900", "-frames:v", "1", str(poster)],
        check=True,
    )  # fmt: skip
    return raw, poster


@ffmpeg
def test_encode_makes_a_small_h264_video_and_a_jpeg_poster(tmp_path: Path) -> None:
    raw, poster = make_take(tmp_path)
    out = tmp_path / "out"

    result = subprocess.run(  # noqa: S603
        [BASH, str(ENCODE), str(raw), "1.0", str(poster), str(out)],
        capture_output=True, text=True, check=False,
    )  # fmt: skip

    assert result.returncode == 0, result.stderr
    probe = subprocess.run(  # noqa: S603
        [FFPROBE, "-v", "error", "-show_entries", "stream=codec_name,codec_type,width,height",
         "-show_entries", "format=duration", "-of", "json", str(out / "walkthrough.mp4")],
        capture_output=True, text=True, check=True,
    )  # fmt: skip
    info = json.loads(probe.stdout)
    assert [(s["codec_type"], s["codec_name"]) for s in info["streams"]] == [("video", "h264")]
    assert (info["streams"][0]["width"], info["streams"][0]["height"]) == (1440, 900)
    # The first second was cut: the tour starts there.
    assert 1.5 < float(info["format"]["duration"]) < 2.5
    assert (out / "walkthrough-poster.jpg").read_bytes()[:3] == b"\xff\xd8\xff"
    # The index comes first, so a browser can play before it has the whole file.
    head = (out / "walkthrough.mp4").read_bytes()[:4096]
    moov, mdat = head.find(b"moov"), head.find(b"mdat")
    assert moov != -1
    assert mdat == -1 or moov < mdat


@ffmpeg
def test_encode_fails_when_the_video_is_too_large(tmp_path: Path) -> None:
    raw, poster = make_take(tmp_path)

    result = subprocess.run(  # noqa: S603
        [BASH, str(ENCODE), str(raw), "0", str(poster), str(tmp_path / "out")],
        capture_output=True, text=True, check=False,
        env={"PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin", "MAX_VIDEO_BYTES": "100"},
    )  # fmt: skip

    assert result.returncode == 1
    assert "over the limit" in result.stderr


def test_encode_refuses_a_start_that_is_not_seconds(tmp_path: Path) -> None:
    result = subprocess.run(  # noqa: S603
        [BASH, str(ENCODE), "a.webm", "1; rm -rf /", "p.png", str(tmp_path)],
        capture_output=True, text=True, check=False,
    )  # fmt: skip

    assert result.returncode == 2
    assert "START_SECONDS" in result.stderr
