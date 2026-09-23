from __future__ import annotations

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.repositories.analytics import AnalyticsRepository, Scope
from app.services.decision.engine import saving_status
from app.services.finance.cashflow import savings_rate


class SavingAnalyticsService:
    """
    Накопления.

    Saving Rate = (Доход - Расход) / Доход * 100%.
    Внимание: «баланс» здесь — доходы минус расходы по загруженным
    операциям за всё время, а не фактический остаток на счетах.
    """

    def __init__(self, db: AsyncSession):
        self.repo = AnalyticsRepository(db)

    async def financial_health(self, user_id: int) -> dict:
        totals = await self.repo.totals(Scope(user_id, settings.DEFAULT_CURRENCY))
        rate = savings_rate(totals.income, totals.expense)
        return {
            "income": totals.income,
            "expense": totals.expense,
            "balance": totals.income - totals.expense,
            "saving_rate": rate,
            "status": saving_status(rate),
        }

    async def get_balance(self, user_id: int) -> Decimal:
        return (await self.financial_health(user_id))["balance"]

    async def get_saving_rate(self, user_id: int) -> Decimal:
        return (await self.financial_health(user_id))["saving_rate"]
