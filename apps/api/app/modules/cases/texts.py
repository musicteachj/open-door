"""The case form's fixed texts and the service's refusals. A model never writes them.

The form's bullets and the sent state are the spec's drafts ("The fixed texts"), worded with the
owner in Stage 4 and tied to their hashes then. The crisis text that follows a crisis verdict is
`app.ai.fixed_texts.CRISIS_TEXT`.
"""

from datetime import date
from typing import Final

MAX_WORDS_CHARACTERS: Final = 4000
MAX_WAITING_CASES: Final = 5


def reply_by_label(day: date) -> str:
    """ "Wednesday, October 28": the form's and the sent state's wording of the reply-by date."""
    return f"{day:%A}, {day:%B} {day.day}"


def form_texts(reply_by: date) -> tuple[str, ...]:
    """The form's bullets, with the reply-by date filled in by the server."""
    return (
        "HR sees your name and the words below. Managers never see a case, including your own"
        " manager.",
        "Your case is stored encrypted.",
        f"HR replies by {reply_by_label(reply_by)}, within 2 business days.",
        "Open Door's AI writes HR a short summary of what you send, written to be neutral, with no"
        " recommendation. Anthropic, the company that runs Open Door's AI, processes your words to"
        " write it. A person in HR reads your own words before deciding anything.",
        "If you or someone else is in danger, call 911. You can call or text 988 to reach the 988"
        " Suicide & Crisis Lifeline, or call the Employee Assistance Program at 1-800-555-0137.",
    )


def sent_state_text(reply_by: date, *, where: str = "My cases") -> str:
    return (
        f"Sent to HR. HR replies by {reply_by_label(reply_by)}. You can see its status in {where}."
    )


WAITING_LIMIT_TEXT: Final = (
    f"You have {MAX_WAITING_CASES} cases waiting for HR. To add to one, contact the HR team"
    " directly."
)
EMPTY_WORDS_TEXT: Final = "Add your words before sending."
TOO_LONG_TEXT: Final = (
    f"{MAX_WORDS_CHARACTERS:,} of {MAX_WORDS_CHARACTERS:,} characters. Shorten it to send."
)
PERSONAL_DATA_TEXT: Final = (
    "That looks like a Social Security or card number. Please take it out before sending."
)
NOT_FOUND_TEXT: Final = "There is no such case."
TURN_NOT_FOUND_TEXT: Final = "That message can't start a case."
OWN_CASE_TEXT: Final = "You opened this case, so you can't act on it or read it here."
WORDS_NOT_READ_TEXT: Final = "Read the person's words before changing the status."
STATUS_REFUSED_TEXT: Final = "A case can't move to that status."
SUBMISSION_CONFLICT_TEXT: Final = "That form was already sent with different words."
INVALID_CATEGORY_TEXT: Final = "Choose what the case is about."
INVALID_FILTER_TEXT: Final = "That filter isn't available."
INVALID_CURSOR_TEXT: Final = "That page of the list isn't available."
