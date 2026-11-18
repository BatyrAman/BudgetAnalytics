"""Async database engine, session factory and FastAPI dependency.

The declarative Base lives in ``app.models.base``; it is the single Base for all
ORM models and for Alembic. Do not declare another one here.

Lifecycle: the engine (connection pool) is created once per process and
disposed in the application lifespan (``app.main``). Each request gets its own
``AsyncSession`` via ``get_db``; route handlers/services own the commit, and any
exception rolls the session back.
"""

from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings, settings

# Every connection uses UTC, so date functions on timestamptz columns (e.g.
# EXTRACT(month ...)) never depend on the database server's configured zone.
CONNECT_ARGS = {"server_settings": {"timezone": "UTC"}}


def create_engine(app_settings: Settings) -> AsyncEngine:
    return create_async_engine(
        app_settings.DATABASE_URL.get_secret_value(),
        echo=app_settings.DB_ECHO,
        pool_pre_ping=True,
        pool_size=app_settings.DB_POOL_SIZE,
        max_overflow=app_settings.DB_MAX_OVERFLOW,
        connect_args=CONNECT_ARGS,
    )


engine: AsyncEngine = create_engine(settings)

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autoflush=False,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as db:
        try:
            yield db
        except Exception:
            await db.rollback()
            raise


async def check_database_connection() -> None:
    """Raise if the database is unreachable. Used by the readiness probe."""

    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
