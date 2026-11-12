import hashlib

import pytest

from app.modules.sandbox import texts


def test_the_four_texts_are_approved_and_unchanged() -> None:
    joined = "\n".join(
        [
            texts.START_LIMIT_TEXT,
            texts.DAY_LIMIT_TEXT,
            texts.TURNSTILE_FAILED_TEXT,
            texts.TURNSTILE_UNAVAILABLE_TEXT,
        ]
    )
    assert texts.SANDBOX_TEXTS_APPROVED_ON == "2026-11-11"
    assert "James Littlefield" in texts.SANDBOX_TEXTS_AUTHOR
    assert hashlib.sha256(joined.encode()).hexdigest() == texts.SANDBOX_TEXTS_SHA256, (
        "A text changed. Get the owner's approval, then set the date and the hash."
    )


def test_no_text_has_an_em_dash() -> None:
    for value in (texts.START_LIMIT_TEXT, texts.DAY_LIMIT_TEXT, texts.TURNSTILE_FAILED_TEXT):
        assert chr(0x2014) not in value


@pytest.mark.parametrize(
    ("seconds", "phrase"),
    [
        (1, "1 minute"),
        (59, "1 minute"),
        (60, "1 minute"),
        (61, "2 minutes"),
        (12 * 60, "12 minutes"),
        (59 * 60, "59 minutes"),
        (59 * 60 + 1, "about 1 hour"),
        (60 * 60, "about 1 hour"),
        (61 * 60, "about 2 hours"),
        (3 * 3600, "about 3 hours"),
    ],
)
def test_the_wait_phrase_rounds_up(seconds: int, phrase: str) -> None:
    assert texts.wait_phrase(seconds) == phrase
