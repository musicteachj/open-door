"""The fixed texts: every message the assistant shows that a model never writes."""

import hashlib
from datetime import date

from app.ai import fixed_texts
from app.ai.fixed_texts import (
    BUDGET_DAILY_TEXT,
    BUDGET_DAILY_TEXT_SHA256,
    BUDGET_SANDBOX_TEXT,
    BUDGET_SANDBOX_TEXT_SHA256,
    BUDGET_TEXTS_APPROVED_ON,
    BUDGET_TEXTS_AUTHOR,
    CRISIS_TEXT,
    CRISIS_TEXT_APPROVED_ON,
    CRISIS_TEXT_SHA256,
    ERROR_TEXTS,
    SENSITIVE_TEXT,
    UNAVAILABLE_TEXT,
    UNAVAILABLE_TEXT_APPROVED_ON,
    UNAVAILABLE_TEXT_AUTHOR,
    UNAVAILABLE_TEXT_SHA256,
)

# The error codes of the stream's `error` event (spec, "The stream").
ERROR_CODES = {
    "refusal",
    "model-unavailable",
    "budget-sandbox",
    "budget-daily",
    "spend-limit",
    "too-many-calls",
    "internal",
}


def test_every_fixed_text_is_a_nonempty_module_level_string() -> None:
    names = ("CRISIS_TEXT", "SENSITIVE_TEXT", "UNAVAILABLE_TEXT")
    for name in names:
        value = vars(fixed_texts)[name]
        assert isinstance(value, str)
        assert value.strip()
    assert set(ERROR_TEXTS) == ERROR_CODES
    for text in ERROR_TEXTS.values():
        assert isinstance(text, str)
        assert text.strip()


def test_the_error_texts_cover_exactly_the_streams_codes() -> None:
    assert set(ERROR_TEXTS) == ERROR_CODES


def test_the_crisis_text_has_what_the_spec_requires() -> None:
    assert "call or text 988" in CRISIS_TEXT.lower()
    for required in (
        "chat.988lifeline.org",
        "911",
        "1-800-555-0137",
        "I'm an AI assistant",
    ):
        assert required in CRISIS_TEXT
    lines = {line for line in CRISIS_TEXT.splitlines()}
    (lifeline,) = [line for line in lines if "988 Suicide" in line]
    (eap,) = [line for line in lines if "Employee Assistance" in line]
    assert "24/7" in lifeline
    assert "24 hours a day" in eap


def test_the_crisis_text_leaves_the_hr_contact_to_the_event() -> None:
    # It varies by sandbox, and the text's hash must stay fixed.
    assert "@" not in CRISIS_TEXT


def test_the_sensitive_and_unavailable_texts_point_to_the_hr_team_below() -> None:
    assert "HR team" in SENSITIVE_TEXT
    assert "contact details are below" in SENSITIVE_TEXT
    assert "HR team" in UNAVAILABLE_TEXT
    assert "contact details are below" in UNAVAILABLE_TEXT
    assert "can't answer right now" in UNAVAILABLE_TEXT


def test_911_is_the_first_bullet_of_the_crisis_text() -> None:
    bullets = [line for line in CRISIS_TEXT.splitlines() if line.startswith("- ")]
    assert "call 911" in bullets[0]


def test_the_guard_down_text_gives_911_and_988() -> None:
    # A failed guard can't tell a crisis from anything else (ADR 0009).
    assert "call 911" in UNAVAILABLE_TEXT
    assert "call or text 988" in UNAVAILABLE_TEXT
    assert "988 Suicide & Crisis Lifeline" in UNAVAILABLE_TEXT


def test_no_fixed_text_has_an_em_dash() -> None:
    for text in (CRISIS_TEXT, SENSITIVE_TEXT, UNAVAILABLE_TEXT, *ERROR_TEXTS.values()):
        assert "\u2014" not in text


def test_the_sensitive_text_hands_over_to_a_person() -> None:
    assert SENSITIVE_TEXT == (
        "A person on the HR team should help with this, and they handle it confidentially. "
        "Their contact details are below."
    )


