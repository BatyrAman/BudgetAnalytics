"""
Подключение к БД.

Declarative Base живёт в app.models.base (единственный на проект).
Схема создаётся только миграциями Alembic — никакого create_all.

Управление транзакциями: сессия на запрос. Репозитории делают
только flush; commit выполняет application-сервис в конце
use-case. При исключении сессия откатывается здесь.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings


def build_engine(url: str | None = None, **kwargs) -> AsyncEngine:
    options = {
        "echo": settings.DB_ECHO,
        "pool_pre_ping": True,
        "pool_size": settings.DB_POOL_SIZE,
        "max_overflow": settings.DB_MAX_OVERFLOW,
    }
    options.update(kwargs)
    return create_async_engine(url or settings.DATABASE_URL, **options)


engine = build_engine()

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autoflush=False,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        try:
            yield session
        except BaseException:
            await session.rollback()
            raise
