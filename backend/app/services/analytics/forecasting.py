from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.repositories.analytics import AnalyticsRepository, Scope
from app.services.decision.engine import forecast_risk
from app.services.finance.cashflow import monthly_average, savings_rate


class ForecastingService:
    """
    Прогноз следующего месяца = среднее по месяцам, в которых были
    операции (один запрос с GROUP BY date_trunc('month')).

    Модель намеренно простая и детерминированная; её можно заменить
    (сезонность, медиана, ARIMA) без изменения API.
    """

    def __init__(self, db: AsyncSession):
        self.repo = AnalyticsRepository(db)

    async def forecast_summary(self, user_id: int, today: date | None = None) -> dict:
        rows = await self.repo.monthly_totals(Scope(user_id, settings.DEFAULT_CURRENCY))
        income = monthly_average([r[1] for r in rows])
        expense = monthly_average([r[2] for r in rows])
        balance = income - expense
        return {
            "forecast_date": today or date.today(),
            "months_of_data": len(rows),
            "predicted_income": income,
            "predicted_expense": expense,
            "predicted_balance": balance,
            "saving_rate": savings_rate(income, expense),
            "risk": forecast_risk(balance),
        }

    async def full_forecast(self, user_id: int) -> dict:
        return await self.forecast_summary(user_id)

    async def forecast_balance(self, user_id: int) -> Decimal:
        return (await self.forecast_summary(user_id))["predicted_balance"]
