from __future__ import annotations

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.analytics.income import IncomeAnalyticsService
from app.services.analytics.spending import SpendingAnalyticsService


class SavingAnalyticsService:
    """
    Сервис аналитики накоплений.

    Saving Rate =
        (Доход - Расход) / Доход * 100%
    """

    def __init__(self, db: AsyncSession, currency_code: str = "KZT"):
        # LEGACY: only rows in this currency are aggregated (never mixed).
        self.db = db
        self.currency_code = currency_code

        self.income_service = IncomeAnalyticsService(db, currency_code)
        self.spending_service = SpendingAnalyticsService(db, currency_code)

    async def get_balance(
        self,
        user_id: int,
    ) -> Decimal:
        """
        Текущий остаток средств.
        """

        income = await self.income_service.get_total_income(user_id)

        expense = await self.spending_service.get_total_expenses(user_id)

        return income - expense

    async def get_saving_rate(
        self,
        user_id: int,
    ) -> Decimal:
        """
        Процент накоплений.

        Формула:

        (Доход - Расход) / Доход * 100
        """

        income = await self.income_service.get_total_income(user_id)

        expense = await self.spending_service.get_total_expenses(user_id)

        if income <= 0:
            return Decimal("0")

        rate = ((income - expense) / income) * 100

        return round(rate, 2)

    async def get_free_cash(
        self,
        user_id: int,
    ) -> Decimal:
        """
        Свободные деньги.

        Это деньги,
        которые пользователь может инвестировать
        либо отложить.
        """

        return await self.get_balance(user_id)

    async def financial_health(
        self,
        user_id: int,
    ) -> dict:
        """
        Оценка финансового состояния пользователя.
        """

        income = await self.income_service.get_total_income(user_id)

        expense = await self.spending_service.get_total_expenses(user_id)

        balance = income - expense

        saving_rate = await self.get_saving_rate(user_id)

        if saving_rate >= 40:
            status = "excellent"

        elif saving_rate >= 20:
            status = "good"

        elif saving_rate >= 10:
            status = "average"

        elif saving_rate >= 0:
            status = "poor"

        else:
            status = "critical"

        return {
            "income": income,
            "expense": expense,
            "balance": balance,
            "saving_rate": saving_rate,
            "status": status,
        }

    async def monthly_summary(
        self,
        user_id: int,
        year: int,
        month: int,
    ) -> dict:
        """
        Финансовая сводка за месяц.
        """

        income = await self.income_service.get_monthly_income(
            user_id,
            year,
            month,
        )

        expense = await self.spending_service.get_monthly_expenses(
            user_id,
            year,
            month,
        )

        balance = income - expense

        if income > 0:
            saving_rate = round(
                balance / income * 100,
                2,
            )
        else:
            saving_rate = Decimal("0")

        return {
            "income": income,
            "expense": expense,
            "balance": balance,
            "saving_rate": saving_rate,
        }

    async def recommend_saving(
        self,
        user_id: int,
    ) -> dict:
        """
        Простые рекомендации пользователю.
        """

        health = await self.financial_health(user_id)

        status = health["status"]

        recommendations = {
            "excellent": [
                "Продолжайте инвестировать.",
                "Создайте резерв на 6–12 месяцев.",
                "Рассмотрите ETF или облигации.",
            ],
            "good": [
                "Увеличьте накопления до 30% дохода.",
                "Сократите необязательные расходы.",
            ],
            "average": [
                "Попробуйте откладывать минимум 20%.",
                "Контролируйте ежедневные траты.",
            ],
            "poor": [
                "Пересмотрите подписки.",
                "Снизьте необязательные расходы.",
                "Создайте финансовую подушку.",
            ],
            "critical": [
                "Расходы превышают доходы.",
                "Необходимо сократить расходы.",
                "Найдите дополнительный источник дохода.",
            ],
        }

        return {
            "status": status,
            "recommendations": recommendations[status],
        }
