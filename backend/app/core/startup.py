"""
Проверки инфраструктуры при старте приложения.

Startup НЕ создаёт схему: он проверяет, что БД доступна и что
она мигрирована до последней ревизии Alembic. Если нет — приложение
не стартует с понятной ошибкой (alembic upgrade head).
"""

from __future__ import annotations

import logging
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[2]


class StartupCheckError(RuntimeError):
    pass


def alembic_head_revisions() -> set[str]:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return set(ScriptDirectory.from_config(config).get_heads())


async def check_database(engine: AsyncEngine) -> None:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            has_version_table = await conn.scalar(
                text("SELECT to_regclass('public.alembic_version') IS NOT NULL")
            )
            current = set()
            if has_version_table:
                rows = await conn.execute(text("SELECT version_num FROM alembic_version"))
                current = {row[0] for row in rows}
    except Exception as exc:
        raise StartupCheckError(f"Database is not reachable: {type(exc).__name__}") from exc

    heads = alembic_head_revisions()
    if current != heads:
        raise StartupCheckError(
            "Database schema is not up to date "
            f"(current={sorted(current) or 'empty'}, head={sorted(heads)}). "
            "Run: alembic upgrade head"
        )

    logger.info("Database is reachable, schema at revision %s", ",".join(sorted(heads)))
