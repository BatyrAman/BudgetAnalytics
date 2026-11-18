"""Integration fixtures: real PostgreSQL from TEST_DATABASE_URL.

The database is migrated once per session with ``alembic upgrade head`` (in a
subprocess, so Alembic's logging config does not touch the test process) and
every table is truncated after each test. Never point TEST_DATABASE_URL at a
database whose data you want to keep.
"""

import os
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SessionLocal, engine
from app.models import Base

BACKEND_DIR = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if "tests/integration" in item.nodeid:
            item.add_marker(pytest.mark.integration)
            if not TEST_DATABASE_URL:
                item.add_marker(
                    pytest.mark.skip(reason="TEST_DATABASE_URL is not set (needs PostgreSQL)")
                )


@pytest.fixture(scope="session")
def migrated_database() -> None:
    assert TEST_DATABASE_URL
    subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": TEST_DATABASE_URL},
        check=True,
        capture_output=True,
    )


# Reference data seeded by migrations must survive between tests: the whole
# ``currencies`` table and the seeded rows of ``categories`` and ``banks``.
REFERENCE_TABLES = {"currencies"}


@pytest.fixture(scope="session")
async def seeded_category_ids(migrated_database: None) -> list[int]:
    async with engine.connect() as connection:
        rows = await connection.execute(text("SELECT id FROM categories WHERE user_id IS NULL"))
        return [row[0] for row in rows]


@pytest.fixture(scope="session")
async def seeded_bank_ids(migrated_database: None) -> list[int]:
    async with engine.connect() as connection:
        return [row[0] for row in await connection.execute(text("SELECT id FROM banks"))]


@pytest.fixture(autouse=True)
async def clean_tables(
    seeded_category_ids: list[int], seeded_bank_ids: list[int]
) -> AsyncIterator[None]:
    yield
    async with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):  # children before parents
            if table.name in REFERENCE_TABLES:
                continue
            if table.name == "categories":
                await connection.execute(
                    text("DELETE FROM categories WHERE NOT (id = ANY(:keep))"),
                    {"keep": seeded_category_ids},
                )
            elif table.name == "banks":
                await connection.execute(
                    text("DELETE FROM banks WHERE NOT (id = ANY(:keep))"),
                    {"keep": seeded_bank_ids},
                )
            else:
                await connection.execute(text(f"DELETE FROM {table.name}"))  # noqa: S608 - model table names


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
