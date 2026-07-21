"""Structured JSON logging with secret redaction."""

import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any

REDACT_PATTERNS = [
    re.compile(r"(api[_-]?key|token|authorization|secret|password)\s*[=:]\s*\S+", re.IGNORECASE),
]


def _redact(message: str) -> str:
    for pattern in REDACT_PATTERNS:
        message = pattern.sub(
            lambda m: m.group(0).split("=")[0].split(":")[0] + "=<redacted>", message
        )
    return message


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": _redact(record.getMessage()),
        }
        if record.exc_info and record.exc_info[0] is not None:
            payload["exception"] = self.formatException(record.exc_info)[-2000:]
        for key in ("request_id", "endpoint", "run_id", "job"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        return json.dumps(payload)


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
