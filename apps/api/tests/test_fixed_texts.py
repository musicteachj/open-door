"""The fixed texts: every message the assistant shows that a model never writes."""

import hashlib
import re
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
    SENSITIVE_TEXT_APPROVED_ON,
    SENSITIVE_TEXT_AUTHOR,
    SENSITIVE_TEXT_SHA256,
    UNAVAILABLE_TEXT,
    UNAVAILABLE_TEXT_APPROVED_ON,
    UNAVAILABLE_TEXT_AUTHOR,
    UNAVAILABLE_TEXT_SHA256,
)
from app.modules.cases import texts as case_texts

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


def test_the_sensitive_text_is_the_specs_panel_text() -> None:
    assert SENSITIVE_TEXT == (
        "This sounds like something a person on the HR team should help with. You can open a "
        "confidential case below. Only the HR team can open it in Open Door, never your manager, "
        "and it's stored encrypted. HR replies within 2 business days. Their contact details are "
        "below."
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


def test_the_composers_two_refusals_keep_their_words() -> None:
    """The web app shows these from `GET /assistant/texts`, and the API sends them as problems."""
    assert fixed_texts.PERSONAL_DATA_TEXT == (
        "That looks like a Social Security or card number. Please take it out; I can't take those."
    )
    assert fixed_texts.STILL_ANSWERING_TEXT == "I'm still answering your last question."


# --- The Phase 6 texts: the sensitive panel, the case form, and the sent line -------------------
#
# The owner approves each (spec, "The fixed texts"). Until then the date is None and the hash is
# pinned, so these tests fail on a changed word at once and on a missing date until approval.

# Promises none of these texts may make (spec, "What the texts must not say"): that the AI won't
# read it, that the case is anonymous, that no one outside HR processes it, or any outcome.
FORBIDDEN_PROMISES = (
    r"\bAI (will not|won't|doesn't|does not|never) (read|see|look)",
    r"\bwon't (be )?(read|seen) by (the )?AI",
    r"\bno AI\b",
    r"\banonymous",
    r"\bno one (outside|but|except)",
    r"\bnobody (outside|but|except)",
    r"\bonly (the )?HR (ever )?(sees|reads|processes|handles)",
    r"\boutcome",
    r"\binvestigat",
    r"\bresolv",
    r"\bdiscipline",
    r"\bwill be (dealt|taken|handled|addressed)",
    r"\baction (will|is going to) be",
)


def promises_found(text: str) -> list[str]:
    return [p for p in FORBIDDEN_PROMISES if re.search(p, text, re.IGNORECASE)]


def phase_6_texts() -> dict[str, str]:
    return {
        "panel": SENSITIVE_TEXT,
        "form": case_texts.FORM_TEXT_TEMPLATE,
        "sent": case_texts.SENT_STATE_TEMPLATE,
    }


def test_the_promise_scan_catches_each_forbidden_kind() -> None:
    for bad in (
        "The AI won't read what you write.",
        "Your case is anonymous.",
        "No one outside HR will ever see it.",
        "We will investigate and the matter will be resolved.",
        "The outcome is up to HR.",
    ):
        assert promises_found(bad), bad
    # The approved sentences about what the AI does are not promises of silence.
    assert promises_found("Open Door's AI writes HR a short summary of what you send.") == []


def test_no_phase_6_text_makes_a_forbidden_promise() -> None:
    for name, text in phase_6_texts().items():
        assert promises_found(text) == [], name


def test_no_phase_6_text_has_an_em_dash() -> None:
    for name, text in phase_6_texts().items():
        assert "\u2014" not in text, name


def test_the_form_template_has_only_the_reply_date_filled_in_by_the_server() -> None:
    assert case_texts.FORM_TEXT_TEMPLATE.count("{reply_by}") == 1
    filled = "\n".join(case_texts.form_texts(date(2026, 10, 28)))
    assert filled == case_texts.FORM_TEXT_TEMPLATE.replace("{reply_by}", "Wednesday, October 28")
    assert "{" not in filled


def test_the_sent_template_has_only_the_reply_date_and_the_place_filled_in() -> None:
    sent = case_texts.sent_state_text(date(2026, 10, 28))
    assert sent == (
        "Sent to HR. HR replies by Wednesday, October 28. You can see its status in My cases."
    )
    assert case_texts.sent_state_text(date(2026, 10, 28), where="Cases").endswith("in Cases.")
    assert case_texts.SENT_STATE_TEMPLATE.count("{") == 2


def test_each_phase_6_text_matches_its_pinned_hash() -> None:
    pinned = {
        "panel": SENSITIVE_TEXT_SHA256,
        "form": case_texts.FORM_TEXT_SHA256,
        "sent": case_texts.SENT_STATE_SHA256,
    }
    for name, text in phase_6_texts().items():
        message = f"The {name} text changed: the owner approves it again, then the hash is reset."
        assert pinned[name] is not None, message
        assert hashlib.sha256(text.encode()).hexdigest() == pinned[name], message


def test_every_phase_6_text_has_an_author_and_an_approval_date() -> None:
    """The gate: red until the owner approves the wording and the dates are filled in."""
    approvals = {
        "panel": (SENSITIVE_TEXT_AUTHOR, SENSITIVE_TEXT_APPROVED_ON),
        "form": (case_texts.FORM_TEXT_AUTHOR, case_texts.FORM_TEXT_APPROVED_ON),
        "sent": (case_texts.SENT_STATE_AUTHOR, case_texts.SENT_STATE_APPROVED_ON),
    }
    for name, (author, approved_on) in approvals.items():
        message = f"The {name} text isn't approved: the owner approves it, then its date is set."
        assert author, message
        assert approved_on is not None, message
        date.fromisoformat(approved_on)
