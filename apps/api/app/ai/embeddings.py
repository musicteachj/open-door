"""Text embeddings: the Voyage client, the committed cache, and a fake for tests.

Embedding happens in two places, and only one of them needs the network. `make embed` fills the
cache through Voyage and the cache is committed. Everything else (`make ingest`, the tests, CI)
reads the cache through `CachedEmbedder` with no inner embedder, so a missing entry is a clear
error instead of a surprise API call.
"""

import asyncio
import base64
import hashlib
import json
import logging
import math
import struct
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from typing import Literal, Protocol, Self

import httpx
from pydantic import SecretStr

logger = logging.getLogger(__name__)

MODEL = "voyage-4"
DIMENSIONS = 1024

InputType = Literal["document", "query"]

VOYAGE_URL = "https://api.voyageai.com/v1/embeddings"
# Voyage allows 1,000 inputs and 320,000 tokens in one request for voyage-4. Smaller batches keep
# a request quick, and keep a retry cheap, on accounts with the lower rate limits.
MAX_BATCH_INPUTS = 128
MAX_BATCH_TOKENS = 320_000
CHARACTERS_PER_TOKEN = 4
MAX_ATTEMPTS = 4
BASE_DELAY_SECONDS = 1.0
TIMEOUT_SECONDS = 60.0
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


class EmbeddingError(Exception):
    """An embedding request failed. The message never contains the API key."""


class EmbeddingMissing(EmbeddingError):  # noqa: N818 (the name the plan uses)
    """The cache lacks an entry and no embedder may fetch it."""


class Embedder(Protocol):
    async def embed(self, texts: Sequence[str], *, input_type: InputType) -> list[list[float]]: ...


UNIT_TOLERANCE = 1e-3


def is_unit_vector(vector: Sequence[float]) -> bool:
    """True if every number is finite and the L2 norm is within 1e-3 of 1 (Voyage's are unit)."""
    if not all(math.isfinite(value) for value in vector):
        return False
    return abs(math.sqrt(math.fsum(value * value for value in vector)) - 1.0) <= UNIT_TOLERANCE


