"""The retrieval eval's runner: dataset validation, the scoring arithmetic, and the exit codes.

No database and no network. The real dataset against the real handbook is in
tests/integration/test_retrieval_eval_real.py.
"""

import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.exc import DBAPIError

from app.ai.embeddings import EmbeddingCache, FakeEmbedder
from tests.retrieval_eval import RUN_PATH, load_runner

run = load_runner()


def write_dataset(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


GOOD = """
questions:
  - id: a
    asker: mateo
    question: how many sick days do I get
    expect: ["4.3"]
  - id: b
    asker: { state: CO, employment_type: hourly, location: den }
    question: do I get overtime after 8 hours
    must_not: [CA-3.2]
    location_code: oak
"""


def parse(tmp_path: Path, body: str) -> list[Any]:
    return list(run.parse_dataset(write_dataset(tmp_path / "d.yaml", body)))


def problems(tmp_path: Path, body: str) -> str:
    with pytest.raises(run.DatasetError) as error:
        parse(tmp_path, body)
    return str(error.value)


def test_the_runner_file_exists_where_the_makefile_and_ci_run_it() -> None:
    assert RUN_PATH.is_file()


def test_a_valid_dataset_parses_personas_and_explicit_askers(tmp_path: Path) -> None:
    first, second = parse(tmp_path, GOOD)
    assert (first.asker.state, first.asker.employment_type, first.asker.location_code) == (
        "TX",
        "hourly",
        "aus",
    )
    assert first.asker_label == "mateo"
    assert second.asker_label == "CO hourly (den)"
    assert second.is_negative
    assert second.location_code == "oak"


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (GOOD.replace("id: b", "id: a"), "duplicate id"),
        (GOOD.replace('expect: ["4.3"]', ""), "exactly one of `expect` and `must_not`"),
        (
            GOOD.replace('expect: ["4.3"]', 'expect: ["4.3"]\n    must_not: [CA-4.3]'),
            "exactly one of `expect` and `must_not`",
        ),
        (GOOD.replace('["4.3"]', "[4.3]"), "section IDs written as strings"),
        (GOOD.replace("asker: mateo", "asker: nobody"), "unknown persona"),
        (GOOD.replace("location: den", "location: xyz"), "unknown location"),
        (GOOD.replace("state: CO", "state: TX"), "is not in 'TX'"),
        (GOOD.replace("employment_type: hourly", "employment_type: temp"), "employment_type"),
        (
            GOOD.replace("{ state: CO, employment_type: hourly, location: den }", "{ state: CO }"),
            "exactly state",
        ),
        (GOOD.replace("location_code: oak", "location_code: nowhere"), "unknown location_code"),
        (GOOD.replace("how many sick days do I get", "how many  sick days"), "clean_query"),
        (GOOD.replace("how many sick days do I get", '"how many\\u0007 sick"'), "clean_query"),
    ],
)
def test_dataset_errors_are_named(tmp_path: Path, body: str, expected: str) -> None:
    assert expected in problems(tmp_path, body)


def test_every_problem_is_reported_together(tmp_path: Path) -> None:
    body = GOOD.replace("id: b", "id: a").replace("asker: mateo", "asker: nobody")
    message = problems(tmp_path, body)
    assert "duplicate id" in message
    assert "unknown persona" in message


def test_a_dataset_without_questions_is_refused(tmp_path: Path) -> None:
    assert "questions" in problems(tmp_path, "foo: 1\n")


def test_sections_missing_from_the_loaded_handbook_are_named(tmp_path: Path) -> None:
    questions = parse(tmp_path, GOOD)
    run.check_sections(questions, {"4.3", "CA-3.2"})
    with pytest.raises(run.DatasetError, match=r"b: no section CA-3.2"):
        run.check_sections(questions, {"4.3"})


# --- Scoring, on hand-built results ---------------------------------------------------------


