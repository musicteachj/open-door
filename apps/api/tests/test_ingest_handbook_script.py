"""Failure exits and embed bookkeeping for the ingest script, with no network or database."""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest

from app.ai.embeddings import EmbeddingCache, FakeEmbedder
from app.modules.handbook.load import IngestResult
from scripts.ingest_handbook import (
    CACHE_NAME,
    REPO_ROOT,
    describe,
    eval_questions,
    run_embed,
    run_ingest,
)

FIXTURE = Path(__file__).parent / "fixtures" / "handbook"
API_DIR = Path(__file__).parent.parent


@pytest.fixture
def handbook_dir(tmp_path: Path) -> Path:
    target = tmp_path / "handbook"
    shutil.copytree(FIXTURE, target)
    return target


def test_the_repo_root_is_found_from_the_script_not_the_working_directory() -> None:
    assert (REPO_ROOT / "CLAUDE.md").is_file()
    assert (REPO_ROOT / "handbook" / "handbook.yaml").is_file()


async def test_ingest_exits_with_every_validation_error_and_its_line(
    handbook_dir: Path, tmp_path: Path
) -> None:
    (handbook_dir / "sections" / "9.9-bad.md").write_text("no front matter here\n")
    with pytest.raises(SystemExit) as caught:
        await run_ingest(handbook_dir, tmp_path / "cache.jsonl", "postgresql+asyncpg://nobody/none")
    assert caught.value.code != 0
    assert "sections/9.9-bad.md:1:" in str(caught.value)


async def test_ingest_exits_on_a_cache_miss_before_it_connects(
    handbook_dir: Path, tmp_path: Path
) -> None:
    # The database URL is unreachable: reaching it would fail differently.
    with pytest.raises(SystemExit) as caught:
        await run_ingest(handbook_dir, tmp_path / "cache.jsonl", "postgresql+asyncpg://nobody/none")
    assert "run `make embed` and commit the cache" in str(caught.value)


async def test_embed_fills_both_caches_and_prunes_the_unused(
    handbook_dir: Path, tmp_path: Path
) -> None:
    cache_path = tmp_path / "cache" / "voyage-4-1024.jsonl"
    stale = EmbeddingCache()
    stale.put("document", "a chunk that no longer exists", [1.0] + [0.0] * 1023)
    stale.save(cache_path)
    dataset = tmp_path / "dataset.yaml"
    dataset.write_text(
        "questions:\n  - question: How much sick leave do I get?\n  - question: Q2\n"
    )
    eval_cache = tmp_path / "eval" / CACHE_NAME

    message = await run_embed(handbook_dir, cache_path, dataset, eval_cache, FakeEmbedder())

    handbook_cache = EmbeddingCache.load(cache_path)
    assert handbook_cache.get("document", "a chunk that no longer exists") is None
    assert len(handbook_cache) > 0
    assert len(EmbeddingCache.load(eval_cache)) == 2
    assert EmbeddingCache.load(eval_cache).get("query", "Q2") is not None
    assert f"Handbook cache: 0 hits, fetched {len(handbook_cache)}, pruned 1." in message
    assert "Eval cache: 0 hits, fetched 2, pruned 0." in message

    # A second run finds everything in the caches and writes the same bytes.
    before = cache_path.read_bytes()
    again = await run_embed(handbook_dir, cache_path, dataset, eval_cache, FakeEmbedder())
    assert "fetched 0" in again
    assert cache_path.read_bytes() == before


async def test_embed_skips_the_eval_cache_when_there_is_no_dataset(
    handbook_dir: Path, tmp_path: Path
) -> None:
    eval_cache = tmp_path / "eval" / CACHE_NAME
    await run_embed(
        handbook_dir,
        tmp_path / "cache.jsonl",
        tmp_path / "missing.yaml",
        eval_cache,
        FakeEmbedder(),
    )
    assert not eval_cache.exists()


def test_eval_questions_accept_a_list_of_strings_or_of_mappings(tmp_path: Path) -> None:
    path = tmp_path / "d.yaml"
    path.write_text("questions:\n  - plain\n  - question: mapped\n    expect: x\n")
    assert eval_questions(path) == ["plain", "mapped"]


async def test_embed_validates_the_handbook_first(handbook_dir: Path, tmp_path: Path) -> None:
    (handbook_dir / "sections" / "9.9-bad.md").write_text("nope\n")
    with pytest.raises(SystemExit, match=r"9\.9-bad\.md:1"):
        await run_embed(
            handbook_dir,
            tmp_path / "c.jsonl",
            tmp_path / "none.yaml",
            tmp_path / "e",
            FakeEmbedder(),
        )


def test_embed_without_a_key_exits_with_a_hint(tmp_path: Path) -> None:
    # Run where there is no .env, so no key is found anywhere. An empty VOYAGE_API_KEY in the shell
    # is ignored (it can no longer shadow the key in .env), so it counts as unset too.
    environment = {
        **os.environ,
        "VOYAGE_API_KEY": "",
        "DATABASE_URL": "postgresql+asyncpg://od_app_login:od_app_dev@127.0.0.1:1/opendoor",
    }
    result = subprocess.run(  # noqa: S603
        [sys.executable, str(API_DIR / "scripts" / "ingest_handbook.py"), "embed"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "VOYAGE_API_KEY is not set" in result.stderr
    assert "apps/api/.env" in result.stderr


def test_publishing_text_that_matches_an_older_version_warns_and_carries_on(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = IngestResult("unchanged", uuid4(), current=False, current_label="2026.11")
    line = describe("2026.10", result, publish=True)  # no SystemExit: the exit status stays 0
    captured = capsys.readouterr()
    assert "2026.10: unchanged" in line
    assert captured.out == ""
    assert "Handbook 2026.10 matches an older published version" in captured.err
    assert "2026.11 is newer and stays current. New sandboxes use 2026.11." in captured.err
    assert "new label in handbook.yaml" in captured.err


def test_the_current_version_is_reported_plainly() -> None:
    result = IngestResult("unchanged", uuid4(), current=True, current_label="2026.10")
    assert "2026.10: unchanged" in describe("2026.10", result, publish=True)
    # Loading without publishing never claims to be current.
    unpublished = IngestResult("loaded", uuid4(), current=False, current_label="2026.09")
    assert "loaded" in describe("2026.10", unpublished, publish=False)
