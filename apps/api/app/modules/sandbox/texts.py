"""What a refused sandbox start says. Written by a person, never generated.

The web app shows each text as the problem's `detail` and holds no copy of its own. The owner
approved the four texts with the Stage 4 plan on 2026-11-11. Changing a word means approving it
again, and setting the date and the hash (tests/test_sandbox_texts.py checks them).
"""

import math
from typing import Final

SANDBOX_TEXTS_AUTHOR: Final = "James Littlefield (owner), approved with the Stage 4 plan"
SANDBOX_TEXTS_APPROVED_ON: Final = "2026-11-11"

# `{wait}` is filled by `wait_phrase`.
START_LIMIT_TEXT: Final = (
    "You've started several sandboxes in a short time. Please try again in {wait}, or keep using "
    "the one you have."
)
DAY_LIMIT_TEXT: Final = (
    "Open Door has started as many sandboxes as it can today. Please come back tomorrow, or watch "
    "the recorded walkthrough."
)
TURNSTILE_FAILED_TEXT: Final = "We couldn't confirm you're a person. Please try again."
TURNSTILE_UNAVAILABLE_TEXT: Final = (
    "We couldn't reach the check that keeps this demo safe. Please try again in a minute."
)

# One hash over the four texts, in this order, joined by a newline.
SANDBOX_TEXTS_SHA256: Final = "a75e090e1d16e8be35d67b1552e1e93578d92392a36694a76c744d56492fffb7"

SECONDS_PER_MINUTE = 60
MINUTES_PER_HOUR = 60


def wait_phrase(seconds: int) -> str:
    """ "1 minute", "N minutes" (under an hour, rounded up), or "about N hours" (an hour or more,
    hours rounded up)."""
    minutes = max(1, math.ceil(seconds / SECONDS_PER_MINUTE))
    if minutes < MINUTES_PER_HOUR:
        return "1 minute" if minutes == 1 else f"{minutes} minutes"
    hours = math.ceil(minutes / MINUTES_PER_HOUR)
    return "about 1 hour" if hours == 1 else f"about {hours} hours"