def outcome(tmp_path: Path, qid: str, sections: tuple[str, ...], mode: str = "hybrid") -> Any:
    questions = {q.id: q for q in parse(tmp_path, SCORING)}
    return run.Outcome(questions[qid], mode, sections)


SCORING = """
questions:
  - {id: p1, asker: priya, question: first, expect: ["4.1", "1.2"]}
  - {id: p2, asker: priya, question: second, expect: ["4.1"]}
  - {id: p3, asker: priya, question: third, expect: ["4.2"]}
  - {id: m1, asker: mateo, question: fourth, expect: ["3.2"]}
  - {id: n1, asker: mateo, question: fifth, must_not: [CA-3.2, CO-3.2]}
  - {id: n2, asker: mateo, question: sixth, must_not: [CA-4.3]}
"""


def test_the_hit_rate_and_mean_reciprocal_rank_are_computed_per_question(tmp_path: Path) -> None:
    outcomes = [
        outcome(tmp_path, "p1", ("2.2", "1.2", "4.1")),  # first expected chunk at place 2
        outcome(tmp_path, "p2", ("4.1", "4.1")),  # place 1
        outcome(tmp_path, "p3", ("4.1", "4.3")),  # a miss
        outcome(tmp_path, "m1", ("1.1", "1.1", "1.1", "2.1", "3.2")),  # place 5
        outcome(tmp_path, "n1", ("3.2", "3.3")),
        outcome(tmp_path, "n2", ("4.3", "CA-4.3")),
    ]
    summary = run.summarize(outcomes)

    assert summary.overall.questions == 4  # negatives don't count
    assert summary.overall.hits == 3
    assert summary.overall.hit_rate == pytest.approx(0.75)
    assert summary.overall.mrr == pytest.approx((1 / 2 + 1 + 0 + 1 / 5) / 4)
    assert summary.per_asker["priya"].hits == 2
    assert summary.per_asker["priya"].mrr == pytest.approx((1 / 2 + 1 + 0) / 3)
    assert summary.per_asker["mateo"].hit_rate == 1.0
    assert [o.question.id for o in summary.misses] == ["p3"]


def test_a_negative_fails_only_when_a_forbidden_section_comes_back(tmp_path: Path) -> None:
    summary = run.summarize(
        [
            outcome(tmp_path, "n1", ("3.2", "3.3")),
            outcome(tmp_path, "n2", ("4.3", "CA-4.3", "CA-4.3")),
        ]
    )
    results = {o.question.id: violations for o, violations in summary.negatives}
    assert results == {"n1": (), "n2": ("CA-4.3",)}
    assert [o.question.id for o in summary.failed_negatives] == ["n2"]


def test_an_empty_run_scores_zero_without_dividing_by_zero() -> None:
    summary = run.summarize([])
    assert summary.overall.hit_rate == 0.0
    assert summary.overall.mrr == 0.0


def many(tmp_path: Path, hits: int, total: int) -> list[Any]:
    base = parse(tmp_path, SCORING)[1]  # p2, expects 4.1
    outcomes = []
    for i in range(total):
        outcomes.append(run.Outcome(base, "hybrid", ("4.1",) if i < hits else ("9.9",)))
    return outcomes


def test_check_passes_at_ninety_percent_and_fails_below(tmp_path: Path) -> None:
    assert run.failures(run.summarize(many(tmp_path, 9, 10))) == []
    below = run.failures(run.summarize(many(tmp_path, 17, 19)))  # 17 of 19 is 0.895
    assert below
    assert "below 0.90" in below[0]


def test_check_fails_on_a_failed_negative(tmp_path: Path) -> None:
    outcomes = [*many(tmp_path, 10, 10), outcome(tmp_path, "n2", ("CA-4.3",))]
    assert run.failures(run.summarize(outcomes)) == ["1 negative(s) failed"]


def test_check_fails_on_any_fulltext_fallback(tmp_path: Path) -> None:
    outcomes = many(tmp_path, 10, 10)
    outcomes[0] = run.Outcome(outcomes[0].question, "fulltext", ("4.1",))
    reasons = run.failures(run.summarize(outcomes))
    assert reasons == ["1 search(es) fell back to full-text only"]


