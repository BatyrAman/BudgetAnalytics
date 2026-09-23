from __future__ import annotations

from app.models.statement_import import StatementImport
from app.repositories.base import OwnedRepository


class StatementImportRepository(OwnedRepository[StatementImport]):
    model = StatementImport

    async def get_for_update(self, import_id: int) -> StatementImport | None:
        """Блокирует строку импорта: параллельный повторный запуск задачи ждёт."""

        from sqlalchemy import select

        return await self.session.scalar(
            select(StatementImport).where(StatementImport.id == import_id).with_for_update()
        )
