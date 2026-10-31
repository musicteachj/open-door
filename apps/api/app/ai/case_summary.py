"""The case summary's plumbing: the request, the summarizer interface, and the program checks.

A case's words are the most sensitive text in the product, so the summary call is built to know as
little as possible: the category and the words, in one message, with no tools. The words sit only
inside an untrusted-text tag whose own name is escaped in them. The call is a `Summarizer`, not a
`Transport` method: a second interface keeps the many `Transport` fakes untouched, and the lifespan
builds it like the embedder. There are scripted, replay, and Anthropic versions (the last is in
`anthropic_transport.py`).

`summary_problem` runs on every summary before it is stored, whoever wrote it.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Final, Protocol

from app.ai.pricing import Usage
from app.ai.prompts.versions import case_summary_prompt
from app.ai.summary_checks import judges, misquotes, unattributed
from app.ai.text import neutralize
from app.domain.cases import CATEGORY_LABELS

# The words go inside this tag, as untrusted data.
SUMMARY_WORDS_TAG: Final = "case_words"
# The conversation model's pin (`CURRENT_PINS.model`; a test holds them equal). Not imported: this
# module must load without the database layer.
SUMMARY_MODEL: Final = "claude-opus-5-5"
SUMMARY_EFFORT: Final = "low"
SUMMARY_TIMEOUT_SECONDS: Final = 30
# Thinking counts toward this and cannot be turned off on Opus 5.5, so a `max_tokens` stop would
# fail the summary; the room is for the thinking and the answer.
SUMMARY_MAX_TOKENS: Final = 2048
# The prompt asks for at most 120 words; a summary over this is stored as failed. The paid runs of
# 2026-10-28 showed the longest note's summary at 161 to 171 words even when asked for 120, with
# every judge line passing, so the ceiling sits above that rather than refusing a sound summary.
SUMMARY_MAX_WORDS: Final = 180

SCRIPTED_PROMPT_VERSION: Final = "scripted-1"

SUMMARY_OUTPUT_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {"summary": {"type": "string"}},
    "required": ["summary"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class SummaryRequest:
    """The one summary call, ready to send. The words are in `messages` and nowhere else."""

    category: str
    messages: tuple[dict[str, Any], ...] = field(repr=False)
    timeout_seconds: int
    # The summary's prompt (`prompts/case_summary.md`), sent as the system prompt.
    system: str = field(default_factory=case_summary_prompt, repr=False)
    model: str = SUMMARY_MODEL
    effort: str = SUMMARY_EFFORT
    max_tokens: int = SUMMARY_MAX_TOKENS


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
    """The call as plain JSON-able data: what a replay fingerprints and what the Anthropic
    summarizer sends."""
    return {
        "model": request.model,
        "max_tokens": request.max_tokens,
        "system": request.system,
        "messages": list(request.messages),
        "output_config": {
            "effort": request.effort,
            "format": {"type": "json_schema", "schema": SUMMARY_OUTPUT_SCHEMA},
        },
    }


# --- The program checks -----------------------------------------------------------------------

# What is wrong even in reported form, because it is the summary's own framing: the summarizer's
# first person ("I recommend", "we suggest") and a label that sets the summary up as a verdict or
# a plan ("Priority:", "Severity:", "Next step:", "Recommendation:"). Everything else that judged
# or recommended (credibility, seriousness, "HR should", "warrants an investigation") is caught
# by the attribution check below, since in the summary's own voice it is never attributed to the
# person, and when it is attributed it is reported speech and allowed ("They want someone to take
# it seriously").
_RECOMMENDING = re.compile(
    r"\b(?:(?:i|we) (?:would |strongly )?(?:recommend|advis|suggest)\w*"
    r"|(?:recommendations?|priority|severity|next steps?)\s*:)",
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
        # A line break, or a quotation that opens right here, starts a sentence of its own.
        if text[i] in "\n\u201c\u2018":
            return True
        # A straight quote opens only when the word follows it directly and the quote itself
        # follows a space or the start; with a space after it, it closes a quotation.
        if text[i] == '"' and i == index - 1 and (i == 0 or text[i - 1] in " \t\r\n([:"):
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
    if unattributed(summary):
        return "unattributed"
    if misquotes(summary, words):
        return "misquote"
    if judges(summary):
        return "judgment"
    if _invented_name(summary, words):
        return "name"
    return None