def test_the_report_names_misses_negatives_and_fulltext(tmp_path: Path) -> None:
    summary = run.summarize(
        [
            outcome(tmp_path, "p3", ("4.1", "4.3"), mode="fulltext"),
            outcome(tmp_path, "n2", ("CA-4.3",)),
        ]
    )
    text = run.render(summary)
    assert "p3 [priya] third" in text
    assert "wanted 4.2; got 4.1, 4.3" in text
    assert "n2 [mateo] FAILED, returned CA-4.3" in text
    assert "fell back to full-text only" in text
    assert "Check: FAILED" in text


# --- The whole run: exit codes and the scoreboard -------------------------------------------


def cache_for(tmp_path: Path, questions: list[str]) -> Path:
    cache = EmbeddingCache()
    for text, vector in zip(questions, _fake(questions), strict=True):
        cache.put("query", text, vector)
    path = tmp_path / "cache.jsonl"
    cache.save(path)
    return path


def _fake(questions: list[str]) -> list[list[float]]:
    return [FakeEmbedder._vector(text) for text in questions]


QUESTIONS = ["how many sick days do I get", "do I get overtime after 8 hours"]


def fake_runner(sections: dict[str, tuple[str, ...]], mode: str = "hybrid") -> Any:
    async def runner(questions: Any, vectors: Any) -> Any:
        assert all(vector is not None and len(vector) == 1024 for vector in vectors)
        outcomes = [run.Outcome(q, mode, sections[q.id]) for q in questions]
        return run.RunResult("2026.10", {"4.3", "CA-3.2", "CO-3.2", "CA-4.3"}, outcomes)

    return runner


async def test_a_missing_cached_embedding_exits_2_and_says_to_run_make_embed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dataset = write_dataset(tmp_path / "d.yaml", GOOD)
    called = False

    async def runner(questions: Any, vectors: Any) -> Any:
        nonlocal called
        called = True

    code = await run.run(
        [], dataset=dataset, cache_path=tmp_path / "does-not-exist.jsonl", runner=runner
    )

    assert code == 2
    assert not called  # never reached the database or any fallback
    assert "run `make embed` and commit the cache" in capsys.readouterr().err


