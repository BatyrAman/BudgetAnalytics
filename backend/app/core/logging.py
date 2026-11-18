"""Structured logging.

One JSON object per line (or a readable console line in development), always
carrying the current ``request_id``. Pass structured data via
``logger.info("msg", extra={"fields": {...}})``.

Never log secrets, tokens, passwords, raw statements or full request bodies.
"""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

logger = logging.getLogger("budget")


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
        }
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            payload.update(fields)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class ConsoleFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = (
            f"{datetime.fromtimestamp(record.created, tz=UTC):%H:%M:%S} "
            f"{record.levelname:<7} {record.name} "
            f"[{getattr(record, 'request_id', None) or '-'}] {record.getMessage()}"
        )
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict) and fields:
            base += " " + " ".join(f"{k}={v}" for k, v in fields.items())
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


def configure_logging(app_settings: Settings) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(_RequestIdFilter())
    handler.setFormatter(JsonFormatter() if app_settings.LOG_JSON else ConsoleFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(app_settings.LOG_LEVEL)

    # Uvicorn: route its server/error logs through our handler. Its access log is
    # disabled: RequestContextMiddleware writes access lines (with request_id and
    # without the client IP), so uvicorn's would only duplicate them.
    for name in ("uvicorn", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers = []
        uvicorn_logger.propagate = True
    uvicorn_access = logging.getLogger("uvicorn.access")
    uvicorn_access.handlers = []
    uvicorn_access.propagate = False
    uvicorn_access.disabled = True

    # SQL echo is controlled only by DB_ECHO (never enabled implicitly by DEBUG).
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.INFO if app_settings.DB_ECHO else logging.WARNING
    )
