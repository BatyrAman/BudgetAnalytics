"""Test configuration.

Environment variables are set here *before* the application is imported,
because ``app.core.config.settings`` is created at import time.

* Unit tests need no services. Without ``TEST_DATABASE_URL`` the app points at
  an unreachable address, so any accidental DB access fails loudly.
* Integration tests (``tests/integration``) need a disposable PostgreSQL
  database in ``TEST_DATABASE_URL``; its tables are truncated after every test.
  They are skipped, with an explicit reason, when it is not set.
"""

import os
from collections.abc import AsyncIterator

import httpx
import pytest

UNREACHABLE_DATABASE_URL = "postgresql+asyncpg://nobody:nopass@127.0.0.1:1/unreachable"
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = TEST_DATABASE_URL or UNREACHABLE_DATABASE_URL
os.environ["SECRET_KEY"] = "test-only-secret-key-0123456789abcdef"
os.environ["DB_ECHO"] = "false"
os.environ["LOG_JSON"] = "false"
os.environ["LOG_LEVEL"] = "WARNING"
# Rate limiting is exercised by dedicated tests with a fresh limiter.
os.environ["RATE_LIMIT_ENABLED"] = "false"

from app.core.database import engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
async def _dispose_engine() -> AsyncIterator[None]:
    yield
    await engine.dispose()


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
