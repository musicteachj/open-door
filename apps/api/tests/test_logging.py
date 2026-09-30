import json
import logging
import sys
from collections.abc import Iterator

import pytest

from app.core.logging import JsonFormatter, configure_logging
from app.core.request_id import request_id_var

UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")


def make_record(message: str) -> logging.LogRecord:
    return logging.LogRecord("app.test", logging.INFO, __file__, 1, message, None, None)


@pytest.fixture
def restore_logging() -> Iterator[None]:
    """`configure_logging` changes process-wide state, so put it back after the test."""
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    uvicorn_state = [
        (logger, logger.handlers[:], logger.propagate, logger.level)
        for logger in map(logging.getLogger, UVICORN_LOGGERS)
    ]
    yield
    root.handlers = saved_handlers
    root.setLevel(saved_level)
    for logger, handlers, propagate, level in uvicorn_state:
        logger.handlers, logger.propagate = handlers, propagate
        logger.setLevel(level)


def test_a_log_line_is_one_json_object() -> None:
    line = JsonFormatter().format(make_record("hello"))

    entry = json.loads(line)
    assert entry["level"] == "INFO"
    assert entry["logger"] == "app.test"
    assert entry["message"] == "hello"
    assert "requestId" not in entry


def test_a_log_line_inside_a_request_carries_its_id() -> None:
    token = request_id_var.set("trace-42")
    try:
        entry = json.loads(JsonFormatter().format(make_record("hello")))
    finally:
        request_id_var.reset(token)

    assert entry["requestId"] == "trace-42"


def test_an_explicit_request_id_on_the_record_wins_over_the_context() -> None:
    record = make_record("hello")
    record.__dict__["request_id"] = "explicit"
    token = request_id_var.set("from-context")
    try:
        entry = json.loads(JsonFormatter().format(record))
    finally:
        request_id_var.reset(token)

    assert entry["requestId"] == "explicit"


def test_an_exception_is_included_in_the_log_line() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        record = logging.LogRecord(
            "app.test", logging.ERROR, __file__, 1, "failed", None, sys.exc_info()
        )

    entry = json.loads(JsonFormatter().format(record))

    assert "ValueError: boom" in entry["exception"]


@pytest.mark.usefixtures("restore_logging")
def test_configure_logging_is_idempotent_and_keeps_other_handlers() -> None:
    root = logging.getLogger()
    other = logging.NullHandler()
    root.addHandler(other)

    configure_logging("INFO")
    configure_logging("INFO")

    json_handlers = [h for h in root.handlers if isinstance(h.formatter, JsonFormatter)]
    assert len(json_handlers) == 1
    assert other in root.handlers


@pytest.mark.usefixtures("restore_logging")
def test_log_level_governs_uvicorn_loggers_too() -> None:
    # uvicorn's own config pins its loggers to INFO; the configured level must override that.
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)

    configure_logging("WARNING")

    assert logging.getLogger("uvicorn.access").getEffectiveLevel() == logging.WARNING
