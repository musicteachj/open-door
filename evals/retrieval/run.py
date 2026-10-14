"""The retrieval eval: do the right handbook sections come back for real employee questions?

Run it from apps/api:

    uv run python ../../evals/retrieval/run.py [--check] [--json PATH]

It reads `dataset.yaml`, embeds each question from the committed cache (never from Voyage), and
runs `embed_query` then `search_handbook` for the question's asker, taking the top 5 chunks. It
reports hit rate at 5 and mean reciprocal rank (MRR) overall and per asker, every miss, and every
negative. A negative passes when none of its `must_not` sections come back.

`--check` exits 1 when the hit rate is under 0.90, a negative fails, or any search fell back to
full-text only. Exit 2 means the eval could not run: a bad dataset, a missing cached embedding
(run `make embed` and commit the cache), or no handbook in the database. CI runs this with no
network and no Voyage key.

Which database login: the app's own, DATABASE_URL, the same login the API uses. The eval has no
tenant, but the handbook is read through one, because the locations table is under row-level
security and `search_handbook` reads it. So the run opens one scratch tenant inside a transaction
(the database pins it to the newest published version, the way a new sandbox is pinned), runs every
search there, and rolls the transaction back. Nothing is left behind.
"""

import argparse
import asyncio
import hashlib
import json
import subprocess
import sys
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.ai.embeddings import DIMENSIONS, MODEL, CachedEmbedder, EmbeddingCache
from app.core.config import get_settings
from app.db.engine import create_engine
from app.db.models import HandbookSection, HandbookVersion, Location, Tenant
from app.db.tenancy import TenantContext, tenant_session
from app.domain.handbook.applicability import Asker
from app.modules.handbook.search import clean_query, embed_query, pinned_version_id, search_handbook
from app.modules.sandbox.seed_data import LOCATIONS
from app.modules.sandbox.service import is_no_published_handbook

EVAL_DIR = Path(__file__).resolve().parent
DATASET_PATH = EVAL_DIR / "dataset.yaml"
CACHE_PATH = EVAL_DIR / "embeddings" / f"{MODEL}-{DIMENSIONS}.jsonl"

TOP_K = 5
MIN_HIT_RATE = 0.90
MISS_HINT = "run `make embed` and commit the cache"
NO_HANDBOOK = "No published handbook in the database. Run `make db` first."

# The four people the demo talks about, as the handbook sees them. Priya and Marcus are salaried
# in California, Dana is salaried in Colorado, Mateo is hourly in Texas.
PERSONAS: dict[str, Asker] = {
    "priya": Asker("CA", "salaried", "oak"),
    "marcus": Asker("CA", "salaried", "oak"),
    "dana": Asker("CO", "salaried", "den"),
    "mateo": Asker("TX", "hourly", "aus"),
}
LOCATION_STATES = {spec.code: spec.state for spec in LOCATIONS}
EMPLOYMENT_TYPES = ("salaried", "hourly")


class DatasetError(Exception):
    """The dataset is invalid. The message lists every problem, one per line."""


class EvalUnavailableError(Exception):
    """The eval can't run here (no handbook loaded, say). Exit code 2."""


@dataclass(frozen=True, slots=True)
class Question:
    id: str
    asker_label: str
    asker: Asker
    text: str
    expect: tuple[str, ...]
    must_not: tuple[str, ...]
    location_code: str | None

    @property
    def is_negative(self) -> bool:
        return bool(self.must_not)


@dataclass(frozen=True, slots=True)
class Outcome:
    """What one search returned: the section of each chunk, best first."""

    question: Question
    mode: str
    sections: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Stats:
    questions: int
    hits: int
    reciprocal_rank_sum: float

    @property
    def hit_rate(self) -> float:
        return self.hits / self.questions if self.questions else 0.0

    @property
    def mrr(self) -> float:
        return self.reciprocal_rank_sum / self.questions if self.questions else 0.0


@dataclass(frozen=True, slots=True)
class Summary:
    overall: Stats
    per_asker: dict[str, Stats]
    misses: tuple[Outcome, ...]
    negatives: tuple[tuple[Outcome, tuple[str, ...]], ...]  # each with the must_not it hit
    fulltext: tuple[Outcome, ...] = field(default=())

    @property
    def failed_negatives(self) -> tuple[Outcome, ...]:
        return tuple(outcome for outcome, violations in self.negatives if violations)


# ---------------------------------------------------------------------------------------------
# The dataset


def _as_ids(value: Any, where: str, problems: list[str]) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or not all(isinstance(v, str) for v in value):
        problems.append(f"{where}: must be a non-empty list of section IDs written as strings")
        return ()
    return tuple(value)


