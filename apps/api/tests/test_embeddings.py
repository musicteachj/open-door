"""The embedding client, its cache, and the fake: no test here reaches the network."""

import base64
import hashlib
import json
import logging
import math
import struct
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from app.ai.embeddings import (
    DIMENSIONS,
    MODEL,
    CachedEmbedder,
    EmbeddingCache,
    EmbeddingError,
    EmbeddingMissing,
    FakeEmbedder,
    VoyageEmbedder,
)
from app.core.config import Settings

KEY = "pa-super-secret-key-12345"


def vector(seed: float = 0.5) -> list[float]:
    # A unit vector (the cache refuses any other), and exact in float32, so the round trip must give
    # it back unchanged.
    return [1.0 if index == int(seed * 2) else 0.0 for index in range(DIMENSIONS)]


def test_the_cache_key_is_a_sha256_of_model_dimensions_input_type_and_text() -> None:
    expected = hashlib.sha256(f"{MODEL}|{DIMENSIONS}|document|hello".encode()).hexdigest()
    assert EmbeddingCache().key("document", "hello") == expected
    assert EmbeddingCache().key("query", "hello") != expected


def test_the_cache_stores_base64_little_endian_float32(tmp_path: Path) -> None:
    cache = EmbeddingCache()
    cache.put("document", "hello", vector())
    assert cache.get("document", "hello") == vector()
    assert cache.get("query", "hello") is None

    path = tmp_path / "cache.jsonl"
    cache.save(path)
    record = json.loads(path.read_text().splitlines()[0])
    raw = base64.b64decode(record["vector"])
    assert struct.unpack(f"<{DIMENSIONS}f", raw) == tuple(vector())
    assert EmbeddingCache.load(path).get("document", "hello") == vector()


def test_saving_is_sorted_by_key_so_the_file_diffs_cleanly(tmp_path: Path) -> None:
    first, second = EmbeddingCache(), EmbeddingCache()
    for text in ("b", "a", "c"):
        first.put("document", text, vector())
    for text in ("c", "b", "a"):
        second.put("document", text, vector())
    first.save(tmp_path / "one.jsonl")
    second.save(tmp_path / "two.jsonl")
    one = (tmp_path / "one.jsonl").read_text()
    assert one == (tmp_path / "two.jsonl").read_text()
    keys = [json.loads(line)["key"] for line in one.splitlines()]
    assert keys == sorted(keys)
    assert one.endswith("\n")


@pytest.mark.parametrize(
    "line",
    [
        "this is not json",
        '{"key": "abc"}',
        '{"vector": "AAAA"}',
        '{"key": "abc", "vector": "!!!not base64!!!"}',
        '{"key": "abc", "vector": "AAAA"}',
    ],
)
def test_a_corrupt_cache_line_is_reported_with_its_file_and_line(tmp_path: Path, line: str) -> None:
    path = tmp_path / "cache.jsonl"
    cache = EmbeddingCache()
    cache.put("document", "ok", vector())
    cache.save(path)
    path.write_text(path.read_text() + line + "\n")
    with pytest.raises(ValueError, match=r"cache\.jsonl:2: not a valid cache line"):
        EmbeddingCache.load(path)


def padded(**at: float) -> list[float]:
    values = [0.0] * DIMENSIONS
    for index, value in at.items():
        values[int(index.removeprefix("i"))] = value
    return values


@pytest.mark.parametrize(
    "bad",
    [
        padded(i0=float("nan")),
        padded(i0=float("inf")),
        padded(i0=-float("inf")),
        padded(i0=3.0e38),  # finite, but its norm is nowhere near 1
        padded(i0=0.5),  # not a unit vector
        padded(),  # the zero vector
    ],
)
def test_a_cached_vector_that_is_not_a_finite_unit_vector_is_reported_with_its_line(
    tmp_path: Path, bad: list[float]
) -> None:
    path = tmp_path / "cache.jsonl"
    cache = EmbeddingCache()
    cache.put("document", "ok", vector())
    cache.put("document", "bad", bad)
    cache.save(path)
    bad_line = [json.loads(line)["key"] for line in path.read_text().splitlines()].index(
        cache.key("document", "bad")
    )

    with pytest.raises(ValueError, match=rf"cache\.jsonl:{bad_line + 1}: .*unit"):
        EmbeddingCache.load(path)


def test_the_fake_embedders_vectors_pass_the_cache_check(tmp_path: Path) -> None:
    cache = EmbeddingCache()
    cache.put("document", "a", FakeEmbedder._vector("a"))
    cache.save(tmp_path / "cache.jsonl")

    assert len(EmbeddingCache.load(tmp_path / "cache.jsonl")) == 1


