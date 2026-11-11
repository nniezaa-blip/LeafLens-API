"""Structured JSON logging configuration."""

import json
import logging
import sys


class JSONFormatter(logging.Formatter):
    """Structured JSON logs — parseable by Datadog, ELK, CloudWatch."""

    def format(self, record: logging.LogRecord) -> str:
        log: dict[str, object] = {
            "time": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
        }
        if hasattr(record, "request_id"):
            log["request_id"] = record.request_id
        if record.exc_info:
            log["exception"] = self.formatException(record.exc_info)
        return json.dumps(log, default=str)


def setup_logging(*, debug: bool = False) -> None:
    """Configure root logger with JSON output."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.DEBUG if debug else logging.INFO)

    # Quiet noisy libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
