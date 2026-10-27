"""Small text helpers the assistant's modules share."""

import re
from functools import cache


def one_line(text: str) -> str:
    """Collapse every run of whitespace, newlines included, so a value can't add lines."""
    return " ".join(text.split())


def error_name(error: BaseException) -> str:
    """The type of an error, for a log line. The rule everywhere: log the type, never the content,
    because the message of an error can hold a question, an answer, or a tool result."""
    return type(error).__name__


@cache
def _tags_pattern(tags: tuple[str, ...]) -> re.Pattern[str]:
    # An opening or closing tag of any of `tags`, in any case and with stray spaces.
    names = "|".join(re.escape(tag) for tag in tags)
    return re.compile(rf"<(?=\s*/?\s*(?:{names})\b)", re.IGNORECASE)


def neutralize(text: str, tags: tuple[str, ...]) -> str:
    """Stop untrusted text from closing or forging one of `tags`: the `<` of any opening or closing
    tag of those names becomes `&lt;`."""
    return _tags_pattern(tags).sub("&lt;", text)
