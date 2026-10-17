"""A check for Social Security and card numbers in a person's message.

Pure: no framework imports, no logging. It never records the text it reads. Stage 6's web copy will
implement the same rules, and both read `evals/assistant/personal-data-cases.json`, so they
cannot drift.
"""

import re
import unicodedata
from typing import Literal

type PersonalDataKind = Literal["ssn", "card"]

# Three digits, two, then four, joined by dashes or spaces, not part of a longer digit run.
_SSN = re.compile(r"(?<![0-9])[0-9]{3}[- ][0-9]{2}[- ][0-9]{4}(?![0-9])")
# A card number: a plausible issuer digit first (2 to 6), then either 13 to 19 digits in one run, or
# digits grouped the way cards are printed, joined by single spaces or dashes: groups of 4 (and a
# last group of 1 to 4 for 17 to 19 digits), or 4-6-5, or 4-6-4. Loose grouping would flag dates:
# "2026-10-19 2026-10-23" is 16 digits and passes the Luhn check one time in ten.
_SEP = r"[ -]"
_CARD_CANDIDATE = re.compile(
    r"(?<![0-9])(?:"
    r"[2-6][0-9]{12,18}"
    rf"|[2-6][0-9]{{3}}(?:{_SEP}[0-9]{{4}}){{2,3}}(?:{_SEP}[0-9]{{1,4}})?"
    rf"|[2-6][0-9]{{3}}{_SEP}[0-9]{{6}}{_SEP}[0-9]{{4,5}}"
    r")(?![0-9])"
)


def normalized(text: str) -> str:
    """The text as the check reads it, in the steps the web app's copy repeats (the `about` of the
    shared vectors): NFKC, drop format characters (Cf), space separators (Zs) to an ASCII space,
    and dashes (Pd) to an ASCII hyphen. Digits are then matched as ASCII only."""
    out: list[str] = []
    for char in unicodedata.normalize("NFKC", text):
        category = unicodedata.category(char)
        if category == "Cf":
            continue
        out.append(" " if category == "Zs" else "-" if category == "Pd" else char)
    return "".join(out)


def _passes_luhn(digits: str) -> bool:
    total = 0
    for index, character in enumerate(reversed(digits)):
        value = int(character)
        if index % 2 == 1:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def kind_of_personal_data(text: str) -> PersonalDataKind | None:
    """What kind of personal number `text` holds, or None. A Social Security number wins a tie."""
    text = normalized(text)
    if _SSN.search(text):
        return "ssn"
    for match in _CARD_CANDIDATE.finditer(text):
        digits = re.sub(r"[^0-9]", "", match.group())
        if 13 <= len(digits) <= 19 and _passes_luhn(digits):
            return "card"
    return None
