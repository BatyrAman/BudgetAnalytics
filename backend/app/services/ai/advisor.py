"""
FinancialAdvisorService — адаптер над детерминированным FinancialDecisionEngine.

Раньше здесь жили if/else-правила; теперь они в
app/services/decision/engine.py. Сервис только собирает снимок
финансов пользователя (агрегаты, без персональных данных) и
возвращает отчёт в прежнем формате для /analytics/health и
/analytics/recommendations. LLM здесь нет и не будет: будущий
AI Coach получит тот же DecisionReport через tools и лишь объяснит его.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.repositories.analytics import AnalyticsRepository, Scope
from app.repositories.debts import DebtRepository
from app.repositories.users import UserRepository
from app.services.analytics.forecasting import ForecastingService
from app.services.debts.projection import project
from app.services.decision.engine import (
    DecisionReport,
    FinancialDecisionEngine,
    FinancialSnapshot,
    FindingKind,
)
from app.services.finance.cashflow import savings_rate
from app.services.finance.money import ZERO, percent


class FinancialAdvisorService:
    def __init__(self, db: AsyncSession, today: date | None = None):
        self.db = db
        self.analytics = AnalyticsRepository(db)
        self.forecast = ForecastingService(db)
        self.debts = DebtRepository(db)
        self.users = UserRepository(db)
        self.engine = FinancialDecisionEngine()
        self.today = today or date.today()

    async def snapshot(self, user_id: int) -> tuple[FinancialSnapshot, dict]:
        totals = await self.analytics.totals(Scope(user_id, settings.DEFAULT_CURRENCY))
        forecast = await self.forecast.forecast_summary(user_id, self.today)

        debts = await self.debts.list_active(user_id)
        user = await self.users.get(user_id)
        monthly_income = (
            user.monthly_income_declared
            if user is not None and user.monthly_income_declared is not None
            else forecast["predicted_income"]
        )
        payments = sum((d.monthly_payment for d in debts), ZERO)
        debt_load = percent(payments, monthly_income) if debts and monthly_income else None

        snapshot = FinancialSnapshot(
            income=totals.income,
            expense=totals.expense,
            balance=totals.income - totals.expense,
            saving_rate=savings_rate(totals.income, totals.expense),
            predicted_balance=forecast["predicted_balance"],
            debt_load=debt_load,
            has_non_amortizing_debt=any(project(d, self.today) is None for d in debts),
        )
        return snapshot, forecast

    async def evaluate(self, user_id: int) -> DecisionReport:
        snapshot, _ = await self.snapshot(user_id)
        return self.engine.evaluate(snapshot)

    async def generate_advice(self, user_id: int) -> dict:
        snapshot, forecast = await self.snapshot(user_id)
        report = self.engine.evaluate(snapshot)
        return {
            "financial_score": report.score,
            "status": report.saving_status,
            "income": snapshot.income,
            "expense": snapshot.expense,
            "balance": snapshot.balance,
            "saving_rate": snapshot.saving_rate,
            "forecast": forecast,
            "warnings": report.messages(FindingKind.WARNING),
            "recommendations": report.messages(FindingKind.RECOMMENDATION),
            "opportunities": report.messages(FindingKind.OPPORTUNITY),
            "findings": report.findings,
        }