def test_the_budget_texts_say_which_limit_was_reached() -> None:
    assert "sandbox" in ERROR_TEXTS["budget-sandbox"]
    assert "reached its limit" in ERROR_TEXTS["budget-sandbox"]
    assert "tomorrow" in ERROR_TEXTS["budget-daily"]


def test_the_crisis_text_is_approved() -> None:
    message = (
        "The crisis text isn't approved: the owner edits it, then sets CRISIS_TEXT_APPROVED_ON "
        "and CRISIS_TEXT_SHA256."
    )
    assert CRISIS_TEXT_APPROVED_ON is not None, message
    assert CRISIS_TEXT_SHA256 is not None, message
    date.fromisoformat(CRISIS_TEXT_APPROVED_ON)
    assert hashlib.sha256(CRISIS_TEXT.encode()).hexdigest() == CRISIS_TEXT_SHA256, message


def test_the_guard_down_text_is_approved() -> None:
    message = (
        "The guard-down text isn't approved: the owner edits it, then sets "
        "UNAVAILABLE_TEXT_APPROVED_ON and UNAVAILABLE_TEXT_SHA256."
    )
    assert UNAVAILABLE_TEXT_AUTHOR
    assert UNAVAILABLE_TEXT_APPROVED_ON is not None, message
    assert UNAVAILABLE_TEXT_SHA256 is not None, message
    date.fromisoformat(UNAVAILABLE_TEXT_APPROVED_ON)
    assert hashlib.sha256(UNAVAILABLE_TEXT.encode()).hexdigest() == UNAVAILABLE_TEXT_SHA256, message


def test_the_budget_texts_are_the_approved_words() -> None:
    assert BUDGET_SANDBOX_TEXT == (
        "This demo sandbox has reached its limit for the assistant. A new sandbox starts fresh. "
        "If you or someone else is in danger, call 911, or call or text 988 to reach the 988 "
        "Suicide & Crisis Lifeline."
    )
    assert BUDGET_DAILY_TEXT == (
        "The demo's daily limit for the assistant has been reached. Please try again tomorrow. "
        "If you or someone else is in danger, call 911, or call or text 988 to reach the 988 "
        "Suicide & Crisis Lifeline."
    )
    assert ERROR_TEXTS["budget-sandbox"] == BUDGET_SANDBOX_TEXT
    assert ERROR_TEXTS["budget-daily"] == BUDGET_DAILY_TEXT
    # The Console spend limit has its own code and reuses the approved daily text, unchanged.
    assert ERROR_TEXTS["spend-limit"] == BUDGET_DAILY_TEXT


def test_each_budget_text_gives_911_and_988() -> None:
    # A budget stop happens before the safety check, so the message was never screened.
    for text in (BUDGET_SANDBOX_TEXT, BUDGET_DAILY_TEXT):
        assert "call 911" in text
        assert "call or text 988" in text


def test_the_sandbox_budget_text_is_approved() -> None:
    message = (
        "The sandbox budget text isn't approved: the owner edits it, then sets "
        "BUDGET_TEXTS_APPROVED_ON and BUDGET_SANDBOX_TEXT_SHA256."
    )
    assert BUDGET_TEXTS_AUTHOR
    date.fromisoformat(BUDGET_TEXTS_APPROVED_ON)
    assert hashlib.sha256(BUDGET_SANDBOX_TEXT.encode()).hexdigest() == BUDGET_SANDBOX_TEXT_SHA256, (
        message
    )


def test_the_daily_budget_text_is_approved() -> None:
    message = (
        "The daily budget text isn't approved: the owner edits it, then sets "
        "BUDGET_TEXTS_APPROVED_ON and BUDGET_DAILY_TEXT_SHA256."
    )
    assert BUDGET_TEXTS_AUTHOR
    date.fromisoformat(BUDGET_TEXTS_APPROVED_ON)
    assert hashlib.sha256(BUDGET_DAILY_TEXT.encode()).hexdigest() == BUDGET_DAILY_TEXT_SHA256, (
        message
    )
