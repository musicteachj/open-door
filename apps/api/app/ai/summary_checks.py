"""Two program checks on a case summary's wording: is every clause reported speech, and does the
text judge or recommend anyway.

Both are pure. `summary_problem` (app/ai/case_summary.py) runs them on every summary before it is
stored, and the case-summary eval runs the same function. They are blunt on purpose: a summary
they refuse is stored as `failed` with the reason `checks`, and HR reads the person's own words.

**Attribution.** A summary may only report: every clause must begin as a report does ("The person
says...", "They ask...", "According to the person,..."), so a claim in the summarizer's own voice
("Sam acted inappropriately.") is refused. The summary is cut into clauses at a sentence end
(a stop, "!" or "?" before a capital letter, with or without a space, or a line break), a
semicolon, a dash, a colon, or an opening parenthesis. Each clause must be attributed on its own.
A comma never starts a clause: ", but", ", so", ", which", and ", and" continue the sentence, so
they inherit its attribution, and what they say in their own voice is left to the judgment words
below. Exceptions, each small and plain:

- text inside quotation marks is the person's own quoted words and is never cut;
- a sentence that ends with a tag such as ", they say." is attributed throughout, but only for
  reporting: if its body carries an outcome or a recommendation (a warning, termination, firing,
  discipline, "should", "recommended", "the appropriate action") it is refused as `judgment`;
- a dash followed by a lowercase preposition continues the clause ("- in the meeting");
- a colon clause with no finite verb, after an attributed clause, is the list of what they report
  ("They report two incidents: one on Tuesday and one in Building 2."), and a quoted colon clause is
  the person's quote;
- "Dr.", "Mr.", "Mrs.", "Ms.", "Prof.", and "p.m." or "a.m." before a weekday, a month, a time, or
  a lowercase word do not end a sentence (a single initial or "St." can end one, so it is cut).

**Judgment words.** As a second net, text outside quotation marks is refused if it holds a word
that judges or recommends (credible, warrants, deserves, clearly, at fault, "HR should", and the
rest below), even inside a sentence that is attributed.
"""

import re
from typing import Final

# Typographic marks, spelled by code point so no formatter turns them into plain ones.
_EN, _EM = chr(0x2013), chr(0x2014)
_LDQ, _RDQ, _LSQ, _RSQ = chr(0x201C), chr(0x201D), chr(0x2018), chr(0x2019)

# --- Reporting ---------------------------------------------------------------------------------

_REPORTING_VERBS: Final = (
    r"says?|said|writes?|wrote|describes?|described|reports?|reported|recalls?|recalled"
    r"|remembers?|remembered|thinks?|thought|believes?|believed|adds?|added|explains?|explained"
    r"|mentions?|mentioned|states?|stated|asks?|asked|notes?|noted|recounts?|recounted"
    r"|wants?|wanted|would like|knows?|feels?|felt|claims?|claimed|alleges?|alleged"
    r"|(?:has|have|had) (?:asked|told|reported|said|written|noted)"
    r"|(?:is|are) (?:not sure|unsure)"
)
_SUBJECT: Final = r"(?:the person|the employee|the writer|they)"
_CONNECTOR: Final = r"(?:(?:also|then|later|finally|first|and|but|however|so|in addition),?\s+)?"
_LEAD_IN: Final = r"(?:(?:in|on|at|during|after|before|since)\s+(?:[^\s,]+\s+){0,4}[^\s,]+,\s+)?"
_ATTRIBUTED = re.compile(
    rf"^{_CONNECTOR}{_LEAD_IN}{_CONNECTOR}"
    r"(?:according to (?:the person|the employee|the writer|them)\b"
    rf"|{_SUBJECT}\s+(?:(?:also|then|later|still|first|further|additionally)\s+)?"
    rf"(?:(?:do|does|did)\s+not\s+)?(?:{_REPORTING_VERBS})\b)",
    re.IGNORECASE,
)
_TRAILING_TAG = re.compile(
    rf",\s*{_SUBJECT}\s+(?:say|says|said|write|writes|wrote|add|adds|added|explain|explains"
    r"|explained|report|reports|reported)\s*[.!?]*$",
    re.IGNORECASE,
)
_FINITE = re.compile(
    r"\b(?:is|are|was|were|am|be|been|being|has|have|had|do|does|did|will|would|can|could"
    r"|should|must|may|might|shall)\b|\w{2,}ed\b",
    re.IGNORECASE,
)

# --- Cutting the summary into clauses ---------------------------------------------------------

