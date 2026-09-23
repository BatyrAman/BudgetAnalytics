"""
Обработка импорта выписки в фоне.

Сейчас /upload обрабатывает файл синхронно (размер ограничен 10 МБ).
Для асинхронного режима API создаёт запись PENDING, кладёт файл в
хранилище и ставит эту задачу в очередь. Задача идемпотентна:
импорт в терминальном статусе повторно не обрабатывается, а
дубли операций исключены UNIQUE(user_id, external_hash).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.enums import ImportStatus
from app.repositories.cards import CardRepository
from app.repositories.imports import StatementImportRepository
from app.services.imports.service import StatementImportService
from app.services.parser import get_parser


async def process_statement_import(
    import_id: int,
    content: bytes,
    session_factory: async_sessionmaker = SessionLocal,
) -> ImportStatus | None:
    async with session_factory() as session:
        record = await StatementImportRepository(session).get_for_update(import_id)
        if record is None:
            return None
        if ImportStatus(record.status).is_terminal:
            return ImportStatus(record.status)
        currency = settings.DEFAULT_CURRENCY
        if record.card_id is not None:
            card = await CardRepository(session).get_owned(record.card_id, record.user_id)
            currency = card.currency if card else currency
        outcome = await StatementImportService(session).process(
            record, get_parser(record.parser), content, currency=currency
        )
        return ImportStatus(outcome.record.status)
