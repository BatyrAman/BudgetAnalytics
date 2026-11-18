import pytest
from pydantic import ValidationError

from app.core.config import Settings

STRONG_SECRET = "x" * 40
PRODUCTION: dict[str, object] = {
    "ENVIRONMENT": "production",
    "RATE_LIMIT_ENABLED": True,
    "RATE_LIMIT_BACKEND": "redis",
    "REDIS_URL": "redis://:pw@redis:6379/0",
}


def make(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "DATABASE_URL": "postgresql+asyncpg://u:p@localhost/db",
        "SECRET_KEY": STRONG_SECRET,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


def test_defaults_for_development() -> None:
    s = make(ENVIRONMENT="development")
    assert s.API_PREFIX == "/api/v1"
    assert s.ALGORITHM == "HS256"
    assert s.DB_ECHO is False
    assert s.docs_enabled is True


def test_secrets_are_not_exposed_in_repr() -> None:
    s = make(ENVIRONMENT="development", SECRET_KEY="super-secret-value-123")
    assert "super-secret-value-123" not in repr(s)
    assert "u:p@" not in repr(s)


def test_production_accepts_strong_config_and_disables_docs() -> None:
    s = make(**PRODUCTION, CORS_ORIGINS=["https://app.example.kz"])
    assert s.is_production
    assert s.docs_enabled is False


def test_docs_can_be_enabled_explicitly_in_production() -> None:
    assert make(**PRODUCTION, DOCS_ENABLED=True).docs_enabled is True


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"SECRET_KEY": "short"}, "at least 32"),
        ({"SECRET_KEY": "change-me"}, "SECRET_KEY"),
        ({"DEBUG": True}, "DEBUG"),
        ({"DB_ECHO": True}, "DB_ECHO"),
        ({"CORS_ORIGINS": ["*"]}, "CORS_ORIGINS"),
        ({"CORS_ORIGINS": ["http://app.example.kz"]}, "https"),
        ({"RATE_LIMIT_ENABLED": False}, "RATE_LIMIT_ENABLED"),
        ({"RATE_LIMIT_BACKEND": "memory"}, "redis"),
        ({"REDIS_URL": None}, "REDIS_URL"),
        ({"LOG_LEVEL": "DEBUG"}, "LOG_LEVEL"),
    ],
)
def test_production_rejects_unsafe_config(overrides: dict[str, object], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        make(**{**PRODUCTION, **overrides})


def test_weak_secret_is_allowed_outside_production() -> None:
    assert make(ENVIRONMENT="development", SECRET_KEY="short").SECRET_KEY


def test_unsupported_jwt_algorithm_is_rejected() -> None:
    with pytest.raises(ValidationError):
        make(ALGORITHM="none")


def test_empty_env_values_fall_back_to_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOCS_ENABLED", "")
    monkeypatch.setenv("LOG_LEVEL", "")
    s = make(ENVIRONMENT="development")
    assert s.DOCS_ENABLED is None
    assert s.LOG_LEVEL == "INFO"


def test_empty_secret_key_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "")
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        Settings(_env_file=None, DATABASE_URL="postgresql+asyncpg://u:p@h/db")  # type: ignore[call-arg]


def test_env_example_file_is_loadable(monkeypatch: pytest.MonkeyPatch) -> None:
    from pathlib import Path

    # Real environment variables take precedence over the file; drop the ones
    # tests/conftest.py sets so the example's own values are what get parsed.
    for key in ("ENVIRONMENT", "DATABASE_URL", "SECRET_KEY", "DB_ECHO", "LOG_JSON", "LOG_LEVEL"):
        monkeypatch.delenv(key, raising=False)

    example = Path(__file__).resolve().parents[2] / ".env.example"
    s = Settings(_env_file=example)  # type: ignore[call-arg]
    assert s.ENVIRONMENT == "development"
    assert s.CORS_ORIGINS == ["http://localhost:3000"]


def test_missing_required_settings_fail() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, DATABASE_URL=None, SECRET_KEY=None)  # type: ignore[arg-type]


def test_legacy_api_is_off_by_default_in_production() -> None:
    assert make(**PRODUCTION).legacy_api_enabled is False
    assert make(ENVIRONMENT="development").legacy_api_enabled is True
    assert make(**PRODUCTION, ENABLE_LEGACY_API=True).legacy_api_enabled is True