_HIDDEN_CHARS: Final = ".!?;:,()-" + _EN + _EM
_HIDE: Final = {c: chr(0xE000 + i) for i, c in enumerate(_HIDDEN_CHARS)}
_SHOW: Final = {v: k for k, v in _HIDE.items()}
_QUOTED = re.compile('"[^"]*"|' + _LDQ + "[^" + _RDQ + "]*" + _RDQ)
# Only titles that never end a sentence keep their period. A single capital ("Building B.") and
# "St." can end one, so they are cut there: a name with an initial is refused, and the cost is that
# HR reads the person's own words.
_TITLE = re.compile(r"\b(?:Dr|Mr|Mrs|Ms|Mx|Prof|vs)\.", re.IGNORECASE)
_DAYS_AND_MONTHS: Final = (
    "monday|tuesday|wednesday|thursday|friday|saturday|sunday|january|february|march|april|may"
    "|june|july|august|september|october|november|december"
)
# "p.m." or "a.m." keeps its periods before a weekday, a month, a time, or a lowercase word. The
# lookahead is case-sensitive: any other capital starts a new sentence.
_CLOCK = re.compile(rf"\b(?i:[ap]\.m\.)(?=\s+(?:(?i:{_DAYS_AND_MONTHS})\b|\d|[a-z]))")
_SENTENCE_END = re.compile(
    "(?<=[.!?])[\"'" + _RDQ + _RSQ + ")\\]]*\\s+(?=[A-Z0-9\"'" + _LDQ + _LSQ + "(\\[])"
    "|\\n+"
    "|(?<=[a-z0-9\"'" + _RDQ + _RSQ + ")][.!?])(?=[A-Z])"
)
_CLAUSE_BREAK = re.compile(
    r"(?P<semi>;\s*)"
    r"|(?P<dash>\s*(?:--|[" + _EN + _EM + r"])\s*|\s+-\s+)"
    r"|(?P<colon>:\s+)"
    r"|(?P<paren>\s*\()"
)
_PREPOSITIONS = frozenset(
    {"in", "on", "at", "during", "after", "before", "from", "to", "by", "with", "for", "near"}
    | {"outside", "inside", "since", "until", "because", "as", "about", "around", "between"}
    | {"under", "over", "through", "toward", "towards", "within", "without"}
)


def _hide(match: re.Match[str]) -> str:
    return "".join(_HIDE.get(c, c) for c in match.group())


def _hide_quoted(match: re.Match[str]) -> str:
    """Cut nothing inside a quotation: hide its punctuation, except a closing stop that may end the
    sentence."""
    whole = match.group()
    inner, tail = whole[1:-1], ""
    if inner and inner[-1] in ".!?":
        inner, tail = inner[:-1], inner[-1]
    return whole[0] + "".join(_HIDE.get(c, c) for c in inner) + tail + whole[-1]


def _show(text: str) -> str:
    return "".join(_SHOW.get(c, c) for c in text)


def clauses_of(summary: str) -> list[tuple[str, str, bool]]:
    """The summary's clauses as (kind, text, tagged): the kind is how it began (`sentence`, `semi`,
    `dash`, `colon`, or `paren`; a comma never starts a clause), and `tagged` says its sentence
    ends with a tag such as ", they say." that attributes all of it."""
    masked = _QUOTED.sub(_hide_quoted, summary)
    masked = _TITLE.sub(_hide, masked)
    masked = _CLOCK.sub(_hide, masked)
    found: list[tuple[str, str, bool]] = []
    for sentence in _SENTENCE_END.split(masked):
        if not sentence.strip():
            continue
        tagged = bool(_TRAILING_TAG.search(_show(sentence).strip()))
        start, kind = 0, "sentence"
        for match in _CLAUSE_BREAK.finditer(sentence):
            if match.lastgroup == "dash":
                following = sentence[match.end() :].split(" ", 1)[0]
                if following[:1].islower() and following in _PREPOSITIONS:
                    continue
            found.append((kind, _show(sentence[start : match.start()]).strip(), tagged))
            start, kind = match.end(), str(match.lastgroup)
        found.append((kind, _show(sentence[start:]).strip(), tagged))
    return [(kind, text, tagged) for kind, text, tagged in found if text]


def unattributed(summary: str) -> bool:
    """Whether any clause of the summary is not reported speech."""
    previous_ok = False
    for kind, text, tagged in clauses_of(summary):
        bare = text.lstrip("\"'" + _LDQ + _LSQ + "([ ")
        ok = tagged or bool(_ATTRIBUTED.match(bare))
        if not ok and kind == "colon" and previous_ok:
            # What they report, listed: a quote, or a clause with no verb of its own.
            ok = _is_quoted(text) or not _FINITE.search(bare)
        if not ok:
            return True
        previous_ok = ok
    return False


