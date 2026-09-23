from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.enums import TransactionType
from app.repositories.analytics import AnalyticsRepository, Scope
from app.services.analytics.ranges import month_range
from app.services.finance.cashflow import growth_percent


class IncomeAnalyticsService:
    """
    Аналитика доходов.

    Все методы — агрегирующие запросы через AnalyticsRepository.
    Фильтр по месяцу — диапазон дат (использует индекс
    (user_id, transaction_date)), а не extract(year/month).
    """

    def __init__(self, db: AsyncSession):
        self.repo = AnalyticsRepository(db)

    def _scope(self, user_id: int, start=None, end=None) -> Scope:
        return Scope(user_id, settings.DEFAULT_CURRENCY, start, end)

    async def get_total_income(self, user_id: int) -> Decimal:
        return (await self.repo.totals(self._scope(user_id))).income

    async def get_monthly_income(self, user_id: int, year: int, month: int) -> Decimal:
        start, end = month_range(year, month)
        return (await self.repo.totals(self._scope(user_id, start, end))).income

    async def get_transactions_count(self, user_id: int) -> int:
        return (await self.repo.totals(self._scope(user_id))).income_count

    async def get_income_by_category(self, user_id: int, limit: int = 10):
        rows = await self.repo.by_category(self._scope(user_id), TransactionType.INCOME, limit)
        return [(name, total) for _, name, _, total, _ in rows]

    async def compare_months(self, user_id: int, current: date, previous: date) -> dict:
        now = await self.get_monthly_income(user_id, current.year, current.month)
        before = await self.get_monthly_income(user_id, previous.year, previous.month)
        return {
            "current": now,
            "previous": before,
            "difference": now - before,
            "percent": growth_percent(now, before),
        }
