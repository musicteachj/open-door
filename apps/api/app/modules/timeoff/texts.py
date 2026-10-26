"""The fixed sentence for each reason a time-off action is refused.

A person reads these, so a person wrote them: one plain sentence per code, with no figures (the
engine's answer carries those) and no pronouns for anyone else. The problem's `detail` is the
sentence, and the model never writes it. A test makes sure every code the service can return has
one.
"""

REFUSAL_TEXTS: dict[str, str] = {
    # The engine's problem codes.
    "no-scheduled-days": (
        "None of those days are scheduled workdays, or each one is a company holiday, "
        "so there is nothing to request."
    ),
    "too-long": "A request covers a limited number of days, so a longer leave goes through HR.",
    "out-of-range": (
        "These dates can't be requested: PTO can't start in the past, before the balance began, "
        "or before the hire date, sick time can't start too far back or before the hire date, "
        "and neither can end after next year."
    ),
    "bad-partial": (
        "A partial day can only be requested for a single day: a half day for PTO, "
        "or whole hours for sick time."
    ),
    "overlaps": "Some of those days are already covered by another request.",
    "not-enough": "There isn't enough time available for this request.",
    # The service's own codes.
    "no-approver": (
        "Your PTO needs a manager's approval, and no manager is on file for you, "
        "so please contact HR."
    ),
    "not-found": "That request could not be found.",
    "not-allowed": "That action isn't open to you on this request.",
    "status-changed": "This request has changed since the page was loaded, so refresh to see it.",
    "already-started": "This request has already started, so it can't be canceled.",
}


def refusal_text(code: str) -> str:
    """The sentence for `code`. An unknown code is a bug, so it raises KeyError."""
    return REFUSAL_TEXTS[code]
