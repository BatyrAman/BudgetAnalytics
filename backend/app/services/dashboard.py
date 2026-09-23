from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.analytics.income import IncomeAnalyticsService
from app.services.analytics.spending import SpendingAnalyticsService
from app.services.analytics.saving import SavingAnalyticsService
from app.services.analytics.forecasting import ForecastingService


class DashboardService:
    """
    Главный сервис Dashboard.

    Собирает всю информацию о пользователе
    в один объект.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

        self.income_service = IncomeAnalyticsService(db)
        self.spending_service = SpendingAnalyticsService(db)
        self.saving_service = SavingAnalyticsService(db)
        self.forecast_service = ForecastingService(db)

    async def get_dashboard(
        self,
        user_id: int,
    ) -> dict:
        """
        Полная информация для главной страницы.
        """

        income = await self.income_service.get_current_month_summary(
            user_id
        )

        spending = await self.spending_service.get_current_month_summary(
            user_id
        )

        savings = await self.saving_service.financial_health(
            user_id
        )

        recommendations = (
            await self.saving_service.recommend_saving(
                user_id
            )
        )

        forecast = await self.forecast_service.full_forecast(
            user_id
        )

        return {
            "income": income,
            "spending": spending,
            "saving": savings,
            "forecast": forecast,
            "recommendations": recommendations,
        }

    async def get_home_statistics(
        self,
        user_id: int,
    ) -> dict:
        """
        Краткая статистика для главной страницы.
        """

        income = await self.income_service.get_total_income(
            user_id
        )

        expense = await self.spending_service.get_total_expenses(
            user_id
        )

        balance = income - expense

        saving_rate = (
            await self.saving_service.get_saving_rate(
                user_id
            )
        )

        return {
            "balance": balance,
            "income": income,
            "expense": expense,
            "saving_rate": saving_rate,
        }

    async def get_financial_report(
        self,
        user_id: int,
    ) -> dict:
        """
        Полный финансовый отчет пользователя.
        """

        dashboard = await self.get_dashboard(user_id)

        statistics = await self.get_home_statistics(
            user_id
        )

        return {
            "statistics": statistics,
            "analytics": dashboard,
        }