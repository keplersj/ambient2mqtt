"""Logging setup: human-readable text (default) or one JSON object per line for Loki & co."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from . import tracing

TEXT_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"

# Attributes every LogRecord has; anything else on a record came from `extra=` and is
# emitted as a top-level JSON field (e.g. device_id, kind, result).
_STANDARD = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out: dict = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD and not key.startswith("_"):
                out[key] = value
        ids = tracing.current_ids()
        if ids:
            out["trace_id"], out["span_id"] = ids
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out, default=str)


def setup_logging(level: str, fmt: str) -> None:
    handler = logging.StreamHandler()
    if fmt == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(TEXT_FORMAT))
    logging.basicConfig(level=level, handlers=[handler], force=True)
