"""Reading an answer the way a person would, and the one check on it the app and the evals share.

`says_not_found` reads a finished answer and says whether it tells the person the handbook doesn't
cover their question. The assistant eval's `unanswerable` grader uses it, and so does the turn, to
label a console row `not_found` (Phase 7). It was moved here from the evals so the app doesn't
import test code, and the evals import it back: the patterns live in this file alone.

Pure: no database, no network, no clock.
"""

import re
import unicodedata

# Dashes other than "-": hyphen, non-breaking hyphen, figure dash, en dash, em dash, horizontal bar,
# minus sign, and the small and fullwidth hyphens. Written as code points so no file has to hold
# them as characters.
_DASH_CODE_POINTS = (0x2010, 0x2011, 0x2012, 0x2013, 0x2014, 0x2015, 0x2212, 0xFE58, 0xFE63, 0xFF0D)
_DASH_TABLE = {code: "-" for code in _DASH_CODE_POINTS}


def normalize(text: str) -> str:
    """The text as a reader sees it: compatibility forms folded (fullwidth digits, the no-break
    space), format characters removed (zero-width spaces and joiners, the soft hyphen, directional
    marks: they hide a value from an exact match and are invisible anyway), and every kind of
    dash made a plain hyphen."""
    folded = unicodedata.normalize("NFKC", text)
    visible = "".join(char for char in folded if unicodedata.category(char) != "Cf")
    return visible.translate(_DASH_TABLE)


# The curly and modifier apostrophes a model's typography may use, as code points so that no
# formatter or linter has to read them as characters.
STRAIGHT_APOSTROPHES = {0x2019: "'", 0x2018: "'", 0x02BC: "'"}


# A not-found statement, in one sentence (no full stop, question mark, or exclamation mark between
# its parts): "I couldn't find that in the handbook", and close paraphrases ("I could not find
# anything in the handbook on that", "I can't see a rule in the employee handbook"). It is
#   - a negative ("couldn't", "could not", "can't", "cannot", "didn't", "did not", "don't", "do
#     not"), then "find", "see", or "locate" within 50 characters; or "wasn't able to", "was not
#     able to", "not able to", or "unable to", then "find" or "locate";
#   - then "in the handbook" ("in our handbook", "in the employee handbook", "in the Juniper Row
#     handbook": up to three words between "in" and "handbook") within 50 characters.
# It is the assistant's own statement, never about the reader: "you" may not stand directly before
# the negative ("you can't find") or between the negative and the verb ("I don't have it, but you
# can find it in the handbook"). "I found it in the handbook" is not this either.
# Where a sentence ends: a ., !, or ? followed by space and a capital letter, or by the end of the
# text. A dot inside "4.3" or "e.g. foo" is not an end.
_SENTENCE_END = r"[.!?](?=\s+(?-i:[A-Z])|\s*$)"
_SAME_SENTENCE = rf"(?:(?!{_SENTENCE_END}).)"
_IN_THE_HANDBOOK = r"\bin (?:[\w'-]+ ){0,3}handbook\b"
_NOT_FOUND = re.compile(
    r"\b(?P<negative>(?:couldn't|could not|can't|cannot|didn't|did not|don't|do not)\b"
    rf"{_SAME_SENTENCE}{{0,50}}?\b(?:find|see|locate)\b"
    r"|(?:wasn't able to|was not able to|not able to|unable to)\s+(?:find|locate)\b)"
    # Up to 80 characters between "find" and "in the handbook", in the same sentence: room for
    # "anything about parking validation or paying for parking" (the smoke run, 2026-10-25).
    rf"{_SAME_SENTENCE}{{0,80}}?{_IN_THE_HANDBOOK}",
    re.IGNORECASE,
)
# The handbook named first: "I searched the handbook twice and couldn't find anything about it"
# (the full run of 2026-10-29). The assistant's own search, then a negative find, in one sentence.
_SEARCHED_NOT_FOUND = re.compile(
    r"\bI(?:'ve| have)?\s+(?:searched|looked through|looked in|checked)\s+(?:[\w'-]+ ){0,3}"
    rf"handbook\b{_SAME_SENTENCE}{{0,60}}?\b(?:couldn't|could not|didn't|did not)\s+"
    r"(?:find|see|turn up|locate)\b",
    re.IGNORECASE,
)
_YOU = re.compile(r"\byou\b", re.IGNORECASE)
_YOU_JUST_BEFORE = re.compile(r"\byou\s$", re.IGNORECASE)


def says_not_found(text: str) -> bool:
    """Whether the text says it couldn't find the answer in the handbook (see `_NOT_FOUND`). Case
    is kept, because a capital letter after a full stop is what ends a sentence."""
    plain = " ".join(normalize(text).translate(STRAIGHT_APOSTROPHES).split())
    return bool(_SEARCHED_NOT_FOUND.search(plain)) or any(
        not _YOU.search(match.group("negative"))
        and not _YOU_JUST_BEFORE.search(plain[: match.start("negative")])
        for match in _NOT_FOUND.finditer(plain)
    )
