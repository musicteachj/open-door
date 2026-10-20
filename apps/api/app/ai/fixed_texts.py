"""Every message the assistant shows that a model never writes.

The crisis text, the sensitive stub, "can't answer right now", and the error messages are fixed
constants. The web app gets them only from stream events, never from its own copy. The voice is the
design brief's: calm, plain, never cute.
"""

from dataclasses import dataclass
from typing import Final

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Location, Person

# Source: 988 Suicide & Crisis Lifeline, https://988lifeline.org, read on 2026-10-15 ("Your conversations are free and confidential."; "The 988 Lifeline is available 24/7/365."; call or text 988, chat at https://chat.988lifeline.org). 911 and the EAP follow handbook section 6.2.  # noqa: E501
CRISIS_TEXT: Final = """\
I'm an AI assistant, and what you wrote sounds serious, so I want to make sure you can reach a person right now.

- If you or someone else is in immediate danger, call 911.
- Call or text 988 to reach the 988 Suicide & Crisis Lifeline, or chat at chat.988lifeline.org. It's free, confidential, and available 24/7.
- The Juniper Row Employee Assistance Program (EAP) offers free, confidential counseling, 24 hours a day: 1-800-555-0137.
- You can also talk to someone on the HR team. Their contact details are below.

You don't have to go through this alone."""  # noqa: E501

# Changing a word of the crisis text means the owner approves it again: set the date and the hash.
CRISIS_TEXT_AUTHOR: Final = "James Littlefield (owner)"
CRISIS_TEXT_APPROVED_ON: str | None = "2026-10-15"
CRISIS_TEXT_SHA256: str | None = "99234f819d1e54f0f68a15cff8663a17577706246e555f7566044f81748a34a2"

SENSITIVE_TEXT: Final = (
    "A person on the HR team should help with this, and they handle it confidentially. "
    "Their contact details are below."
)

# Approved by the owner like the crisis text: a failed guard can't tell a crisis from anything else
# (ADR 0009), so this text also gives 911 and 988. Changing a word means approving it again.
UNAVAILABLE_TEXT: Final = (
    "I'm an AI assistant, and I can't answer right now. Please try again in a moment. If you or "
    "someone else is in danger, call 911, or call or text 988 to reach the 988 Suicide & Crisis "
    "Lifeline. For anything else that can't wait, the HR team can help directly. Their contact "
    "details are below."
)
UNAVAILABLE_TEXT_AUTHOR: Final = "James Littlefield (owner)"
UNAVAILABLE_TEXT_APPROVED_ON: str | None = "2026-10-15"
UNAVAILABLE_TEXT_SHA256: str | None = (
    "1f00bfe3f36e4f7c142ad7c6119559db83a13b514cc3322606e2fab874ac9919"
)

# A budget stop happens before the safety check, so the message was never screened and may be a
# crisis: these two texts give 911 and 988 like the "can't answer right now" text (ADR 0009). Stage
# 4's 429 budget banner uses these same texts. Approved by the owner; changing a word means
# approving it again, and setting its hash.
BUDGET_SANDBOX_TEXT: Final = (
    "This demo sandbox has reached its limit for the assistant. A new sandbox starts fresh. "
    "If you or someone else is in danger, call 911, or call or text 988 to reach the 988 "
    "Suicide & Crisis Lifeline."
)
BUDGET_DAILY_TEXT: Final = (
    "The demo's daily limit for the assistant has been reached. Please try again tomorrow. "
    "If you or someone else is in danger, call 911, or call or text 988 to reach the 988 "
    "Suicide & Crisis Lifeline."
)
BUDGET_TEXTS_AUTHOR: Final = "James Littlefield (owner)"
BUDGET_TEXTS_APPROVED_ON: str = "2026-10-15"
BUDGET_SANDBOX_TEXT_SHA256: str = "6a3fc6f7b20c4e316e2830de9d354baad1ce6b3083a58606363747aa6a7e8635"
BUDGET_DAILY_TEXT_SHA256: str = "23fa3acad35801765fb94c2999da280328d812b779b011d44fcb5226f3b901fd"

# The two refusals the composer shows before a request is sent (and the API sends as problems),
# from `GET /assistant/texts`, so the web app holds no copy of them. Not model text, and not a
# safety message: they carry no 911 or 988 wording.
PERSONAL_DATA_TEXT: Final = (
    "That looks like a Social Security or card number. Please take it out; I can't take those."
)
STILL_ANSWERING_TEXT: Final = "I'm still answering your last question."

ERROR_TEXTS: Final[dict[str, str]] = {
    "refusal": (
        "I can't help with that one. If you need an answer, the HR team can help. "
        "You can find them in the directory."
    ),
    "model-unavailable": (
        "I can't reach the assistant service right now. Please try again in a moment, or ask "
        "the HR team directly."
    ),
    "budget-sandbox": BUDGET_SANDBOX_TEXT,
    "budget-daily": BUDGET_DAILY_TEXT,
    # Anthropic's Console spend limit, not the product's own cap. The owner chose to reuse the
    # approved daily text for it, so there are no new words to approve.
    "spend-limit": BUDGET_DAILY_TEXT,
    "too-many-calls": (
        "That question took more steps than I can take in one turn. Try asking it in a "
        "smaller piece, or ask the HR team."
    ),
    "internal": (
        "Something went wrong on our side, and I couldn't finish that. Please try again, or "
        "ask the HR team."
    ),
}


@dataclass(frozen=True)
class HrContact:
    name: str
    work_email: str
    job_title: str | None
    location_name: str | None

    def to_json(self) -> dict[str, str | None]:
        return {
            "name": self.name,
            "workEmail": self.work_email,
            "jobTitle": self.job_title,
            "locationName": self.location_name,
        }


async def hr_contact(db: AsyncSession) -> list[HrContact]:
    """The HR team's names, work emails, job titles, and offices. Row-level security limits it to
    the caller's tenant. These are directory fields every member of the sandbox already sees.

    The directory has no active flag in this phase, so every HR administrator in the tenant counts.
    """
    rows = await db.execute(
        select(
            Person.given_name,
            Person.family_name,
            Person.work_email,
            Person.title,
            Location.name,
        )
        .join(
            Location,
            (Location.tenant_id == Person.tenant_id) & (Location.id == Person.location_id),
        )
        .where(Person.is_hr_admin.is_(True))
        .order_by(Person.family_name, Person.given_name, Person.id)
    )
    return [
        HrContact(f"{given} {family}", email, title, location)
        for given, family, email, title, location in rows
    ]
