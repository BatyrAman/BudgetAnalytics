"""
Общая конфигурация тестов.

Unit-тесты (tests/unit) не требуют БД. Интеграционные и API-тесты
(tests/integration) требуют PostgreSQL: URL берётся из
TEST_DATABASE_URL (по умолчанию локальная БД budget_test). Схема
создаётся настоящими миграциями (alembic upgrade head) — так тесты
заодно проверяют миграции. Если БД недоступна, интеграционные
тесты пропускаются.
"""

from __future__ import annotations

import os

os.environ.setdefault(
    "TEST_DATABASE_URL", "postgresql+asyncpg://postgres@localhost:5432/budget_test"
)
os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-long-enough-0123456789")
os.environ["ENVIRONMENT"] = "test"
os.environ["STARTUP_CHECKS"] = "false"
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["REFRESH_COOKIE_SECURE"] = "false"
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ["BCRYPT_ROUNDS"] = "4"
