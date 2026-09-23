from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.database import SessionLocal
from app.services.products.service import BankProductService, UpdateStats
from app.services.products.sources import ProductSource

logger = logging.getLogger(__name__)


def configured_sources() -> list[ProductSource]:
    """
    Источники ставок. Сейчас — только файл, заданный в
    BANK_PRODUCTS_FILE (готовит оператор). Скраперы банков и КФГД
    подключаются сюда же как реализации ProductSource.
    """

    from app.core.config import settings
    from app.services.products.sources import JsonFileProductSource

    path = settings.BANK_PRODUCTS_FILE
    return [JsonFileProductSource(path)] if path else []


async def update_bank_products(
    sources: list[ProductSource] | None = None,
    session_factory: async_sessionmaker = SessionLocal,
) -> list[UpdateStats]:
    stats: list[UpdateStats] = []
    for source in sources if sources is not None else configured_sources():
        async with session_factory() as session:
            try:
                stats.append(await BankProductService(session).update_from_source(source))
            except Exception:
                # Сбой одного источника не трогает данные остальных.
                await session.rollback()
                logger.exception("Bank products source %s failed", source.name)
    return stats
