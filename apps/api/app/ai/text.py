"""Small text helpers the assistant's modules share."""


def one_line(text: str) -> str:
    """Collapse every run of whitespace, newlines included, so a value can't add lines."""
    return " ".join(text.split())


def error_name(error: BaseException) -> str:
    """The type of an error, for a log line. The rule everywhere: log the type, never the content,
    because the message of an error can hold a question, an answer, or a tool result."""
    return type(error).__name__