def _asker(value: Any, where: str, problems: list[str]) -> tuple[str, Asker] | None:
    if isinstance(value, str):
        if value in PERSONAS:
            return value, PERSONAS[value]
        problems.append(f"{where}: unknown persona {value!r} (known: {', '.join(PERSONAS)})")
        return None
    if isinstance(value, dict):
        state, kind, location = (value.get(k) for k in ("state", "employment_type", "location"))
        if set(value) != {"state", "employment_type", "location"}:
            problems.append(f"{where}: an asker needs exactly state, employment_type, and location")
        elif location not in LOCATION_STATES:
            problems.append(f"{where}: unknown location {location!r}")
        elif LOCATION_STATES[location] != state:
            problems.append(f"{where}: location {location!r} is not in {state!r}")
        elif kind not in EMPLOYMENT_TYPES:
            problems.append(f"{where}: employment_type must be one of {EMPLOYMENT_TYPES}")
        else:
            return f"{state} {kind} ({location})", Asker(state, kind, location)
        return None
    problems.append(f"{where}: asker must be a persona name or a mapping")
    return None


def parse_dataset(path: Path) -> list[Question]:
    """The questions in `path`, checked on their own. Raises `DatasetError` listing every problem.

    Whether the section IDs exist in the loaded handbook is checked separately, by
    `check_sections`, because that needs the database.
    """
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    items = data.get("questions") if isinstance(data, dict) else None
    if not isinstance(items, list) or not items:
        msg = f"{path}: expected a `questions:` list"
        raise DatasetError(msg)

    problems: list[str] = []
    questions: list[Question] = []
    seen: set[str] = set()
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            problems.append(f"item {index}: must be a mapping")
            continue
        qid = item.get("id")
        where = f"{qid}" if isinstance(qid, str) and qid else f"item {index}"
        if not isinstance(qid, str) or not qid:
            problems.append(f"{where}: needs an id")
        elif qid in seen:
            problems.append(f"{where}: duplicate id")
        else:
            seen.add(qid)

        text = item.get("question")
        if not isinstance(text, str) or not text.strip():
            problems.append(f"{where}: needs question text")
            text = ""
        else:
            try:
                cleaned = clean_query(text)
            except ValueError:
                cleaned = ""
            if cleaned != text:
                problems.append(
                    f"{where}: the question changes under clean_query (control characters, "
                    "extra spaces, or over 500 characters), so its cached embedding wouldn't match"
                )

        has_expect, has_must_not = "expect" in item, "must_not" in item
        if has_expect == has_must_not:
            problems.append(f"{where}: needs exactly one of `expect` and `must_not`")
        expect = _as_ids(item["expect"], f"{where} expect", problems) if has_expect else ()
        must_not = _as_ids(item["must_not"], f"{where} must_not", problems) if has_must_not else ()

        location_code = item.get("location_code")
        if location_code is not None and location_code not in LOCATION_STATES:
            problems.append(f"{where}: unknown location_code {location_code!r}")
            location_code = None

        who = _asker(item.get("asker"), f"{where} asker", problems)
        if who is not None and isinstance(qid, str) and (expect or must_not):
            questions.append(Question(qid, who[0], who[1], text, expect, must_not, location_code))

    if problems:
        raise DatasetError("\n".join(problems))
    return questions


def check_sections(questions: Sequence[Question], section_ids: set[str]) -> None:
    """Raises `DatasetError` for any `expect` or `must_not` ID the loaded version doesn't have."""
    problems = [
        f"{q.id}: no section {section} in the loaded handbook"
        for q in questions
        for section in (*q.expect, *q.must_not)
        if section not in section_ids
    ]
    if problems:
        raise DatasetError("\n".join(problems))


def dataset_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------------------------
# Scoring


def first_hit_rank(outcome: Outcome) -> int | None:
    """The 1-based place of the first chunk from an expected section, or None."""
    expected = set(outcome.question.expect)
    for place, section in enumerate(outcome.sections, start=1):
        if section in expected:
            return place
    return None


def _stats(outcomes: Sequence[Outcome]) -> Stats:
    ranks = [first_hit_rank(outcome) for outcome in outcomes]
    return Stats(
        questions=len(outcomes),
        hits=sum(rank is not None for rank in ranks),
        reciprocal_rank_sum=sum(1 / rank for rank in ranks if rank is not None),
    )


def summarize(outcomes: Sequence[Outcome]) -> Summary:
    positives = [o for o in outcomes if not o.question.is_negative]
    by_asker: dict[str, list[Outcome]] = {}
    for outcome in positives:
        by_asker.setdefault(outcome.question.asker_label, []).append(outcome)
    return Summary(
        overall=_stats(positives),
        per_asker={label: _stats(group) for label, group in sorted(by_asker.items())},
        misses=tuple(o for o in positives if first_hit_rank(o) is None),
        negatives=tuple(
            (o, tuple(s for s in dict.fromkeys(o.sections) if s in o.question.must_not))
            for o in outcomes
            if o.question.is_negative
        ),
        fulltext=tuple(o for o in outcomes if o.mode != "hybrid"),
    )


