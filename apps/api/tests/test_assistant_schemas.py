"""The assistant's request bodies refuse text Postgres cannot store."""

import pytest
from pydantic import ValidationError

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
