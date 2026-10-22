"""One rule for a denial's note, shared by the page's route and the assistant's confirm."""

import pytest

from app.modules.timeoff import schemas, service


def test_the_limit_is_defined_once() -> None:
    assert service.MAX_NOTE_CHARACTERS == 300
    assert schemas.MAX_NOTE_CHARACTERS is service.MAX_NOTE_CHARACTERS


@pytest.mark.parametrize(
    ("note", "stored"), [("  hi  ", "hi"), ("   ", ""), ("x" * 300, "x" * 300)]
)
def test_a_note_is_trimmed_and_may_be_blank(note: str, stored: str) -> None:
    assert service.checked_note(note) == stored


@pytest.mark.parametrize("note", ["x" * 301, "a\x00b", "\x00"], ids=["long", "NUL", "only NUL"])
def test_a_note_that_cannot_be_stored_is_a_value_error(note: str) -> None:
    with pytest.raises(ValueError, match="note"):
        service.checked_note(note)
