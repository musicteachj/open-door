"""The case summary's plumbing: the request, the summarizer interface, and the program checks.

A case's words are the most sensitive text in the product, so the summary call is built to know as
little as possible: the category and the words, in one message, with no tools. The words sit only
inside an untrusted-text tag whose own name is escaped in them. The call is a `Summarizer`, not a
`Transport` method: a second interface keeps the many `Transport` fakes untouched, and the lifespan
builds it like the embedder. This stage has the scripted and replay versions; the Anthropic version
and the prompt arrive with Stage 4.

`summary_problem` runs on every summary before it is stored, whoever wrote it.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Final, Protocol

from app.ai.pricing import Usage
from app.ai.text import neutralize

# The words go inside this tag, as untrusted data.
SUMMARY_WORDS_TAG: Final = "case_words"
# The conversation model's pin (`CURRENT_PINS.model`; a test holds them equal). Not imported: this
# module must load without the database layer.
SUMMARY_MODEL: Final = "claude-opus-5-5"
SUMMARY_EFFORT: Final = "low"
SUMMARY_TIMEOUT_SECONDS: Final = 30
SUMMARY_MAX_TOKENS: Final = 1024  # Thinking counts toward this.
# The spec asks for about 120 words; a summary over this is stored as failed.
SUMMARY_MAX_WORDS: Final = 150

SCRIPTED_PROMPT_VERSION: Final = "scripted-1"

SUMMARY_OUTPUT_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {"summary": {"type": "string"}},
    "required": ["summary"],
    "additionalProperties": False,
}

CATEGORY_LABELS: Final = {
    "harassment_discrimination": "harassment or discrimination",
    "safety": "workplace safety",
    "medical_accommodation": "a medical need or accommodation",
    "pay": "a pay concern",
    "other": "something else",
}


@dataclass(frozen=True)
class SummaryRequest:
    """The one summary call, ready to send. The words are in `messages` and nowhere else."""

    category: str
    messages: tuple[dict[str, Any], ...] = field(repr=False)
    timeout_seconds: int
    model: str = SUMMARY_MODEL
    effort: str = SUMMARY_EFFORT
    max_tokens: int = SUMMARY_MAX_TOKENS
    # Always empty: the model never opens, reads, or ranks a case.
    tools: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class SummaryAnswer:
    text: str = field(repr=False)
    model: str
    prompt_version: str
    usage: Usage


class SummaryUnavailable(Exception):  # noqa: N818
    """The summary call failed. `usage` is None when the cost is unknown."""

    def __init__(self, message: str = "", *, usage: Usage | None = None) -> None:
        super().__init__(message)
        self.usage = usage


class SummaryRefused(Exception):  # noqa: N818
    """The model declined to write a summary. `usage` is what the call used, if known."""

    def __init__(self, message: str = "", *, usage: Usage | None = None) -> None:
        super().__init__(message)
        self.usage = usage


class Summarizer(Protocol):
    async def summarize(self, request: SummaryRequest) -> SummaryAnswer: ...


def build_summary_request(category: str, words: str) -> SummaryRequest:
    """The request for a category and the person's words, and nothing else: no name, directory, or
    conversation. The tag is escaped in the words so they cannot close it."""
    tag = SUMMARY_WORDS_TAG
    label = CATEGORY_LABELS.get(category, CATEGORY_LABELS["other"])
    # The category line is the server's own text, outside the untrusted tag.
    content = f"Category: {label}\n<{tag}>{neutralize(words, (tag,))}</{tag}>"
    return SummaryRequest(
        category=category,
        messages=({"role": "user", "content": content},),
        timeout_seconds=SUMMARY_TIMEOUT_SECONDS,
    )


def summary_api_kwargs(request: SummaryRequest) -> dict[str, Any]:
    """The call as plain JSON-able data: what a replay fingerprints (and, in Stage 4, what is
    sent)."""
    return {
        "model": request.model,
        "max_tokens": request.max_tokens,
        "messages": list(request.messages),
        "tools": list(request.tools),
        "output_config": {
            "effort": request.effort,
            "format": {"type": "json_schema", "schema": SUMMARY_OUTPUT_SCHEMA},
        },
    }


# --- The program checks -----------------------------------------------------------------------

# Phrases that recommend an action or outcome, or judge credibility or seriousness. Ordinary
# descriptive words (fire, must, dismissed) are left out: a neutral summary may report them.
# Stage 4 tunes the list against the case-summary set.
_RECOMMENDING = re.compile(
    r"\b(?:recommend\w*|advis\w*|ought to|appropriate action"
    r"|suggest\w* that (?:hr|the company)"
    r"|hr (?:should|must|needs? to)"
    r"|(?:should|must|ought to) be"
    r" (?:fired|terminated|dismissed|suspended|disciplined|investigated)"
    r"|credib\w*|believab\w*|exaggerat\w*|seriousness"
    r"|(?:seems?|sounds?|appears?) (?:very |quite )?(?:a )?serious"
    r"|is (?:a )?(?:very |quite )?serious (?:complaint|case|matter|allegation|concern)"
    r"|takes? (?:this|it) seriously)\b",
    re.IGNORECASE,
)
_LINK = re.compile(r"https?://|www\.|\b[\w-]+\.(?:com|org|net|gov|edu|io|co)\b", re.IGNORECASE)
_PHONE = re.compile(
    r"\+\d[\d\s().-]{7,}\d"  # an international number
    r"|\(?\b\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}\b"  # 303-555-0100, (303) 555 0100
    r"|\b\d{3}[\s.-]\d{4}\b"  # 555-0100
    r"|\b\d{10,}\b"
)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_MARKDOWN = re.compile(r"`|\*\*|__|~~|\]\(|^\s{0,3}(?:#{1,6}\s|[-*+]\s|>|\d+[.)]\s)", re.MULTILINE)
_WORD = re.compile(r"\b[A-Za-z][A-Za-z'\u2019-]*\b")
# Capitalized words a summary may use that the person's words need not hold.
_ALLOWED_CAPITALIZED: Final = frozenset(
    {"hr", "ai", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}
    | {"january", "february", "march", "april", "may", "june", "july", "august", "september"}
    | {"october", "november", "december"}
)
# What may precede a sentence's first word: the start, a stop, a colon, a semicolon, or a line
# break, with spaces and opening quotes or brackets skipped.
_SENTENCE_STOPS = ".!?:;\n"
_SKIPPED_BEFORE_WORD = " \t\r\n\"'\u201c\u2018(["


def _token(word: str) -> str:
    """A whole word, lowercased, without a possessive ending."""
    lowered = word.lower()
    for ending in ("'s", "\u2019s"):
        lowered = lowered.removesuffix(ending)
    return lowered


def _starts_sentence(text: str, index: int) -> bool:
    """Whether the word at `index` follows the start or a stop, past spaces, quotes, brackets."""
    i = index - 1
    while i >= 0 and text[i] in _SKIPPED_BEFORE_WORD:
        if text[i] == "\n":
            return True
        i -= 1
    return i < 0 or text[i] in _SENTENCE_STOPS


def _invented_name(summary: str, words: str) -> bool:
    """Whether a whole word that starts with a capital and starts no sentence is missing from the
    words: a name the person never wrote. Conservative on purpose, and simple: Stage 4 tunes it."""
    written = {_token(word) for word in _WORD.findall(words)}
    for match in _WORD.finditer(summary):
        if not match.group()[0].isupper():
            continue
        word = _token(match.group())
        if word in written or word in _ALLOWED_CAPITALIZED:
            continue
        if not _starts_sentence(summary, match.start()):
            return True
    return False


def summary_problem(summary: str, words: str) -> str | None:
    """The first program check the summary fails, by name, or None when it passes. Pure."""
    if not summary.strip():
        return "empty"
    if len(summary.split()) > SUMMARY_MAX_WORDS:
        return "too long"
    if _RECOMMENDING.search(summary):
        return "recommendation"
    if _EMAIL.search(summary):
        return "email address"
    if _LINK.search(summary):
        return "link"
    if _PHONE.search(summary):
        return "phone number"
    if _MARKDOWN.search(summary):
        return "markdown"
    if _invented_name(summary, words):
        return "name"
    return None
