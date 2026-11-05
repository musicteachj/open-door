"""The one percentile formula, shared by the console's tiles and the evals' scoreboard."""

from app.core.stats import percentile


def test_no_values_have_no_percentile() -> None:
    assert percentile([], 50) is None


def test_the_zeroth_percentile_is_the_smallest_value_never_the_largest() -> None:
    # Nearest rank is never below 1: rank ceil(0 * n / 100) = 0 means the first value.
    assert percentile([3, 1, 2], 0) == 1


def test_the_hundredth_percentile_is_the_largest_value() -> None:
    assert percentile([3, 1, 2], 100) == 3


def test_the_median_of_four_values_is_the_second_by_nearest_rank() -> None:
    # Rank ceil(50 * 4 / 100) = 2, so the second smallest.
    assert percentile([40, 10, 30, 20], 50) == 20
