"""Structured JSON logging.

Every log line is a single JSON object on stdout, suitable for container log
collection (docs/architecture.md §3 "Logs"). Request-scoped fields
(``request_id``, ``duration_ms``, ``collector_id`` …) are attached by the
request-logging middleware via the ``extra=`` mechanism.

Security (docs/security.md §7): log records never include headers, request
bodies, or credentials. API keys are never logged anywhere.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

#: Request-scoped attributes copied from a log record into the JSON output
#: when present. This is an allow-list: arbitrary record attributes are NOT
#: serialized, which keeps accidental secret leakage out of the logs.
_CONTEXT_FIELDS: tuple[str, ...] = (
    "request_id",
    "method",
    "endpoint",
    "status",
    "duration_ms",
    "collector_id",
    "event_id",
    "client",
    "db_operation",
)


class JsonFormatter(logging.Formatter):
    """Format log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in _CONTEXT_FIELDS:
            value = record.__dict__.get(field)
            if value is not None:
                entry[field] = value
        if record.exc_info and record.exc_info[0] is not None:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def configure_logging(level: str) -> None:
    """Configure root logging with the JSON formatter.

    Idempotent: replaces existing root handlers so repeated app-factory calls
    (e.g. in tests) do not duplicate output. Uvicorn's access log is silenced
    because the request-logging middleware emits richer structured entries.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())

    # Our middleware logs every request; uvicorn's plain-text access log
    # would only duplicate it in a non-JSON format.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
