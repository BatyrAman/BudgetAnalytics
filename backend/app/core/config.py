from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


Environment = Literal["development", "test", "production"]


class Settings(BaseSettings):
    """
    Конфигурация приложения.

    Всё читается из переменных окружения / файла .env
    (см. backend/.env.example). Обязательны только секреты:
    DATABASE_URL и SECRET_KEY — у остальных есть безопасные
    значения по умолчанию для локальной разработки.
    """

    # --- application ---
    APP_NAME: str = "Budget Analytics"
    VERSION: str = "0.2.0"
    API_PREFIX: str = "/api/v1"
    ENVIRONMENT: Environment = "development"
    DEBUG: bool = False

    # --- database ---
    DATABASE_URL: str
    DB_ECHO: bool = False
    DB_POOL_SIZE: int = Field(default=5, ge=1)
    DB_MAX_OVERFLOW: int = Field(default=10, ge=0)
    # На старте приложения проверяем, что БД доступна и схема
    # мигрирована до head. В тестах отключается.
    STARTUP_CHECKS: bool = True

    # --- auth / JWT ---
    SECRET_KEY: str = Field(min_length=32)
    ALGORITHM: Literal["HS256", "HS384", "HS512"] = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=15, ge=1, le=24 * 60)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=14, ge=1, le=90)
    # Стоимость bcrypt; в тестах понижается для скорости.
    BCRYPT_ROUNDS: int = Field(default=12, ge=4, le=16)

    # Refresh-токен живёт в httpOnly-cookie.
    REFRESH_COOKIE_NAME: str = "refresh_token"
    REFRESH_COOKIE_SECURE: bool = True
    REFRESH_COOKIE_SAMESITE: Literal["strict", "lax", "none"] = "strict"
    REFRESH_COOKIE_DOMAIN: str | None = None
    # Legacy-режим для не-браузерных клиентов: refresh-токен
    # дополнительно возвращается/принимается в теле запроса.
    REFRESH_TOKEN_IN_BODY: bool = False

    # --- CORS ---
    # Список origin'ов через запятую. "*" запрещён (см. валидатор).
    CORS_ORIGINS: str = "http://localhost:3000"

    # --- logging ---
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    LOG_JSON: bool = False

    # --- uploads / abuse protection ---
    MAX_UPLOAD_SIZE_MB: int = Field(default=10, ge=1, le=100)
    RATE_LIMIT_ENABLED: bool = True
    LOGIN_RATE_LIMIT_PER_MINUTE: int = Field(default=10, ge=1)
    UPLOAD_RATE_LIMIT_PER_MINUTE: int = Field(default=20, ge=1)

    # --- finance defaults ---
    DEFAULT_CURRENCY: str = "KZT"

    # --- AI (пока только интерфейсы) ---
    AI_PROVIDER: str = "disabled"

    # --- background tasks ---
    REDIS_URL: str = "redis://localhost:6379/0"
    # JSON-файл с актуальными условиями банков для update_bank_products.
    BANK_PRODUCTS_FILE: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    @field_validator("CORS_ORIGINS")
    @classmethod
    def _no_wildcard_origin(cls, value: str) -> str:
        origins = [item.strip() for item in value.split(",") if item.strip()]
        if "*" in origins:
            raise ValueError(
                "CORS_ORIGINS must list explicit origins; '*' is not allowed "
                "because the API uses credentials (refresh cookie)."
            )
        return ",".join(origins)

    @model_validator(mode="after")
    def _production_guards(self) -> "Settings":
        if self.ENVIRONMENT == "production":
            if self.DEBUG:
                raise ValueError("DEBUG must be disabled in production")
            if not self.REFRESH_COOKIE_SECURE:
                raise ValueError("REFRESH_COOKIE_SECURE must be true in production")
        return self

    @property
    def cors_origins(self) -> list[str]:
        return [item for item in self.CORS_ORIGINS.split(",") if item]

    @property
    def max_upload_size_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