def _estimated_tokens(text: str) -> int:
    return -(-len(text) // CHARACTERS_PER_TOKEN)


def _batches(texts: Sequence[str], max_inputs: int, max_tokens: int) -> list[list[str]]:
    batches: list[list[str]] = []
    current: list[str] = []
    tokens = 0
    for text in texts:
        size = _estimated_tokens(text)
        if current and (len(current) >= max_inputs or tokens + size > max_tokens):
            batches.append(current)
            current, tokens = [], 0
        current.append(text)
        tokens += size
    if current:
        batches.append(current)
    return batches


class VoyageEmbedder:
    """Embeds through Voyage's HTTP API. The key is sent in the Authorization header only."""

    def __init__(
        self,
        api_key: SecretStr,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        max_batch_inputs: int = MAX_BATCH_INPUTS,
        max_batch_tokens: int = MAX_BATCH_TOKENS,
        max_attempts: int = MAX_ATTEMPTS,
        timeout_seconds: float = TIMEOUT_SECONDS,
    ) -> None:
        self._api_key = api_key
        self._transport = transport
        self._sleep = sleep
        self._max_batch_inputs = max_batch_inputs
        self._max_batch_tokens = max_batch_tokens
        self._max_attempts = max_attempts
        self._timeout_seconds = timeout_seconds

    def __repr__(self) -> str:
        return f"VoyageEmbedder(model={MODEL!r})"

    async def embed(self, texts: Sequence[str], *, input_type: InputType) -> list[list[float]]:
        vectors: list[list[float]] = []
        async with httpx.AsyncClient(
            transport=self._transport, timeout=self._timeout_seconds
        ) as client:
            for batch in _batches(texts, self._max_batch_inputs, self._max_batch_tokens):
                vectors.extend(await self._embed_batch(client, batch, input_type))
        return vectors

    async def _embed_batch(
        self, client: httpx.AsyncClient, batch: list[str], input_type: InputType
    ) -> list[list[float]]:
        body = {
            "model": MODEL,
            "input": batch,
            "input_type": input_type,
            "output_dimension": DIMENSIONS,
            # An over-long text is an error here, not a silently shortened embedding.
            "truncation": False,
        }
        headers = {"Authorization": f"Bearer {self._api_key.get_secret_value()}"}
        reason = ""
        for attempt in range(1, self._max_attempts + 1):
            if attempt > 1:
                await self._sleep(BASE_DELAY_SECONDS * 2 ** (attempt - 2))
            try:
                response = await client.post(VOYAGE_URL, json=body, headers=headers)
            except httpx.TimeoutException:
                reason = "the request timed out"
            except httpx.TransportError as error:
                reason = f"the connection failed ({type(error).__name__})"
            except httpx.HTTPError as error:
                # Not worth retrying. Only the type is reported, never the message.
                msg = f"The request failed ({type(error).__name__})."
                raise EmbeddingError(msg) from None
            else:
                if response.status_code == 200:
                    return _vectors(response, len(batch))
                if response.status_code not in RETRY_STATUSES:
                    msg = f"Voyage refused the request with status {response.status_code}."
                    raise EmbeddingError(msg)
                reason = f"Voyage answered with status {response.status_code}"
            logger.warning(
                "Embedding attempt %d of %d failed: %s", attempt, self._max_attempts, reason
            )
        msg = f"Embedding failed after {self._max_attempts} attempts: {reason}."
        raise EmbeddingError(msg)


def _vectors(response: httpx.Response, expected: int) -> list[list[float]]:
    """The batch's vectors in input order, checked for count and size."""
    try:
        rows = sorted(response.json()["data"], key=lambda row: row["index"])
        if [row["index"] for row in rows] != list(range(expected)):
            msg = "Voyage returned the wrong number of embeddings."
            raise EmbeddingError(msg)
        vectors = [[float(value) for value in row["embedding"]] for row in rows]
    except (ValueError, KeyError, TypeError) as error:
        msg = f"Voyage sent an answer this client can't read ({type(error).__name__})."
        raise EmbeddingError(msg) from None
    if any(len(vector) != DIMENSIONS for vector in vectors):
        msg = f"Voyage returned a vector that isn't {DIMENSIONS} numbers long."
        raise EmbeddingError(msg)
    return vectors


class EmbeddingCache:
    """Vectors on disk as JSON Lines, so a committed file diffs cleanly.

    The key is a SHA-256 over the model, the dimensions, the input type, and the text, so a change
    to any of them is a miss. A vector is stored as base64 of little-endian float32.
    """

    def __init__(self) -> None:
        self._vectors: dict[str, bytes] = {}

    def __len__(self) -> int:
        return len(self._vectors)

    @staticmethod
    def key(input_type: InputType, text: str) -> str:
        return hashlib.sha256(f"{MODEL}|{DIMENSIONS}|{input_type}|{text}".encode()).hexdigest()

    def get(self, input_type: InputType, text: str) -> list[float] | None:
        raw = self._vectors.get(self.key(input_type, text))
        return None if raw is None else list(struct.unpack(f"<{DIMENSIONS}f", raw))

    def put(self, input_type: InputType, text: str, vector: Sequence[float]) -> None:
        if len(vector) != DIMENSIONS:
            msg = f"A vector must have {DIMENSIONS} numbers, not {len(vector)}."
            raise ValueError(msg)
        self._vectors[self.key(input_type, text)] = struct.pack(f"<{DIMENSIONS}f", *vector)

    def prune(self, keep: set[str]) -> int:
        """Drop every entry whose key isn't in `keep`; return how many went."""
        stale = [key for key in self._vectors if key not in keep]
        for key in stale:
            del self._vectors[key]
        return len(stale)

    def save(self, path: Path) -> None:
        lines = [
            json.dumps(
                {"key": key, "vector": base64.b64encode(self._vectors[key]).decode("ascii")},
                separators=(",", ":"),
            )
            for key in sorted(self._vectors)
        ]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> Self:
        cache = cls()
        if not path.exists():
            return cache
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                raw = base64.b64decode(record["vector"], validate=True)
                key = record["key"]
            except (ValueError, KeyError, TypeError):
                msg = f"{path}:{number}: not a valid cache line"
                raise ValueError(msg) from None
            if len(raw) != DIMENSIONS * 4 or not isinstance(key, str):
                msg = f"{path}:{number}: not a valid cache line"
                raise ValueError(msg)
            if not is_unit_vector(struct.unpack(f"<{DIMENSIONS}f", raw)):
                msg = f"{path}:{number}: not a finite unit vector"
                raise ValueError(msg)
            cache._vectors[key] = raw
        return cache


class CachedEmbedder:
    """Reads the cache first. A miss goes to `inner` and is stored; with none, it's an error."""

    def __init__(self, cache: EmbeddingCache, inner: Embedder | None) -> None:
        self.cache = cache
        self._inner = inner
        self.hits = 0
        self.fetched = 0
        # Every key this embedder was asked for, so `make embed` can prune the rest.
        self.used: set[str] = set()

    async def embed(self, texts: Sequence[str], *, input_type: InputType) -> list[list[float]]:
        self.used.update(self.cache.key(input_type, text) for text in texts)
        misses = list(dict.fromkeys(t for t in texts if self.cache.get(input_type, t) is None))
        self.hits += len(set(texts)) - len(misses)
        if misses:
            if self._inner is None:
                msg = (
                    f"{len(misses)} text(s) have no cached embedding: "
                    "run `make embed` and commit the cache."
                )
                raise EmbeddingMissing(msg)
            fetched = await self._inner.embed(misses, input_type=input_type)
            for text, vector in zip(misses, fetched, strict=True):
                self.cache.put(input_type, text, vector)
            self.fetched += len(misses)
        results = [self.cache.get(input_type, text) for text in texts]
        return [vector for vector in results if vector is not None]


class FakeEmbedder:
    """Deterministic unit-length vectors from a hash of the text. For tests and development."""

    async def embed(self, texts: Sequence[str], *, input_type: InputType) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    @staticmethod
    def _vector(text: str) -> list[float]:
        raw = hashlib.shake_256(text.encode()).digest(DIMENSIONS * 2)
        values = [int.from_bytes(raw[i : i + 2], "little") - 32768 for i in range(0, len(raw), 2)]
        norm = math.sqrt(sum(v * v for v in values))
        return [v / norm for v in values]


class QueryEmbeddingLru:
    """A small in-process memory of recent query embeddings, wrapped around another embedder.

    It keeps vectors under the same SHA-256 key the cache uses and never the question's text, so
    nothing a person typed stays in memory in readable form. Only `input_type="query"` calls with
    one text are remembered; anything else passes straight through.
    """

    def __init__(self, inner: Embedder, *, max_entries: int = 256) -> None:
        self._inner = inner
        self._max_entries = max_entries
        self._vectors: OrderedDict[str, list[float]] = OrderedDict()

    def __len__(self) -> int:
        return len(self._vectors)

    def scoped(self, scope: str) -> "ScopedQueryEmbedder":
        """A view of this memory for one sandbox. A hit skips the embedding service's round trip,
        and a tool's duration reaches the browser, so a hit shared across sandboxes would tell one
        visitor that another asked the same question. Each scope has its own keys; the one bounded
        memory is shared, so memory stays bounded."""
        return ScopedQueryEmbedder(self, scope)

    async def embed(
        self, texts: Sequence[str], *, input_type: InputType, scope: str = ""
    ) -> list[list[float]]:
        if input_type != "query" or len(texts) != 1:
            return await self._inner.embed(texts, input_type=input_type)
        key = EmbeddingCache.key(input_type, texts[0])
        if scope:
            key = hashlib.sha256(f"{scope}\n{key}".encode()).hexdigest()
        remembered = self._vectors.get(key)
        if remembered is not None:
            self._vectors.move_to_end(key)
            return [list(remembered)]
        [vector] = await self._inner.embed(texts, input_type=input_type)
        self._vectors[key] = list(vector)
        while len(self._vectors) > self._max_entries:
            self._vectors.popitem(last=False)
        return [vector]


class ScopedQueryEmbedder:
    """`QueryEmbeddingLru` for one sandbox (see `QueryEmbeddingLru.scoped`)."""

    def __init__(self, memory: QueryEmbeddingLru, scope: str) -> None:
        self._memory = memory
        self._scope = scope

    async def embed(self, texts: Sequence[str], *, input_type: InputType) -> list[list[float]]:
        return await self._memory.embed(texts, input_type=input_type, scope=self._scope)


def for_sandbox(embedder: Embedder | None, tenant_id: object) -> Embedder | None:
    """The embedder a sandbox's turns use: its own view of the shared query memory."""
    if isinstance(embedder, QueryEmbeddingLru):
        return embedder.scoped(str(tenant_id))
    return embedder
