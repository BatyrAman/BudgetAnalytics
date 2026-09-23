"""upgrade → downgrade base → upgrade на отдельной БД + модели совпадают со схемой."""

import uuid

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from tests.integration.conftest import _alembic_config

pytestmark = pytest.mark.integration


@pytest.fixture
async def scratch_database():
    base_url = make_url(settings.DATABASE_URL)
    name = f"migrations_{uuid.uuid4().hex[:8]}"
    admin = create_async_engine(base_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        await conn.execute(text(f'CREATE DATABASE "{name}"'))
    engine = create_async_engine(base_url.set(database=name))
    try:
        yield engine
    finally:
        await engine.dispose()
        async with admin.connect() as conn:
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        await admin.dispose()


async def test_full_upgrade_downgrade_cycle(scratch_database):
    def cycle(sync_conn):
        config = _alembic_config(sync_conn)
        command.upgrade(config, "head")
        command.downgrade(config, "base")
        command.upgrade(config, "head")
        command.check(config)  # модели и схема после миграций совпадают

    async with scratch_database.begin() as conn:
        await conn.run_sync(cycle)

    async with scratch_database.connect() as conn:
        tables = set(
            (await conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))).scalars()
        )
        banks = (await conn.execute(text("SELECT count(*) FROM banks"))).scalar()
    assert {"users", "transactions", "debts", "bank_products", "refresh_tokens", "statement_imports"} <= tables
    assert banks == 3
