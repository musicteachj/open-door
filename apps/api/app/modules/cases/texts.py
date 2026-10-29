"""The case form's fixed texts and the service's refusals. A model never writes them.

The form's bullets and the sent state are the spec's drafts ("The fixed texts"), tied to their
hashes in `tests/test_fixed_texts.py`, with an author and an approval date like the crisis text.
The crisis text that follows a crisis verdict is `app.ai.fixed_texts.CRISIS_TEXT`.
"""

from datetime import date
from typing import Final

# Fixed English names, so the text doesn't change with the server's locale.
WEEKDAYS: Final = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)
MONTHS: Final = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)

MAX_WORDS_CHARACTERS: Final = 4000
MAX_WAITING_CASES: Final = 5


def reply_by_label(day: date) -> str:
    """ "Wednesday, October 28": the form's and the sent state's wording of the reply-by date."""
    return f"{WEEKDAYS[day.weekday()]}, {MONTHS[day.month - 1]} {day.day}"


# The form's bullets, one per line, with the reply-by date left as a placeholder that the server
# fills in. The hash covers this template, so a changed word fails the hash test. The owner approved
# it on 2026-10-28. Changing a word means approving it again, then setting the date and the hash.
FORM_TEXT_TEMPLATE: Final = "\n".join(
    (
        "HR sees your name and the words below. Managers never see a case, including your own"
        " manager.",
        "Your case is stored encrypted.",
        "HR replies by {reply_by}, within 2 business days.",
        "Open Door's AI writes HR a short summary of what you send, written to be neutral, with no"
        " recommendation. Anthropic, the company that runs Open Door's AI, processes your words to"
        " write it. A person in HR reads your own words before deciding anything.",
        "If you or someone else is in danger, call 911. You can call or text 988 to reach the 988"
        " Suicide & Crisis Lifeline, or call the Employee Assistance Program at 1-800-555-0137.",
    )
)
FORM_TEXT_AUTHOR: Final = "James Littlefield (owner)"
FORM_TEXT_APPROVED_ON: str | None = "2026-10-28"
FORM_TEXT_SHA256: Final = "5184e1b01fe6c3ea23f0e315ef035b7810fbc514dfda55851635e33c614d3cb7"

# The sent state: the reply-by date and the page ("My cases" or "Cases") are filled in. For a
# crisis verdict the fixed crisis text follows it.
SENT_STATE_TEMPLATE: Final = (
    "Sent to HR. HR replies by {reply_by}. You can see its status in {where}."
)
SENT_STATE_AUTHOR: Final = "James Littlefield (owner)"
SENT_STATE_APPROVED_ON: str | None = "2026-10-28"
SENT_STATE_SHA256: Final = "53282b8a6cce4c8ec8b85fc4711542f16a3a71c233d7b4563e0b778df8171567"


def form_texts(reply_by: date) -> tuple[str, ...]:
    """The form's bullets, with the reply-by date filled in by the server."""
    filled = FORM_TEXT_TEMPLATE.replace("{reply_by}", reply_by_label(reply_by))
    return tuple(filled.split("\n"))


def split_sent_template(template: str) -> tuple[str, str]:
    """The template cut at its `{reply_by}. ` boundary into a lead and a pointer.

    Raises if the boundary is missing: a silent cut would hand the page the whole line as the lead
    and an empty pointer.
    """
    head, boundary, pointer = template.partition("{reply_by}. ")
    if not boundary:
        raise ValueError("The sent template has no '{reply_by}. ' boundary to cut at")
    return (head + boundary).rstrip(), pointer


# The template cut once, at import: a template that loses its boundary fails at startup (and in the
# test import), not on a request.
SENT_LEAD_TEMPLATE, SENT_POINTER_TEMPLATE = split_sent_template(SENT_STATE_TEMPLATE)


def _fill(template: str, reply_by: date, where: str) -> str:
    return template.replace("{reply_by}", reply_by_label(reply_by)).replace("{where}", where)


def sent_state_text(reply_by: date, *, where: str = "My cases") -> str:
    lead, pointer = sent_state_parts(reply_by, where=where)
    return f"{lead} {pointer}"


def sent_state_parts(reply_by: date, *, where: str = "My cases") -> tuple[str, str]:
    """The sent line as its lead and its pointer, both cut from the hashed template.

    The page shows the pointer as plain words and the link ("View in My cases") apart from it, so
    it needs the two sentences separately. The cut is the template's own `{reply_by}. ` boundary,
    so the parts joined by one space are exactly `sent_state_text`.
    """
    return (
        _fill(SENT_LEAD_TEMPLATE, reply_by, where),
        _fill(SENT_POINTER_TEMPLATE, reply_by, where),
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
SUMMARY_RETRY_REFUSED_TEXT: Final = "A summary can't be tried again for this case right now."
