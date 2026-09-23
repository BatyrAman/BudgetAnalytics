from __future__ import annotations

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.enums import TransactionType
from app.repositories.analytics import AnalyticsRepository, Scope
from app.services.analytics.ranges import month_range


class SpendingAnalyticsService:
    """Аналитика расходов (агрегирующие запросы)."""

    def __init__(self, db: AsyncSession):
        self.repo = AnalyticsRepository(db)

    def _scope(self, user_id: int, start=None, end=None) -> Scope:
        return Scope(user_id, settings.DEFAULT_CURRENCY, start, end)

    async def get_total_expenses(self, user_id: int) -> Decimal:
        return (await self.repo.totals(self._scope(user_id))).expense

    async def get_monthly_expenses(self, user_id: int, year: int, month: int) -> Decimal:
        start, end = month_range(year, month)
        return (await self.repo.totals(self._scope(user_id, start, end))).expense

    async def get_transactions_count(self, user_id: int) -> int:
        return (await self.repo.totals(self._scope(user_id))).expense_count

    async def get_top_categories(self, user_id: int, limit: int = 5) -> list[tuple[str, Decimal, int]]:
        """(название, сумма, число операций) — самые затратные категории."""

        rows = await self.repo.by_category(self._scope(user_id), TransactionType.EXPENSE, limit)
        return [(name, total, count) for _, name, _, total, count in rows]
