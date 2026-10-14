"""Reciprocal-rank fusion, on rankings worked out by hand."""

from uuid import uuid4

import pytest

from app.domain.retrieval import ChunkKey, fuse


def key(section_position: int, position: int = 0) -> ChunkKey:
    return ChunkKey(uuid4(), uuid4(), section_position, position)


def test_a_chunk_in_both_lists_outranks_one_in_only_one() -> None:
    a, b, c = key(1), key(2), key(3)

    # a: rank 2 in both lists, 1/62 + 1/62; b and c: one list each
    fused = fuse([b, a], [c, a])

    assert fused[0].key == a
    assert fused[0].score == pytest.approx(1 / 62 + 1 / 62)
    assert fused[0].ranks == (2, 2)


def test_scores_are_the_sum_of_one_over_k_plus_rank() -> None:
    a, b = key(1), key(2)

    fused = fuse([a, b], [b], k=10)

    by_key = {f.key: f for f in fused}
    assert by_key[a].score == pytest.approx(1 / 11)
    assert by_key[b].score == pytest.approx(1 / 12 + 1 / 11)
    assert [f.key for f in fused] == [b, a]
    assert by_key[a].ranks == (1, None)
    assert by_key[b].ranks == (2, 1)


def test_exact_ties_break_by_section_position_then_chunk_position() -> None:
    late_section = key(5, 0)
    early_section_late_chunk = key(2, 3)
    early_section_early_chunk = key(2, 1)

    # Each is first in its own single-entry list, so all three score 1/61.
    fused = fuse([late_section], [early_section_late_chunk], [early_section_early_chunk])

    assert [f.key for f in fused] == [
        early_section_early_chunk,
        early_section_late_chunk,
        late_section,
    ]


def test_one_empty_list_leaves_the_other_in_order() -> None:
    a, b, c = key(3), key(1), key(2)

    fused = fuse([a, b, c], [])

    assert [f.key for f in fused] == [a, b, c]
    assert all(f.ranks[1] is None for f in fused)


def test_no_lists_or_only_empty_lists_fuse_to_nothing() -> None:
    assert fuse() == []
    assert fuse([], []) == []


def test_the_same_inputs_always_give_the_same_order() -> None:
    keys = [key(i % 3, i) for i in range(8)]

    first = fuse(keys, list(reversed(keys)))
    assert fuse(keys, list(reversed(keys))) == first
