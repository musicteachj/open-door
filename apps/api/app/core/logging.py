"""Structured JSON logs, one object per line, each carrying the request ID when there is one."""

import json
import logging
from datetime import UTC, datetime

from app.core.request_id import request_id_var


class JsonFormatter(logging.Formatter):
    """Format a log record as a single JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "time": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = getattr(record, "request_id", None) or request_id_var.get()
        if request_id is not None:
            entry["requestId"] = request_id
        # Structured fields passed as `extra={"fields": {...}}`. They can't replace the keys above.
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            entry.update({key: value for key, value in fields.items() if key not in entry})
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def configure_logging(level: str) -> None:
    """Send every log record, including uvicorn's, through one JSON handler on the root logger.

    Safe to call repeatedly: it replaces only its own handler, so pytest's caplog and any future
    handler (tracing, for example) stay attached.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [h for h in root.handlers if not isinstance(h.formatter, JsonFormatter)]
    root.addHandler(handler)
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers = []
        uvicorn_logger.propagate = True
        # uvicorn pins its own levels; NOTSET defers to the root, so LOG_LEVEL governs everything.
        uvicorn_logger.setLevel(logging.NOTSET)