def failures(summary: Summary) -> list[str]:
    """Why `--check` would fail, one line each. Empty means it passes."""
    reasons = []
    if summary.overall.hit_rate < MIN_HIT_RATE:
        reasons.append(f"hit rate {summary.overall.hit_rate:.3f} is below {MIN_HIT_RATE:.2f}")
    if summary.failed_negatives:
        reasons.append(f"{len(summary.failed_negatives)} negative(s) failed")
    if summary.fulltext:
        reasons.append(f"{len(summary.fulltext)} search(es) fell back to full-text only")
    return reasons


def render(summary: Summary) -> str:
    lines = [
        f"Hit rate at {TOP_K}: {summary.overall.hit_rate:.3f} "
        f"({summary.overall.hits}/{summary.overall.questions})   MRR: {summary.overall.mrr:.3f}",
        "",
        "Per asker:",
    ]
    for label, stats in summary.per_asker.items():
        lines.append(
            f"  {label:<28} hit rate {stats.hit_rate:.3f} ({stats.hits}/{stats.questions})"
            f"   MRR {stats.mrr:.3f}"
        )
    lines += ["", f"Misses ({len(summary.misses)}):"]
    for outcome in summary.misses:
        q = outcome.question
        lines += [
            f"  {q.id} [{q.asker_label}] {q.text}",
            f"    wanted {', '.join(q.expect)}; got {', '.join(outcome.sections) or 'nothing'}",
        ]
    lines += ["", f"Negatives ({len(summary.negatives)}):"]
    for outcome, violations in summary.negatives:
        q = outcome.question
        verdict = f"FAILED, returned {', '.join(violations)}" if violations else "passed"
        lines += [
            f"  {q.id} [{q.asker_label}] {verdict}",
            f"    must not return {', '.join(q.must_not)}; got "
            f"{', '.join(outcome.sections) or 'nothing'}",
        ]
    if summary.fulltext:
        lines += ["", "FAILURE: these searches fell back to full-text only:"]
        lines += [f"  {o.question.id} (mode {o.mode})" for o in summary.fulltext]
    reasons = failures(summary)
    lines += ["", "Check: " + ("passed" if not reasons else "FAILED, " + "; ".join(reasons))]
    return "\n".join(lines)


def _stats_json(stats: Stats) -> dict[str, Any]:
    return {
        "questions": stats.questions,
        "hits": stats.hits,
        "hitRateAt5": round(stats.hit_rate, 4),
        "meanReciprocalRank": round(stats.mrr, 4),
    }


def scoreboard(
    summary: Summary, *, dataset: Path, version_label: str, commit: str, when: datetime
) -> dict[str, Any]:
    return {
        "model": MODEL,
        "dimensions": DIMENSIONS,
        "datasetSha256": dataset_hash(dataset),
        "commit": commit,
        "date": when.astimezone(UTC).isoformat(timespec="seconds"),
        "handbookVersion": version_label,
        "overall": _stats_json(summary.overall),
        "perAsker": {label: _stats_json(s) for label, s in summary.per_asker.items()},
        "misses": [
            {
                "id": o.question.id,
                "asker": o.question.asker_label,
                "question": o.question.text,
                "expect": list(o.question.expect),
                "returned": list(o.sections),
            }
            for o in summary.misses
        ],
        "negatives": [
            {
                "id": o.question.id,
                "asker": o.question.asker_label,
                "mustNot": list(o.question.must_not),
                "returned": list(o.sections),
                "passed": not violations,
            }
            for o, violations in summary.negatives
        ],
        "fulltextFallbacks": [o.question.id for o in summary.fulltext],
        "passed": not failures(summary),
    }


# ---------------------------------------------------------------------------------------------
# Running the searches

# Given the questions and their cached vectors, returns the handbook version's label, its section
# IDs (to validate the dataset against), and one outcome per question. Tests substitute a fake.
Runner = Callable[[Sequence[Question], list[list[float] | None]], Awaitable["RunResult"]]


@dataclass(frozen=True, slots=True)
class RunResult:
    version_label: str
    section_ids: set[str]
    outcomes: list[Outcome]


class _Discard(Exception):  # noqa: N818 (it's a signal, not an error)
    """Raised to roll the scratch tenant back."""


def missing_embeddings(questions: Sequence[Question], cache: EmbeddingCache) -> list[Question]:
    return [q for q in questions if cache.get("query", clean_query(q.text)) is None]


