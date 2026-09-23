from __future__ import annotations

from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.analytics.income import IncomeAnalyticsService
from app.services.analytics.spending import SpendingAnalyticsService
from app.services.analytics.saving import SavingAnalyticsService
from app.services.analytics.forecasting import ForecastingService


class FinancialAdvisorService:
    """
    AI Financial Advisor.

    Сейчас советы строятся по правилам.

    Позже можно подключить:
        • OpenAI
        • Ollama
        • Gemini
        • Claude
    """

    def __init__(self, db: AsyncSession):

        self.db = db

        self.income = IncomeAnalyticsService(db)
        self.spending = SpendingAnalyticsService(db)
        self.saving = SavingAnalyticsService(db)
        self.forecast = ForecastingService(db)

    async def generate_advice(
        self,
        user_id: int,
    ) -> dict:

        income = await self.income.get_total_income(user_id)

        expense = await self.spending.get_total_expenses(user_id)

        saving_rate = await self.saving.get_saving_rate(user_id)

        balance = await self.saving.get_balance(user_id)

        forecast = await self.forecast.full_forecast(user_id)

        advice: List[str] = []

        warnings: List[str] = []

        opportunities: List[str] = []

        # ------------------------
        # Income
        # ------------------------

        if income == 0:

            warnings.append(
                "У вас пока отсутствуют доходы."
            )

        # ------------------------
        # Expense
        # ------------------------

        if expense > income:

            warnings.append(
                "Расходы превышают доходы."
            )

            advice.append(
                "Необходимо сократить необязательные расходы."
            )

        # ------------------------
        # Saving Rate
        # ------------------------

        if saving_rate >= 40:

            opportunities.append(
                "Отличная финансовая дисциплина."
            )

            advice.append(
                "Можно начать инвестировать свободные средства."
            )

        elif saving_rate >= 20:

            advice.append(
                "Попробуйте увеличить накопления до 30–40%."
            )

        elif saving_rate >= 10:

            advice.append(
                "Стоит сократить ежедневные расходы."
            )

        else:

            warnings.append(
                "Очень низкий процент накоплений."
            )

            advice.append(
                "Создайте резервный фонд минимум на 3 месяца."
            )

        # ------------------------
        # Balance
        # ------------------------

        if balance < 0:

            warnings.append(
                "Ваш баланс отрицательный."
            )

        elif balance > 300000:

            opportunities.append(
                "У вас достаточно свободных средств для инвестирования."
            )

        # ------------------------
        # Forecast
        # ------------------------

        if forecast["risk"] == "CRITICAL":

            warnings.append(
                "Высокий риск дефицита бюджета в следующем месяце."
            )

        elif forecast["risk"] == "HIGH":

            advice.append(
                "Следующий месяц может быть финансово напряженным."
            )

        elif forecast["risk"] == "LOW":

            opportunities.append(
                "Финансовый прогноз выглядит стабильно."
            )

        # ------------------------
        # Score
        # ------------------------

        score = 100

        score -= len(warnings) * 15

        score += len(opportunities) * 5

        score = max(0, min(score, 100))

        return {

            "financial_score": score,

            "income": income,

            "expense": expense,

            "balance": balance,

            "saving_rate": saving_rate,

            "forecast": forecast,

            "warnings": warnings,

            "recommendations": advice,

            "opportunities": opportunities,
        }

    async def quick_tip(
        self,
        user_id: int,
    ) -> str:

        report = await self.generate_advice(user_id)

        if report["financial_score"] >= 90:
            return "Отличное финансовое состояние."

        if report["financial_score"] >= 70:
            return "Финансы находятся в хорошем состоянии."

        if report["financial_score"] >= 50:
            return "Есть потенциал для улучшения финансов."

        return "Рекомендуется пересмотреть бюджет и расходы."