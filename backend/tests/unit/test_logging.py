import json
import logging

import pytest

from app.core.config import settings
from app.core.logging import JsonFormatter, configure_logging, request_id_var


def test_json_formatter_includes_request_id_and_fields() -> None:
    record = logging.LogRecord("budget", logging.INFO, __file__, 1, "hello %s", ("world",), None)
    record.request_id = "req-1"
    record.fields = {"path": "/health", "status": 200}

    payload = json.loads(JsonFormatter().format(record))

    assert payload["message"] == "hello world"
    assert payload["level"] == "INFO"
    assert payload["request_id"] == "req-1"
    assert payload["path"] == "/health"
    assert payload["status"] == 200
    assert payload["ts"].endswith("+00:00")


def test_uvicorn_access_log_is_disabled_to_avoid_duplicates() -> None:
    configure_logging(settings)
    assert logging.getLogger("uvicorn.access").disabled is True
    assert logging.getLogger("uvicorn.error").disabled is False


def test_request_id_reaches_log_records(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(settings.model_copy(update={"LOG_JSON": True, "LOG_LEVEL": "INFO"}))
    token = request_id_var.set("ctx-42")
    try:
        logging.getLogger("budget.test").info("inside request")
    finally:
        request_id_var.reset(token)
        configure_logging(settings)

    line = capsys.readouterr().out.strip().splitlines()[-1]
    assert json.loads(line)["request_id"] == "ctx-42"
