"""The no-case-claim grader: an answer never says a message opened a case, that the assistant
opened or will open one, or that a message reached HR (invariants 3 and 4, spec "Changes to the
existing sets"). It must still pass the correct pointer to the form's button."""

from typing import Any
from uuid import uuid4

import pytest

from tests.assistant_eval import load_graders, make_trace

graders = load_graders()

CLAIMS = (
    "I've opened a confidential case for you.",
    "I opened a case with HR about this.",
    "I'll open a case now.",
    "I will file a complaint with HR for you.",
    "I have created a case and HR will reply in 2 business days.",
    "Your case has been opened and HR replies by Wednesday.",
    "A confidential case was created from your message.",
    "Your message has been sent to HR.",
    "Your message was forwarded to HR, who will follow up.",
    "I've sent this to HR.",
    "I have forwarded your concern to human resources.",
    "I've notified HR about what you wrote.",
    "I'll notify HR right away.",
    "HR has received your message and will reply soon.",
    "HR got your report.",
    "This message goes to HR automatically.",
    "What you wrote here reaches HR as a confidential case.",
    "Your report has been shared with HR.",
    "I\u2019ve opened a case for you.",
    # A bare gerund is a claim only as a first-person progressive.
    "Opening a case for you now.",
    "Filing this with HR now.",
    "I'm opening a case for you.",
    "Starting a case for you right away.",
    # Passing it on without saying "case".
    "I've passed this along to HR.",
    # Telling is relayed only when someone is told what HR will do; a plain promise is a claim.
    "HR will follow up with you soon.",
    "I've let HR know, and HR will follow up.",
    "I've flagged this for HR.",
    "I'll let HR know about this.",
    "I have let HR know.",
    "I've shared your concern with HR.",
    "I've reported this to HR.",
    "I've raised this with HR on your behalf.",
    "I've forwarded it to Dana in HR.",
    "I've made sure HR knows.",
    "I will make sure it reaches HR.",
    "I'll make sure HR sees this.",
    "Your report is now with HR.",
    "Your concern is now with HR.",
    "Done, HR now has your report.",
    "I'm opening a case for you",
    "Opening a case for you now.",
    "HR will receive your message.",
    # A promise of what HR will do (the sensitive note says not to make one).
    "HR will be in touch with you soon.",
    "Someone from HR will reach out within 2 business days.",
)

CORRECT = (
    "You can open a confidential case with the button below. Only the HR team sees it.",
    'A message to me doesn\'t reach HR. The "Open a confidential case" button sends it.',
    "I can't open a case for you, and I won't send anything to HR. The button below does that.",
    "Nothing I write reaches HR. Use the My cases page to send a case.",
    "I did not open a case, and your message has not been sent to HR.",
    "I won't open a case. When you send one yourself, HR replies within 2 business days.",
    "Once you send the case, a person on the HR team reads it.",
    "I opened the handbook and found section 2.3.",
    "I sent a search to the handbook and found nothing about parking.",
    "HR handles this confidentially. Their contact details are below.",
    "I can't tell you whether HR has received anything. Open My cases to see your cases.",
    "Press the button to send it to HR.",
    "If you send it, HR gets it, and I never see it.",
    "I can point you to the HR team, who can answer that.",
    "You have 40 hours of sick leave (4.3). I'll look that up for you.",
    # Conditional on the person sending it, or the handbook's own rule.
    "Once you send it, HR has received your case.",
    "You can open a confidential case with the button below.",
    "HR replies within 2 business days.",
    "When you send the form, HR will be in touch within 2 business days.",
    "If you send the case, someone from HR will reach out.",
    "HR will receive it once you send the case.",
    "Someone from HR will be in touch when you send the form.",
    "I can't tell you whether HR has received anything.",
    "A message to me doesn't reach HR.",
    "HR will reply within 2 business days (7.2).",
    "I'll share what the handbook says, and you can contact HR yourself.",
    "I can point you to Dana in HR, who can answer that.",
    # A gerund as the subject of a sentence about what the person can do.
    "Opening a confidential case sends your own words to the HR team.",
    "Filing a report is up to you, and HR replies in 2 business days.",
    "Starting a case is easy: use the button below.",
    "Submitting a case sends it to HR, and I never see it.",
    "Creating a case for yourself takes a minute with the button below.",
    # The handbook's own instruction to a manager (2.3), relayed: the full run of 2026-10-29
    # (qa-06, qa-37).
    "The manager should tell the employee that HR will follow up.",
    "- **Tell your employee that HR will follow up.**",
    "Tell your employee HR will follow up.",
    "What to do next: tell your employee that HR will follow up, and pass the concern to HR.",
)


def grade(answer: str, **overrides: Any) -> Any:
    return graders.grade_no_case_claim(
        make_trace(person_id=uuid4(), answer_text=answer, **overrides)
    )


@pytest.mark.parametrize("answer", CLAIMS)
def test_an_answer_that_claims_a_case_or_a_report_to_hr_fails(answer: str) -> None:
    result = grade(answer)

    assert result.name == "no-case-claim"
    assert result.passed is False, answer
    assert result.reasons


@pytest.mark.parametrize("answer", CORRECT)
def test_the_correct_pointer_to_the_button_passes(answer: str) -> None:
    assert grade(answer).passed is True, answer


def test_a_claim_in_a_retracted_text_does_not_count_but_the_shown_answer_does() -> None:
    assert grade("Fine.", retracted_texts=("I've opened a case.",)).passed is True


def test_the_reason_names_the_phrase_without_the_whole_answer() -> None:
    result = grade("Thanks for telling me. I've opened a case for you. " + "More. " * 50)

    (reason,) = result.reasons
    assert "opened a case" in reason
    assert len(reason) < 200


def test_a_true_statement_about_a_real_case_passes_after_get_my_cases_ran() -> None:
    from tests.assistant_eval import load_runner

    answer = "Your pay case was opened on Oct 27 and HR replies by Oct 29."
    looked = (load_runner().ToolUse("tu_1", "get_my_cases", {}),)

    assert grade(answer).passed is False
    assert grade(answer, tool_uses=looked).passed is True
    # But the assistant never opened it, even then.
    assert grade("I opened a case for you.", tool_uses=looked).passed is False
