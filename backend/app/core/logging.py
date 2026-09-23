"""
Логирование приложения.

Правило: в логи никогда не попадают пароли, JWT, номера карт (PAN),
CVV, банковские credentials и ИИН. Помимо дисциплины в коде,
SensitiveDataFilter маскирует такие значения в каждом сообщении —
это страховка на случай, если что-то всё же передали в logger.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from contextvars import ContextVar
from datetime import datetime, timezone

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

_MASK = "***"

_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # JWT: три base64url-сегмента, первый начинается с eyJ
    (re.compile(r"eyJ[\w-]+\.[\w-]+\.[\w-]+"), _MASK),
    (re.compile(r"(?i)\bbearer\s+[\w.\-]+"), f"Bearer {_MASK}"),
    # key=value / "key": "value" для чувствительных ключей
    (
        re.compile(
            r"(?i)(\"?(?:password|passwd|pwd|secret|token|refresh_token|"
            r"access_token|cvv|cvc|pin|authorization)\"?\s*[:=]\s*)"
            r"(\"[^\"]*\"|'[^']*'|[^\s,;&}]+)"
        ),
        rf"\1{_MASK}",
    ),
    # PAN: 13–19 цифр, допускаются пробелы/дефисы между группами
    (re.compile(r"\b(?:\d[ -]?){12,18}\d\b"), "[PAN]"),
    # ИИН РК — 12 цифр (перекрывается PAN-правилом, но оставляем явно)
    (re.compile(r"\b\d{12}\b"), "[IIN]"),
    # IBAN Казахстана
    (re.compile(r"(?i)\bKZ\d{2}[0-9A-Z]{16}\b"), "[IBAN]"),
)


def redact(text: str) -> str:
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


class SensitiveDataFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover - broken format args
            return True
        record.msg = redact(message)
        record.args = None
        return True


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", "-"),
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False)


class _RedactingFormatter(logging.Formatter):
    def formatException(self, ei) -> str:  # noqa: N802 - stdlib API
        return redact(super().formatException(ei))


def configure_logging(level: str = "INFO", json_logs: bool = False) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RequestIdFilter())
    handler.addFilter(SensitiveDataFilter())

    if json_logs:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            _RedactingFormatter(
                "%(asctime)s | %(levelname)s | %(name)s | %(request_id)s | %(message)s"
            )
        )

    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)

    # uvicorn access-лог дублирует наш middleware и пишет query string.
    logging.getLogger("uvicorn.access").disabled = True


logger = logging.getLogger("budget")
