"""Application settings.

All configuration comes from environment variables (optionally a `.env` file in
the working directory). Secrets have no defaults and are wrapped in `SecretStr`
so they are never printed in reprs or logs.

`ENVIRONMENT` selects the profile:

* ``development`` — local work; docs on, readable console logs allowed.
* ``test`` — automated tests.
* ``production`` — strict: validated secret strength, no DEBUG/SQL echo,
  no wildcard CORS, docs off by default.
"""

import os
from decimal import Decimal
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "test", "production"]

_MIN_PRODUCTION_SECRET_LENGTH = 32
_PLACEHOLDER_SECRETS = {"change-me", "changeme", "secret", "please-change-me"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # `KEY=` (empty) means "use the default"; for required secrets it means
        # "missing", so an empty SECRET_KEY is rejected rather than accepted.
        env_ignore_empty=True,
    )

    # --- application
    ENVIRONMENT: Environment = "development"
    APP_NAME: str = "BudgetAnalytics"
    VERSION: str = "0.1.0"
    API_PREFIX: str = "/api/v1"
    DEBUG: bool = False
    # None → enabled everywhere except production.
    DOCS_ENABLED: bool | None = None

    # --- database
    DATABASE_URL: SecretStr
    DB_ECHO: bool = False
    DB_POOL_SIZE: int = Field(default=5, ge=1, le=100)
    DB_MAX_OVERFLOW: int = Field(default=10, ge=0, le=100)

    # --- security
    SECRET_KEY: SecretStr
    ALGORITHM: Literal["HS256", "HS384", "HS512"] = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, ge=1, le=24 * 60)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, ge=1, le=90)
    CORS_ORIGINS: list[str] = Field(default_factory=list)
    # Max request body for JSON endpoints; statement uploads get IMPORT_MAX_FILE_BYTES.
    MAX_REQUEST_BYTES: int = Field(default=1024 * 1024, ge=1024, le=20 * 1024 * 1024)

    # --- rate limiting ("memory" is per process: development/tests only)
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_BACKEND: Literal["memory", "redis"] = "memory"
    REDIS_URL: SecretStr | None = None

    # Deprecated legacy endpoints (/analytics legacy, /dashboard, /investments,
    # /upload). None -> enabled everywhere except production.
    ENABLE_LEGACY_API: bool | None = None

    # --- logging
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    LOG_JSON: bool = True

    # --- statement import
    IMPORT_MAX_FILE_BYTES: int = Field(default=5 * 1024 * 1024, ge=1024, le=50 * 1024 * 1024)
    IMPORT_MAX_ROWS: int = Field(default=5000, ge=1, le=100_000)
    # Zip-bomb guard for XLSX (sum of uncompressed sizes and compression ratio).
    IMPORT_XLSX_MAX_UNCOMPRESSED_BYTES: int = Field(default=50 * 1024 * 1024, ge=1024)
    IMPORT_XLSX_MAX_RATIO: int = Field(default=100, ge=2)
    IMPORT_PREVIEW_TTL_HOURS: int = Field(default=24, ge=1, le=24 * 7)

    # --- AI advisor (provider-independent; "none" = deterministic rules only)
    AI_PROVIDER: Literal["none", "openai"] = "none"
    AI_MODEL: str = Field(default="gpt-4o-mini", min_length=1, max_length=100)
    AI_TIMEOUT_SECONDS: float = Field(default=30.0, gt=0, le=300)
    AI_MAX_RETRIES: int = Field(default=2, ge=0, le=5)
    AI_RETRY_BASE_DELAY_SECONDS: float = Field(default=0.5, ge=0, le=30)
    AI_MAX_OUTPUT_TOKENS: int = Field(default=1500, ge=100, le=16000)
    # None = provider default (some reasoning models reject a custom temperature).
    AI_TEMPERATURE: float | None = Field(default=None, ge=0, le=2)
    OPENAI_API_KEY: SecretStr | None = None
    # Any OpenAI-compatible endpoint (e.g. a proxy); must serve /chat/completions.
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    # Cost control. Prices are configured (they change), never hard-coded.
    AI_INPUT_PRICE_PER_1M_TOKENS_USD: Decimal | None = Field(default=None, ge=0)
    AI_OUTPUT_PRICE_PER_1M_TOKENS_USD: Decimal | None = Field(default=None, ge=0)
    AI_DAILY_TOKEN_LIMIT_PER_USER: int = Field(default=50_000, ge=0)
    AI_DAILY_COST_LIMIT_PER_USER_USD: Decimal | None = Field(default=None, ge=0)
    AI_MONTHLY_COST_LIMIT_TOTAL_USD: Decimal | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _validate_ai(self) -> "Settings":
        if self.AI_PROVIDER == "openai" and (
            self.OPENAI_API_KEY is None or not self.OPENAI_API_KEY.get_secret_value()
        ):
            raise ValueError("OPENAI_API_KEY is required when AI_PROVIDER=openai")
        cost_limits = (self.AI_DAILY_COST_LIMIT_PER_USER_USD, self.AI_MONTHLY_COST_LIMIT_TOTAL_USD)
        prices = (self.AI_INPUT_PRICE_PER_1M_TOKENS_USD, self.AI_OUTPUT_PRICE_PER_1M_TOKENS_USD)
        if any(limit is not None for limit in cost_limits) and any(p is None for p in prices):
            raise ValueError("AI cost limits require both AI_*_PRICE_PER_1M_TOKENS_USD settings")
        return self

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def legacy_api_enabled(self) -> bool:
        if self.ENABLE_LEGACY_API is not None:
            return self.ENABLE_LEGACY_API
        return not self.is_production

    @property
    def docs_enabled(self) -> bool:
        if self.DOCS_ENABLED is not None:
            return self.DOCS_ENABLED
        return not self.is_production

    @model_validator(mode="after")
    def _validate_production(self) -> "Settings":
        if not self.is_production:
            return self

        errors: list[str] = []
        secret = self.SECRET_KEY.get_secret_value()

        if len(secret) < _MIN_PRODUCTION_SECRET_LENGTH:
            errors.append(
                f"SECRET_KEY must be at least {_MIN_PRODUCTION_SECRET_LENGTH} "
                "characters in production"
            )
        if secret.lower() in _PLACEHOLDER_SECRETS:
            errors.append("SECRET_KEY is a placeholder value")
        if self.DEBUG:
            errors.append("DEBUG must be false in production")
        if self.DB_ECHO:
            errors.append("DB_ECHO must be false in production (it logs SQL parameters)")
        if "*" in self.CORS_ORIGINS:
            errors.append("CORS_ORIGINS must list explicit origins in production")
        if any(not origin.startswith("https://") for origin in self.CORS_ORIGINS if origin != "*"):
            errors.append("CORS_ORIGINS must use https:// in production")
        if not self.RATE_LIMIT_ENABLED:
            errors.append("RATE_LIMIT_ENABLED must be true in production")
        if self.RATE_LIMIT_BACKEND != "redis" or self.REDIS_URL is None:
            errors.append(
                "production requires RATE_LIMIT_BACKEND=redis and REDIS_URL "
                "(in-memory limits are per process and can be bypassed)"
            )
        if self.LOG_LEVEL == "DEBUG":
            errors.append("LOG_LEVEL must not be DEBUG in production")

        if errors:
            raise ValueError("; ".join(errors))

        return self


# Docker/Kubernetes secrets: one file per setting, e.g. /run/secrets/SECRET_KEY.
# Environment variables still take precedence over secret files.
SECRETS_DIR = os.environ.get("SECRETS_DIR", "/run/secrets")


@lru_cache
def get_settings() -> Settings:
    if os.path.isdir(SECRETS_DIR):
        return Settings(_secrets_dir=SECRETS_DIR)
    return Settings()  # values come from the environment


settings = get_settings()
