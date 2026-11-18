import httpx
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import engine
from app.models import Base


async def test_readiness_with_real_database(client: httpx.AsyncClient) -> None:
    response = await client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok", "rate_limit_store": "not_used"}


async def test_migrations_created_every_model_table(db_session: AsyncSession) -> None:
    async with engine.connect() as connection:
        tables = await connection.run_sync(lambda c: set(inspect(c).get_table_names()))
    assert set(Base.metadata.tables) <= tables
    assert "alembic_version" in tables

    version = await db_session.scalar(text("SELECT version_num FROM alembic_version"))
    assert version
