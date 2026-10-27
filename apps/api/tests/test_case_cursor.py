"""A queue cursor is ours or it is refused: every malformed one is a ValueError, never another
exception (which would reach the client as a 500)."""

import base64
import json
from typing import Any

import pytest

from app.modules.cases.queries import decode_cursor

GOOD = [0, "2026-01-01", "2026-01-01T00:00:00+00:00", "7d4e0d2e-5f55-4a39-9f0f-3c1d3a3f6a11"]


def cursor(value: Any) -> str:
    return base64.urlsafe_b64encode(json.dumps(value).encode()).decode()


def test_a_cursor_of_ours_decodes() -> None:
    group, reply, created, case_id = decode_cursor(cursor(GOOD))

    assert (group, str(reply), created.isoformat(), str(case_id)) == (
        0,
        "2026-01-01",
        "2026-01-01T00:00:00+00:00",
        GOOD[3],
    )


@pytest.mark.parametrize(
    "value",
    [
        [0, "2026-01-01", "2026-01-01T00:00:00+00:00", 5],
        [True, "2026-01-01", "2026-01-01T00:00:00+00:00", GOOD[3]],
        [False, "2026-01-01", "2026-01-01T00:00:00+00:00", GOOD[3]],
        [2, "2026-01-01", "2026-01-01T00:00:00+00:00", GOOD[3]],
        [0, 20260101, "2026-01-01T00:00:00+00:00", GOOD[3]],
        [0, "2026-01-01", 5, GOOD[3]],
        [0, "2026-01-01", "2026-01-01T00:00:00", GOOD[3]],
        [0, "2026-01-01", "2026-01-01T00:00:00+00:00", None],
        [0, "2026-01-01", "2026-01-01T00:00:00+00:00"],
        {"a": 1},
        "text",
        5,
        None,
        [0, "x", "y", "z"],
    ],
)
def test_every_malformed_cursor_is_a_value_error(value: Any) -> None:
    with pytest.raises(ValueError, match="not a cursor"):
        decode_cursor(cursor(value))


@pytest.mark.parametrize("raw", ["", "!!!", "bm90IGpzb24="])
def test_text_that_is_not_base64_json_is_a_value_error(raw: str) -> None:
    with pytest.raises(ValueError, match="not a cursor"):
        decode_cursor(raw)