def test_a_missing_file_is_an_empty_cache(tmp_path: Path) -> None:
    assert len(EmbeddingCache.load(tmp_path / "nope.jsonl")) == 0


def test_prune_keeps_only_the_named_keys() -> None:
    cache = EmbeddingCache()
    cache.put("document", "a", vector())
    cache.put("document", "b", vector())
    assert cache.prune({cache.key("document", "a")}) == 1
    assert cache.get("document", "a") is not None
    assert cache.get("document", "b") is None


def test_the_cache_refuses_a_vector_of_the_wrong_size() -> None:
    with pytest.raises(ValueError, match="1024"):
        EmbeddingCache().put("document", "a", [0.0] * 3)


async def test_a_cache_miss_without_an_inner_embedder_names_the_count() -> None:
    cache = EmbeddingCache()
    cache.put("document", "known", vector())
    embedder = CachedEmbedder(cache, None)
    with pytest.raises(EmbeddingMissing, match="2") as caught:
        await embedder.embed(["known", "x", "y"], input_type="document")
    assert "run `make embed` and commit the cache" in str(caught.value)


async def test_a_miss_goes_to_the_inner_embedder_and_is_stored() -> None:
    cache = EmbeddingCache()
    cache.put("document", "known", vector())
    embedder = CachedEmbedder(cache, FakeEmbedder())
    result = await embedder.embed(["known", "new", "new"], input_type="document")
    assert result[0] == vector()
    # The cache holds float32, so a fetched vector comes back rounded the same way as a cached one.
    assert result[1] == result[2] == cache.get("document", "new")
    assert cache.get("document", "new") is not None
    assert (embedder.hits, embedder.fetched) == (1, 1)
    assert embedder.used == {cache.key("document", "known"), cache.key("document", "new")}


async def test_the_fake_is_deterministic_and_unit_length() -> None:
    first = await FakeEmbedder().embed(["a", "b"], input_type="query")
    again = await FakeEmbedder().embed(["a"], input_type="query")
    assert first[0] == again[0] != first[1]
    assert len(first[0]) == DIMENSIONS
    assert math.isclose(math.sqrt(sum(x * x for x in first[0])), 1.0, rel_tol=1e-9)


# --- VoyageEmbedder ---------------------------------------------------------------------------


class Server:
    """A MockTransport handler that records requests and answers like Voyage."""

    def __init__(self, *, failures: Sequence[int | Exception] | None = None) -> None:
        self.requests: list[httpx.Request] = []
        self.failures = list(failures or [])

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.failures:
            failure = self.failures.pop(0)
            if isinstance(failure, Exception):
                raise failure
            return httpx.Response(failure, json={"detail": "nope"})
        texts = json.loads(request.content)["input"]
        # Answer out of order, to prove the embedder sorts by index.
        data = [
            {"object": "embedding", "index": index, "embedding": [float(len(text))] * DIMENSIONS}
            for index, text in reversed(list(enumerate(texts)))
        ]
        return httpx.Response(200, json={"data": data, "usage": {"total_tokens": 1}})

    def bodies(self) -> list[dict[str, Any]]:
        return [json.loads(request.content) for request in self.requests]


def voyage(server: Server, **options: Any) -> tuple[VoyageEmbedder, list[float]]:
    delays: list[float] = []

    async def sleep(seconds: float) -> None:
        delays.append(seconds)

    embedder = VoyageEmbedder(
        SecretStr(KEY), transport=httpx.MockTransport(server), sleep=sleep, **options
    )
    return embedder, delays


async def test_the_request_has_the_documented_fields_and_the_key_only_in_a_header() -> None:
    server = Server()
    embedder, _ = voyage(server)
    result = await embedder.embed(["abc", "de"], input_type="query")

    request = server.requests[0]
    assert str(request.url) == "https://api.voyageai.com/v1/embeddings"
    assert request.method == "POST"
    assert request.headers["authorization"] == f"Bearer {KEY}"
    assert server.bodies()[0] == {
        "model": "voyage-4",
        "input": ["abc", "de"],
        "input_type": "query",
        "output_dimension": 1024,
        "truncation": False,
    }
    assert KEY not in request.content.decode()
    assert KEY not in str(request.url)
    assert [row[0] for row in result] == [3.0, 2.0]


async def test_inputs_are_batched_by_count() -> None:
    server = Server()
    embedder, _ = voyage(server, max_batch_inputs=2)
    result = await embedder.embed(["a", "bb", "ccc", "dddd", "eeeee"], input_type="document")
    assert [len(body["input"]) for body in server.bodies()] == [2, 2, 1]
    assert [row[0] for row in result] == [1.0, 2.0, 3.0, 4.0, 5.0]


