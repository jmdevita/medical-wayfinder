"""
JSON-line logging setup. Opt-in via ATLAS_LOG_FORMAT=json (default for prod);
falls back to readable text for local dev.

The output is one JSON object per line, with the active request id when one is
in context. Container log aggregators (Loki, Cloudwatch, GCP Logging) all
parse this shape natively.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time

from app.middleware.request_id import request_id_ctx


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts":    _iso(record.created),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg":   record.getMessage(),
        }
        rid = request_id_ctx.get()
        if rid:
            payload["rid"] = rid
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # Stash any structured kwargs the caller passed via `extra={...}`.
        for k, v in record.__dict__.items():
            if k in _STD_FIELDS or k.startswith("_"):
                continue
            try:
                json.dumps(v)
            except TypeError:
                v = repr(v)
            payload[k] = v
        return json.dumps(payload, default=str)


_STD_FIELDS = {
    "args", "asctime", "created", "exc_info", "exc_text", "filename",
    "funcName", "levelname", "levelno", "lineno", "module", "msecs",
    "message", "msg", "name", "pathname", "process", "processName",
    "relativeCreated", "stack_info", "thread", "threadName", "taskName",
}


def _iso(epoch: float) -> str:
    # Millisecond precision; UTC. Cheap and aggregator-friendly.
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(epoch)) + f".{int((epoch % 1) * 1000):03d}Z"


def configure_logging() -> None:
    """Replace any existing handlers with a JSON or text handler based on env."""
    fmt = os.environ.get("ATLAS_LOG_FORMAT", "text").lower()
    level_name = os.environ.get("ATLAS_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    if fmt == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s %(levelname)-5s %(name)s — %(message)s",
                datefmt="%H:%M:%S",
            )
        )

    root = logging.getLogger()
    # Remove uvicorn's default handlers if present so we don't double-log.
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Uvicorn attaches its own handlers to these loggers and propagates upward.
    # Without intervention, every access line would be emitted twice in JSON
    # mode (once by uvicorn's text handler, once by our root JSON handler).
    # Drop their handlers, raise the level, and stop propagation.
    for name in ("uvicorn.access", "uvicorn.error", "uvicorn"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True   # let our root handler render them
        if name == "uvicorn.access":
            lg.setLevel(max(level, logging.WARNING))
        else:
            lg.setLevel(level)