async def embed_questions(
    questions: Sequence[Question], cache: EmbeddingCache
) -> list[list[float] | None]:
    """Each question's vector from the cache. There is no inner embedder, so a miss can't reach
    Voyage. `missing_embeddings` has already made sure there are none."""
    embedder = CachedEmbedder(cache, None)
    return [await embed_query(embedder, q.text) for q in questions]


async def run_searches_on(
    engine: AsyncEngine, questions: Sequence[Question], vectors: list[list[float] | None]
) -> RunResult:
    tenant_id = uuid4()
    now = datetime.now(UTC)
    result: RunResult | None = None
    try:
        async with tenant_session(engine, TenantContext(tenant_id, None)) as db:
            db.add(
                Tenant(id=tenant_id, expires_at=now + timedelta(hours=1), anchor_date=now.date())
            )
            try:
                await db.flush()
            except DBAPIError as error:
                # Migration 0005's trigger refuses a tenant when no handbook is published.
                if not is_no_published_handbook(error):
                    raise
                raise EvalUnavailableError(NO_HANDBOOK) from error
            db.add_all(
                Location(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    code=spec.code,
                    name=spec.name,
                    city=spec.city,
                    state=spec.state,
                    timezone=spec.timezone,
                )
                for spec in LOCATIONS
            )
            await db.flush()
            version_id = await pinned_version_id(db)
            if version_id is None:
                raise EvalUnavailableError(NO_HANDBOOK)
            label = await db.scalar(
                select(HandbookVersion.label).where(HandbookVersion.id == version_id)
            )
            section_ids = set(
                await db.scalars(
                    select(HandbookSection.section_key).where(
                        HandbookSection.version_id == version_id
                    )
                )
            )
            check_sections(questions, section_ids)
            outcomes = []
            for question, vector in zip(questions, vectors, strict=True):
                found = await search_handbook(
                    db,
                    version_id=version_id,
                    asker=question.asker,
                    query=question.text,
                    query_vector=vector,
                    location_code=question.location_code,
                    limit=TOP_K,
                )
                outcomes.append(
                    Outcome(question, found.mode, tuple(hit.section_id for hit in found.hits))
                )
            result = RunResult(label or "", section_ids, outcomes)
            raise _Discard
    except _Discard:
        pass
    assert result is not None  # noqa: S101 (unreachable otherwise)
    return result


async def run_searches(
    questions: Sequence[Question], vectors: list[list[float] | None]
) -> RunResult:
    engine = create_engine(str(get_settings().database_url))
    try:
        return await run_searches_on(engine, questions, vectors)
    finally:
        await engine.dispose()


def _git(*args: str) -> str:
    done = subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=EVAL_DIR,
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout.strip()


def git_commit(git: Callable[..., str] = _git) -> str:
    """HEAD's hash, with `-dirty` added when the working tree has uncommitted changes."""
    try:
        commit = git("rev-parse", "HEAD")
        dirty = bool(git("status", "--porcelain"))
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return f"{commit}-dirty" if dirty else commit


async def run(
    argv: Sequence[str] | None = None,
    *,
    dataset: Path = DATASET_PATH,
    cache_path: Path = CACHE_PATH,
    runner: Runner = run_searches,
) -> int:
    """The whole eval. Returns the exit code: 0, 1 (`--check` failed), or 2 (couldn't run)."""
    parser = argparse.ArgumentParser(description="Run the handbook retrieval eval.")
    parser.add_argument("--check", action="store_true", help="exit 1 if the eval fails")
    parser.add_argument("--json", type=Path, metavar="PATH", help="write the scoreboard here")
    args = parser.parse_args(argv)

    try:
        questions = parse_dataset(dataset)
    except DatasetError as error:
        print(f"The dataset is invalid:\n{error}", file=sys.stderr)
        return 2

    cache = EmbeddingCache.load(cache_path)
    missing = missing_embeddings(questions, cache)
    if missing:
        print(
            f"{len(missing)} of {len(questions)} questions have no cached embedding "
            f"(first: {missing[0].id}). {MISS_HINT}.",
            file=sys.stderr,
        )
        return 2

    vectors = await embed_questions(questions, cache)
    try:
        result = await runner(questions, vectors)
        check_sections(questions, result.section_ids)
    except DatasetError as error:
        print(f"The dataset is invalid for this handbook:\n{error}", file=sys.stderr)
        return 2
    except EvalUnavailableError as error:
        print(str(error), file=sys.stderr)
        return 2

    summary = summarize(result.outcomes)
    print(f"Handbook {result.version_label}, {len(questions)} questions.\n")
    print(render(summary))
    if args.json is not None:
        board = scoreboard(
            summary,
            dataset=dataset,
            version_label=result.version_label,
            commit=git_commit(),
            when=datetime.now(UTC),
        )
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(board, indent=2) + "\n", encoding="utf-8")
    return 1 if args.check and failures(summary) else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
