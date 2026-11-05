"""Small statistics helpers, with no imports from the rest of the app, so the evals can use them
without loading the assistant."""

from collections.abc import Sequence


def percentile(values: Sequence[int], percent: int) -> int | None:
    """The `percent`th percentile by the nearest-rank method; None for no values.

    The one percentile formula: the console's tiles and the evals' scoreboard both use it. The
    value at rank ceil(percent * n / 100) of the sorted values (never below rank 1), with the
    ceiling done in integers so no float rounding moves the rank.
    """
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, -(-percent * len(ordered) // 100))
    return ordered[rank - 1]
