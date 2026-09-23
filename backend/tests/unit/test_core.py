import logging

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.logging import SensitiveDataFilter, redact


@pytest.mark.parametrize(
    "raw, secret",
    [
        ("token=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abc-DEF_123", "eyJhbGci"),
        ("Authorization: Bearer abc.def.ghi", "abc.def.ghi"),
        ('{"password": "hunter22"}', "hunter22"),
        ("card 4400 4301 2345 6789 used", "4400 4301"),
        ("cvv=123", "123"),
        ("IIN 900101300123", "900101300123"),
        ("iban KZ86125KZT5004100100", "KZ86125KZT5004100100"),
    ],
)
def test_redaction(raw, secret):
    assert secret not in redact(raw)


def test_filter_masks_format_args():
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "login %s", ("password=qwerty123",), None)
    SensitiveDataFilter().filter(record)
    assert "qwerty123" not in record.getMessage()


def _settings(**overrides):
    base = {"DATABASE_URL": "postgresql+asyncpg://x/y", "SECRET_KEY": "k" * 40}
    base.update(overrides)
    return Settings(_env_file=None, **base)


def test_wildcard_cors_rejected():
    with pytest.raises(ValidationError):
        _settings(CORS_ORIGINS="*")
    assert _settings(CORS_ORIGINS="https://a.kz, https://b.kz").cors_origins == ["https://a.kz", "https://b.kz"]


def test_short_secret_rejected():
    with pytest.raises(ValidationError):
        _settings(SECRET_KEY="short")


def test_production_guards():
    with pytest.raises(ValidationError):
        _settings(ENVIRONMENT="production", DEBUG=True)
    with pytest.raises(ValidationError):
        _settings(ENVIRONMENT="production", REFRESH_COOKIE_SECURE=False)
    assert _settings(ENVIRONMENT="production", REFRESH_COOKIE_SECURE=True).is_production
