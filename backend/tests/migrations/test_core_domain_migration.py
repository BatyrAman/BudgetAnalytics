"""Data migration 86fba8eeb485 -> 5d2fb0f83b83 (core financial domain).

Runs only with MIGRATION_TEST_DATABASE_URL pointing at a DISPOSABLE database:
the test downgrades it to an empty schema and rebuilds it.
"""

import os
import subprocess
import sys
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

URL = os.environ.get("MIGRATION_TEST_DATABASE_URL")
BACKEND_DIR = Path(__file__).resolve().parents[2]
INITIAL, CORE = "86fba8eeb485", "5d2fb0f83b83"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not URL, reason="MIGRATION_TEST_DATABASE_URL is not set"),
]


def alembic(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": URL or ""},
        check=check,
        capture_output=True,
        text=True,
    )


@pytest.fixture
async def db() -> AsyncIterator[AsyncEngine]:
    alembic("downgrade", "base")
    alembic("upgrade", INITIAL)
    engine = create_async_engine(URL or "", connect_args={"server_settings": {"timezone": "UTC"}})
    yield engine
    await engine.dispose()
    alembic("downgrade", "base")
    alembic("upgrade", "head")


async def _execute(engine: AsyncEngine, sql: str) -> None:
    async with engine.begin() as conn:
        await conn.execute(text(sql))


async def _rows(engine: AsyncEngine, sql: str) -> list[tuple]:
    async with engine.connect() as conn:
        return [tuple(r) for r in await conn.execute(text(sql))]


LEGACY_DATA = """
INSERT INTO users (id, full_name, email, hashed_password, is_active)
VALUES (1, 'A', 'a@example.com', 'x', true), (2, 'B', 'b@example.com', 'x', true);
INSERT INTO banks (id, name) VALUES (1, 'Kaspi Bank');
INSERT INTO categories (id, name, color, icon) VALUES
    (1, 'Food', '#111111', 'cart'), (2, 'Rent', '#222222', 'home'), (3, 'Orphan', '#333333', 'x');
INSERT INTO transactions (id, amount, description, transaction_type, transaction_date,
                          user_id, category_id, bank_id) VALUES
    (1, 100.00, 'a food', 'EXPENSE', '2025-03-31 23:30:00', 1, 1, 1),
    (2, 200.00, 'b food', 'EXPENSE', '2025-03-01 00:00:00', 2, 1, 1),
    (3, 300.00, 'a rent', 'EXPENSE', '2025-03-02 12:00:00', 1, 2, 1),
    (4, 400.00, 'a salary', 'INCOME', '2025-03-03 09:15:00', 1, 1, 1);
INSERT INTO budgets (id, title, monthly_limit, spent, user_id) VALUES (1, 'Food', 1000, 100, 1);
INSERT INTO deposits (id, amount, interest_rate, start_date, end_date, user_id, bank_id)
VALUES (1, 500000, 14.00, '2025-01-01', '2026-01-01', 1, 1);
"""


async def test_upgrade_moves_shared_categories_to_owners_and_downgrade_restores(
    db: AsyncEngine,
) -> None:
    for statement in LEGACY_DATA.strip().split(";"):
        if statement.strip():
            await _execute(db, statement)

    alembic("upgrade", CORE)

    categories = await _rows(
        db, "SELECT user_id, name, color, icon FROM categories ORDER BY user_id, name"
    )
    assert categories == [
        (1, "Food", "#111111", "cart"),
        (1, "Rent", "#222222", "home"),
        (2, "Food", "#111111", "cart"),
    ]  # no global rows remain; the unreferenced 'Orphan' is gone

    links = await _rows(
        db,
        "SELECT t.id, t.user_id, c.user_id, c.name FROM transactions t "
        "JOIN categories c ON c.id = t.category_id ORDER BY t.id",
    )
    assert links == [(1, 1, 1, "Food"), (2, 2, 2, "Food"), (3, 1, 1, "Rent"), (4, 1, 1, "Food")]

    dates = await _rows(
        db, "SELECT id, transaction_date, currency_code FROM transactions ORDER BY id"
    )
    assert dates[0] == (1, datetime(2025, 3, 31, 23, 30, tzinfo=UTC), "KZT")  # naive -> UTC

    deposit = await _rows(db, "SELECT capitalization, currency_code, effective_rate FROM deposits")
    assert deposit == [("none", "KZT", None)]
    assert await _rows(db, "SELECT default_currency_code FROM users ORDER BY id") == [
        ("KZT",),
        ("KZT",),
    ]

    alembic("downgrade", INITIAL)

    assert await _rows(db, "SELECT name FROM categories ORDER BY name") == [("Food",), ("Rent",)]
    restored = await _rows(
        db,
        "SELECT t.id, c.name, t.transaction_date FROM transactions t "
        "JOIN categories c ON c.id = t.category_id ORDER BY t.id",
    )
    assert [(r[0], r[1]) for r in restored] == [(1, "Food"), (2, "Food"), (3, "Rent"), (4, "Food")]
    assert restored[0][2] == datetime(2025, 3, 31, 23, 30)  # back to naive, same wall time


async def test_upgrade_aborts_on_rows_violating_new_constraints(db: AsyncEngine) -> None:
    await _execute(
        db,
        "INSERT INTO users (id, full_name, email, hashed_password, is_active) "
        "VALUES (1, 'A', 'a@example.com', 'x', true)",
    )
    await _execute(db, "INSERT INTO banks (id, name) VALUES (1, 'Bank')")
    await _execute(
        db, "INSERT INTO categories (id, name, color, icon) VALUES (1, 'C', '#000', 'x')"
    )
    await _execute(
        db,
        "INSERT INTO transactions "
        "(amount, transaction_type, transaction_date, user_id, category_id, bank_id) "
        "VALUES (0, 'EXPENSE', '2025-01-01', 1, 1, 1)",
    )

    result = alembic("upgrade", CORE, check=False)

    assert result.returncode != 0
    assert "1 row(s) in transactions have amount <= 0" in result.stderr
    # Transactional DDL: nothing was applied.
    assert await _rows(db, "SELECT version_num FROM alembic_version") == [(INITIAL,)]
    assert await _rows(db, "SELECT to_regclass('currencies')") == [(None,)]