async def test_inputs_are_batched_by_estimated_tokens() -> None:
    server = Server()
    # Four characters a token: each 40-character text is 10 tokens, so two fit in 25.
    embedder, _ = voyage(server, max_batch_tokens=25)
    await embedder.embed(["x" * 40] * 5, input_type="document")
    assert [len(body["input"]) for body in server.bodies()] == [2, 2, 1]


async def test_an_oversize_text_still_goes_out_alone() -> None:
    server = Server()
    embedder, _ = voyage(server, max_batch_tokens=10)
    await embedder.embed(["x" * 400, "y"], input_type="document")
    assert [len(body["input"]) for body in server.bodies()] == [1, 1]


async def test_no_texts_make_no_request() -> None:
    server = Server()
    embedder, _ = voyage(server)
    assert await embedder.embed([], input_type="document") == []
    assert server.requests == []


@pytest.mark.parametrize("status", [429, 503])
async def test_it_retries_a_rate_limit_or_server_error_with_backoff(status: int) -> None:
    server = Server(failures=[status, status])
    embedder, delays = voyage(server)
    result = await embedder.embed(["abc"], input_type="document")
    assert result[0][0] == 3.0
    assert len(server.requests) == 3
    assert len(delays) == 2
    assert delays[1] > delays[0] > 0


async def test_it_gives_up_after_a_few_attempts_with_a_clear_error() -> None:
    server = Server(failures=[503] * 10)
    embedder, _ = voyage(server, max_attempts=3)
    with pytest.raises(EmbeddingError, match="503") as caught:
        await embedder.embed(["abc"], input_type="document")
    assert len(server.requests) == 3
    assert "3 attempts" in str(caught.value)


async def test_a_client_error_is_not_retried() -> None:
    server = Server(failures=[401])
    embedder, _ = voyage(server)
    with pytest.raises(EmbeddingError, match="401"):
        await embedder.embed(["abc"], input_type="document")
    assert len(server.requests) == 1


async def test_a_timeout_is_retried_and_then_reported() -> None:
    server = Server(failures=[httpx.ReadTimeout("slow")] * 10)
    embedder, _ = voyage(server, max_attempts=2)
    with pytest.raises(EmbeddingError, match="timed out"):
        await embedder.embed(["abc"], input_type="document")
    assert len(server.requests) == 2


async def test_the_key_never_reaches_a_log_or_an_error(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    ok = Server()
    embedder, _ = voyage(ok)
    await embedder.embed(["abc"], input_type="document")

    failure_lists: list[list[int | Exception]] = [
        [401],
        [503] * 5,
        [httpx.ConnectError("boom")] * 5,
    ]
    for failures in failure_lists:
        server = Server(failures=failures)
        embedder, _ = voyage(server, max_attempts=2)
        with pytest.raises(EmbeddingError) as caught:
            await embedder.embed(["abc"], input_type="document")
        assert KEY not in str(caught.value)
        assert KEY not in repr(caught.value)
        assert KEY not in repr(caught.value.__cause__)
    assert KEY not in caplog.text
    assert KEY not in repr(embedder)


async def test_a_non_transport_http_error_fails_at_once_naming_only_its_type() -> None:
    server = Server(failures=[httpx.TooManyRedirects("redirects with " + KEY)])
    embedder, delays = voyage(server)
    with pytest.raises(EmbeddingError, match="TooManyRedirects") as caught:
        await embedder.embed(["abc"], input_type="document")
    assert len(server.requests) == 1
    assert delays == []
    assert KEY not in str(caught.value)
    assert caught.value.__cause__ is None


@pytest.mark.parametrize(
    "payload",
    [
        {"data": [{"index": 0, "embedding": [0.0] * 3}]},
        {"data": []},
        {"data": [{"index": 5, "embedding": [0.0] * DIMENSIONS}]},
        {"nonsense": True},
    ],
)
async def test_a_malformed_answer_is_an_error(payload: dict[str, Any]) -> None:
    embedder = VoyageEmbedder(
        SecretStr(KEY),
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)),
    )
    with pytest.raises(EmbeddingError):
        await embedder.embed(["abc"], input_type="document")


# --- settings ---------------------------------------------------------------------------------


def settings_from_environment() -> Settings:
    return Settings(_env_file=None, database_url="postgresql+asyncpg://u:p@localhost/db")


def test_an_empty_voyage_key_counts_as_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VOYAGE_API_KEY", "")
    assert settings_from_environment().voyage_api_key is None
    monkeypatch.delenv("VOYAGE_API_KEY")
    assert settings_from_environment().voyage_api_key is None


def test_a_voyage_key_is_a_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VOYAGE_API_KEY", KEY)
    settings = settings_from_environment()
    assert settings.voyage_api_key is not None
    assert settings.voyage_api_key.get_secret_value() == KEY
    assert KEY not in repr(settings)