def _is_quoted(text: str) -> bool:
    return bool(_QUOTED.match(text)) or text[:1] in ('"', _LDQ)


# --- Judgment words ---------------------------------------------------------------------------

_SERIOUS_NOUNS: Final = (
    "matter|issue|concern|case|problem|allegation|complaint|misconduct|violation|wrongdoing"
    "|situation|incident|behavior|harassment|discrimination"
)
_JUDGMENT = re.compile(
    r"\b(?:credib\w*|consistent|exaggerat\w*|plausib\w*|believab\w*|warrant(?:s|ed|ing)?"
    r"|deserv\w*|justif\w*|guilty|clearly|obviously|urgent\w*|escalat\w*|seriousness"
    rf"|serious (?:{_SERIOUS_NOUNS})"
    r"|(?:is|are|was|were|seems?|appears?|very|quite|extremely|most|so|too|how) serious"
    r"|at fault|prompt attention|inappropriately|(?<!as )inappropriate"
    r"|(?:un)?reliable (?:witness|account|story|claim|source|person|narrator|version)"
    r"|(?:account|story|claim|witness|statement|person|they|he|she) "
    r"(?:is|are|was|seems?|appears?) (?:\w+ )?(?:un)?reliable"
    r"|(?:should be|must be|needs to be) (?:fired|terminated|dismissed|suspended|demoted"
    r"|disciplined|escalated|investigated|interviewed|removed|let go|reprimanded|written up)"
    r"|ought to"
    r"|suggest(?:s|ed)? that (?:hr|the company|management)"
    r"|(?:hr|the company|management|the employer|the store|the manager|their manager)"
    r" (?:should|must|needs? to|has to|have to|ought to)(?! have)"
    r"|is recommended"
    r"|(?:is|would be) the appropriate (?:action|response|step|outcome)"
    r"|an investigation is (?:needed|warranted|required|necessary))\b",
    re.IGNORECASE,
)
# A sentence attributed only by a trailing tag ("..., they say.") must not carry an outcome or a
# recommendation: the tag would make a verdict on Sam read as the person's report. Blunt on purpose;
# a refused summary means HR reads the person's own words.
_OUTCOME = re.compile(
    r"\b(?:recommend\w*|advis\w*|appropriate (?:action|response|step|outcome|discipline"
    r"|consequence)s?|warnings?|(?:terminate[sd]?|terminating|termination)|fir(?:e|ed|ing)|disciplin\w*|suspen\w*|demot\w*"
    r"|should|must|ought to)\b",
    re.IGNORECASE,
)


# --- Quotations -------------------------------------------------------------------------------

_APOSTROPHES = str.maketrans({_RSQ: "'", _LSQ: "'"})


def _squash(text: str) -> str:
    """Lowercase, one apostrophe style, whitespace collapsed: how a quotation is compared."""
    return " ".join(text.translate(_APOSTROPHES).lower().split())


def misquotes(summary: str, words: str) -> bool:
    """Whether a quotation in the summary is not in the person's words. The judgment, attribution,
    and name checks leave quoted text alone because it is the person's own, so this confirms it is.
    Double quotes only, straight or curly: a single quote doubles as an apostrophe, and
    single-quoted text is not exempt from any other check, so it gets none of the leeway. Compared
    without case, with whitespace collapsed, and ignoring the quotation's own trailing . , ! ? and
    closing mark. The match is on whole words (a word boundary or the text's edge on each side),
    so a fragment can't change who acted: "he hit me" is not in "she hit me"."""
    haystack = _squash(words)
    for match in _QUOTED.finditer(summary):
        inner = _squash(match.group()[1:-1]).rstrip(".,!? ")
        if inner and not re.search(rf"(?<!\w){re.escape(inner)}(?!\w)", haystack):
            return True
    return False


def judges(summary: str) -> bool:
    """Whether the text outside quotation marks holds a word that judges or recommends, or a clause
    attributed only by a trailing tag holds an outcome or a recommendation."""
    if _JUDGMENT.search(_QUOTED.sub(" ", summary)):
        return True
    for _, text, tagged in clauses_of(summary):
        bare = text.lstrip("\"'" + _LDQ + _LSQ + "([ ")
        if tagged and not _ATTRIBUTED.match(bare) and _OUTCOME.search(_QUOTED.sub(" ", text)):
            return True
    return False
