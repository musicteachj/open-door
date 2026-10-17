"""The personal-data check, against the vectors the web app's copy shares."""

import json
from pathlib import Path

import pytest

from app.ai.personal_data import kind_of_personal_data

CASES_PATH = (
    Path(__file__).resolve().parents[3] / "evals" / "assistant" / "personal-data-cases.json"
)
CASES = json.loads(CASES_PATH.read_text(encoding="utf-8"))


def test_the_shared_vectors_are_present() -> None:
    assert len(CASES["caught"]) >= 10
    assert len(CASES["passes"]) >= 10
    for case in CASES["caught"] + CASES["passes"]:
        assert set(case) == {"text", "why"}


@pytest.mark.parametrize("case", CASES["caught"], ids=lambda case: case["why"])
def test_caught(case: dict[str, str]) -> None:
    assert kind_of_personal_data(case["text"]) is not None


@pytest.mark.parametrize("case", CASES["passes"], ids=lambda case: case["why"] or "empty")
def test_passes(case: dict[str, str]) -> None:
    assert kind_of_personal_data(case["text"]) is None


def test_the_kind_is_reported() -> None:
    assert kind_of_personal_data("123-45-6789") == "ssn"
    assert kind_of_personal_data("4111 1111 1111 1111") == "card"


def test_the_check_never_logs_the_text(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("DEBUG"):
        kind_of_personal_data("123-45-6789 and 4111111111111111")
    assert caplog.records == []
