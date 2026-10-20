"""Reciprocal-rank fusion: merge several ranked lists of chunks into one.

Each chunk scores the sum of `1 / (k + rank)` over the lists it appears in, with ranks counted
from 1. Pure: no framework, no database.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

RRF_K = 60

# A question is a sentence or two. The cap bounds what one search can cost. Here, not beside the
# search, so the scripted model can cut its query to fit without loading the database layer.
MAX_QUERY_CHARACTERS = 500


@dataclass(frozen=True, slots=True)
class ChunkKey:
    """A chunk, with the two positions that break ties so the order never varies."""

    chunk_id: UUID
    section_id: UUID
    # The section's place in the handbook, then the chunk's place in its section.
    section_position: int
    position: int


@dataclass(frozen=True, slots=True)
class Fused:
    key: ChunkKey
    score: float
    # This chunk's 1-based rank in each input list, in the order the lists were given; None where
    # it doesn't appear.
    ranks: tuple[int | None, ...]


def fuse(*rankings: Sequence[ChunkKey], k: int = RRF_K) -> list[Fused]:
    """Best first. Equal scores order by section position, then chunk position."""
    scores: dict[ChunkKey, float] = {}
    ranks: dict[ChunkKey, list[int | None]] = {}
    for index, ranking in enumerate(rankings):
        for rank, key in enumerate(ranking, start=1):
            if ranks.setdefault(key, [None] * len(rankings))[index] is not None:
                continue  # a repeat within one list counts once, at its best rank
            ranks[key][index] = rank
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
    fused = [Fused(key, scores[key], tuple(ranks[key])) for key in scores]
    fused.sort(key=lambda f: (-f.score, f.key.section_position, f.key.position))
    return fused
