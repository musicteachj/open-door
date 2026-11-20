"""The assistant's request bodies refuse text Postgres cannot store."""

import pytest
from pydantic import ValidationError

from app.ai.provenance import DIGITAL_SOURCE_TYPE, GENERATOR, ai_generated_out
from app.modules.assistant.display import turn_mark
from app.modules.assistant.schemas import FeedbackIn, is_storable


@pytest.mark.parametrize("text", ["a\u0000b", "a\ud800b"])
def test_a_reason_postgres_cannot_hold_is_refused(text: str) -> None:
    with pytest.raises(ValidationError):
        FeedbackIn.model_validate({"helpful": True, "reason": text})


def test_a_reason_of_ordinary_text_is_kept_trimmed() -> None:
    body = FeedbackIn.model_validate({"helpful": True, "reason": "  café \U0001f600  "})

    assert body.reason == "café \U0001f600"


def test_what_is_storable() -> None:
    assert is_storable("café \U0001f600")
    assert not is_storable("a\u0000b")
    assert not is_storable("a\ud800b")


def test_the_mark_lists_each_model_once_in_order() -> None:
    mark = ai_generated_out(["model-a", "model-b", "model-a"])

    assert mark.generator == GENERATOR
    assert mark.models == ["model-a", "model-b"]
    assert mark.digital_source_type == DIGITAL_SOURCE_TYPE


def test_a_normal_answer_is_marked_with_its_models_deduplicated() -> None:
    mark = turn_mark("completed", "You get 40 hours.", ["m1", "m2", "m1"])

    assert mark is not None
    assert mark.models == ["m1", "m2"]


@pytest.mark.parametrize("answer", ["", "   ", "\n\t "])
def test_a_blank_answer_gets_no_mark(answer: str) -> None:
    assert turn_mark("failed", answer, ["m1"]) is None


@pytest.mark.parametrize("status", ["crisis", "guard_unavailable"])
def test_a_turn_that_never_ran_the_model_gets_no_mark(status: str) -> None:
    assert turn_mark(status, "text", ["m1"]) is None