async def test_one_missing_question_is_enough_to_stop(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dataset = write_dataset(tmp_path / "d.yaml", GOOD)
    cache = cache_for(tmp_path, QUESTIONS[:1])
    code = await run.run([], dataset=dataset, cache_path=cache, runner=fake_runner({}))
    assert code == 2
    assert "1 of 2 questions have no cached embedding (first: b)" in capsys.readouterr().err


async def test_an_invalid_dataset_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dataset = write_dataset(tmp_path / "d.yaml", GOOD.replace("id: b", "id: a"))
    code = await run.run([], dataset=dataset, cache_path=tmp_path / "c.jsonl")
    assert code == 2
    assert "duplicate id" in capsys.readouterr().err


async def test_a_section_the_handbook_lacks_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dataset = write_dataset(tmp_path / "d.yaml", GOOD.replace('["4.3"]', '["9.9"]'))
    cache = cache_for(tmp_path, QUESTIONS)
    code = await run.run(
        [], dataset=dataset, cache_path=cache, runner=fake_runner({"a": (), "b": ()})
    )
    assert code == 2
    assert "no section 9.9" in capsys.readouterr().err


async def test_a_passing_run_exits_0_and_check_agrees(tmp_path: Path) -> None:
    dataset = write_dataset(tmp_path / "d.yaml", GOOD)
    cache = cache_for(tmp_path, QUESTIONS)
    runner = fake_runner({"a": ("4.3",), "b": ("CO-3.2",)})
    assert await run.run(["--check"], dataset=dataset, cache_path=cache, runner=runner) == 0


async def test_check_exits_1_on_a_miss_but_a_plain_run_exits_0(tmp_path: Path) -> None:
    dataset = write_dataset(tmp_path / "d.yaml", GOOD)
    cache = cache_for(tmp_path, QUESTIONS)
    runner = fake_runner({"a": ("1.1",), "b": ("CO-3.2",)})
    assert await run.run([], dataset=dataset, cache_path=cache, runner=runner) == 0
    assert await run.run(["--check"], dataset=dataset, cache_path=cache, runner=runner) == 1


async def test_check_exits_1_on_a_failed_negative(tmp_path: Path) -> None:
    dataset = write_dataset(tmp_path / "d.yaml", GOOD)
    cache = cache_for(tmp_path, QUESTIONS)
    runner = fake_runner({"a": ("4.3",), "b": ("CA-3.2",)})
    assert await run.run(["--check"], dataset=dataset, cache_path=cache, runner=runner) == 1


async def test_check_exits_1_on_a_fulltext_fallback(tmp_path: Path) -> None:
    dataset = write_dataset(tmp_path / "d.yaml", GOOD)
    cache = cache_for(tmp_path, QUESTIONS)
    runner = fake_runner({"a": ("4.3",), "b": ("CO-3.2",)}, mode="fulltext")
    assert await run.run(["--check"], dataset=dataset, cache_path=cache, runner=runner) == 1


async def test_json_writes_the_scoreboard(tmp_path: Path) -> None:
    dataset = write_dataset(tmp_path / "d.yaml", GOOD)
    cache = cache_for(tmp_path, QUESTIONS)
    runner = fake_runner({"a": ("1.1", "4.3"), "b": ("CA-3.2",)})
    out = tmp_path / "out" / "score.json"

    code = await run.run(["--json", str(out)], dataset=dataset, cache_path=cache, runner=runner)

    board = json.loads(out.read_text(encoding="utf-8"))
    assert code == 0
    assert board["model"] == "voyage-4"
    assert board["dimensions"] == 1024
    assert board["datasetSha256"] == run.dataset_hash(dataset)
    assert len(board["datasetSha256"]) == 64
    assert board["handbookVersion"] == "2026.10"
    assert board["date"].endswith("+00:00")
    assert board["commit"]
    assert board["overall"] == {
        "questions": 1,
        "hits": 1,
        "hitRateAt5": 1.0,
        "meanReciprocalRank": 0.5,
    }
    assert board["perAsker"]["mateo"]["hits"] == 1
    assert board["misses"] == []
    assert board["negatives"][0]["passed"] is False
    assert board["passed"] is False


def stub_git(status: str) -> Any:
    def git(*args: str) -> str:
        return "abc123" if args[0] == "rev-parse" else status

    return git


def test_the_commit_is_marked_dirty_when_the_tree_has_uncommitted_changes() -> None:
    assert run.git_commit(stub_git("")) == "abc123"
    assert run.git_commit(stub_git(" M apps/api/app/x.py\n")) == "abc123-dirty"


def test_the_commit_is_unknown_when_git_is_unavailable() -> None:
    def git(*args: str) -> str:
        raise FileNotFoundError

    assert run.git_commit(git) == "unknown"


class _TriggerRefusalError(Exception):
    """What psycopg raises when migration 0005's trigger finds no published handbook."""

    sqlstate = "OD001"


async def test_no_published_handbook_is_unavailable_not_a_traceback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class RefusingSession:
        def add(self, _row: object) -> None:
            pass

        async def flush(self) -> None:
            raise DBAPIError("INSERT INTO tenants ...", {}, _TriggerRefusalError())

    @asynccontextmanager
    async def refusing_session(_engine: object, _context: object) -> Any:
        yield RefusingSession()

    monkeypatch.setattr(run, "tenant_session", refusing_session)
    with pytest.raises(run.EvalUnavailableError, match="Run `make db` first"):
        await run.run_searches_on(object(), [], [])
