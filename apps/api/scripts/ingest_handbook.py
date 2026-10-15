"""Load the handbook into the database, and fill the embedding caches it loads from.

    python scripts/ingest_handbook.py ingest   read handbook/, validate, embed from the cache, load
    python scripts/ingest_handbook.py embed    fetch missing embeddings from Voyage into the caches

`ingest` runs as the database owner (MIGRATION_DATABASE_URL) in one transaction and never calls
Voyage: a text with no cached vector stops it. `embed` is the only command that needs
VOYAGE_API_KEY. It fills the handbook's cache and, once Stage 3 adds the file, the retrieval eval's
cache, then drops entries nothing uses. Commit the caches, so CI and every other machine can load
the handbook without a key.
"""

import argparse
import asyncio
import sys
from pathlib import Path

import yaml
from sqlalchemy.ext.asyncio import create_async_engine

from app.ai.embeddings import (
    DIMENSIONS,
    MODEL,
    CachedEmbedder,
    Embedder,
    EmbeddingCache,
    EmbeddingError,
    EmbeddingMissing,
    InputType,
    VoyageEmbedder,
)
from app.core.config import get_settings
from app.domain.handbook.chunks import chunks_for
from app.domain.handbook.errors import HandbookInvalid
from app.domain.handbook.models import Handbook
from app.modules.handbook.load import IngestError, IngestResult, ingest
from app.modules.handbook.source import read_handbook

# scripts/ is two levels below the repository root: apps/api/scripts.
REPO_ROOT = Path(__file__).resolve().parents[3]
HANDBOOK_DIR = REPO_ROOT / "handbook"
CACHE_NAME = f"{MODEL}-{DIMENSIONS}.jsonl"
CACHE_PATH = HANDBOOK_DIR / "embeddings" / CACHE_NAME
EVAL_DIR = REPO_ROOT / "evals" / "retrieval"
EVAL_DATASET = EVAL_DIR / "dataset.yaml"
EVAL_CACHE_PATH = EVAL_DIR / "embeddings" / CACHE_NAME

MISS_HINT = "run `make embed` and commit the cache"


def read_valid(handbook_dir: Path) -> Handbook:
    """The validated handbook, or an exit that lists every error with its file and line."""
    try:
        return read_handbook(handbook_dir)
    except HandbookInvalid as invalid:
        raise SystemExit(str(invalid)) from None


def embed_texts(handbook: Handbook) -> list[str]:
    return [chunk.embed_text for section in handbook.sections for chunk in chunks_for(section)]


async def run_ingest(handbook_dir: Path, cache_path: Path, database_url: str) -> str:
    handbook = read_valid(handbook_dir)
    embedder = CachedEmbedder(EmbeddingCache.load(cache_path), None)
    try:
        # Look every vector up before connecting, so a miss fails without touching the database.
        await embedder.embed(embed_texts(handbook), input_type="document")
    except EmbeddingMissing as missing:
        raise SystemExit(str(missing)) from None

    # hide_parameters keeps the handbook's text and vectors out of SQLAlchemy's error messages.
    engine = create_async_engine(database_url, hide_parameters=True)
    try:
        async with engine.begin() as connection:
            result = await ingest(connection, handbook, embedder, publish=True)
    except IngestError as error:
        raise SystemExit(str(error)) from None
    finally:
        await engine.dispose()
    return describe(handbook.version, result, publish=True)


def describe(label: str, result: IngestResult, *, publish: bool) -> str:
    """The line to print. Text that matches an older published version isn't an error (switching
    branches puts one on disk, and `make db` runs this every time), so it only warns on stderr."""
    if publish and not result.current:
        print(
            f"Warning: Handbook {label} matches an older published version; "
            f"{result.current_label} is newer and stays current. New sandboxes use "
            f"{result.current_label}. To make this text current again, give it a new label in "
            "handbook.yaml.",
            file=sys.stderr,
        )
    return f"Handbook {label}: {result.status} (version {result.version_id})."


def eval_questions(dataset: Path) -> list[str]:
    """The questions in the retrieval eval's dataset: a list, or a `questions:` list, whose items
    are strings or mappings with a `question` field."""
    data = yaml.safe_load(dataset.read_text(encoding="utf-8"))
    items = data["questions"] if isinstance(data, dict) else data
    return [item["question"] if isinstance(item, dict) else str(item) for item in items]


def optional_eval_questions(dataset: Path) -> list[str] | None:
    """The questions, or None while Stage 3 hasn't created the dataset yet."""
    return eval_questions(dataset) if dataset.exists() else None


async def _fill(
    cache_path: Path, texts: list[str], input_type: InputType, inner: Embedder
) -> tuple[int, int, int]:
    """Fill one cache for `texts`, prune the rest, save. Returns (hits, fetched, pruned)."""
    cache = EmbeddingCache.load(cache_path)
    embedder = CachedEmbedder(cache, inner)
    await embedder.embed(texts, input_type=input_type)
    pruned = cache.prune(embedder.used)
    cache.save(cache_path)
    return embedder.hits, embedder.fetched, pruned


async def run_embed(
    handbook_dir: Path,
    cache_path: Path,
    eval_dataset: Path,
    eval_cache_path: Path,
    embedder: Embedder,
) -> str:
    handbook = read_valid(handbook_dir)
    lines = []
    try:
        hits, fetched, pruned = await _fill(cache_path, embed_texts(handbook), "document", embedder)
        lines.append(f"Handbook cache: {hits} hits, fetched {fetched}, pruned {pruned}.")
        questions = optional_eval_questions(eval_dataset)
        if questions is not None:
            hits, fetched, pruned = await _fill(eval_cache_path, questions, "query", embedder)
            lines.append(f"Eval cache: {hits} hits, fetched {fetched}, pruned {pruned}.")
    except EmbeddingError as error:
        raise SystemExit(f"Embedding failed: {error}") from None
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0] if __doc__ else None)
    parser.add_argument("command", choices=["ingest", "embed"])
    command = parser.parse_args(argv).command

    settings = get_settings()
    if command == "embed":
        if settings.voyage_api_key is None:
            raise SystemExit(
                "VOYAGE_API_KEY is not set. Add it to apps/api/.env (an empty value there means no "
                "key)."
            )
        embedder = VoyageEmbedder(settings.voyage_api_key)
        print(
            asyncio.run(
                run_embed(HANDBOOK_DIR, CACHE_PATH, EVAL_DATASET, EVAL_CACHE_PATH, embedder)
            )
        )
        return

    if settings.migration_database_url is None:
        raise SystemExit("MIGRATION_DATABASE_URL is not set. See apps/api/.env.example.")
    print(asyncio.run(run_ingest(HANDBOOK_DIR, CACHE_PATH, str(settings.migration_database_url))))


if __name__ == "__main__":
    try:
        main()
    except SystemExit as stop:
        if isinstance(stop.code, str):
            print(stop.code, file=sys.stderr)
            sys.exit(1)
        raise
