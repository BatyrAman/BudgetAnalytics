"""
Отчёты для существующих эндпоинтов /analytics/* (контракт v0.1 сохранён).

Все цифры считаются агрегирующими запросами; тренд за N месяцев —
один запрос с date_trunc('month') вместо 2×N запросов.
"""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.repositories.analytics import AnalyticsRepository, Scope
from app.repositories.deposits import DepositRepository
from app.schemas.analytics import (
    AIRecommendation,
    AnalyticsResponse,
    BankAnalytics,
    CashFlowAnalytics,
    CategoryAnalytics,
    FinancialHealth,
    IncomeExpenseTrend,
    InvestmentAnalytics,
    MonthlyComparison,
    SavingsAnalytics,
    SpendingForecast,
)
from app.services.ai.advisor import FinancialAdvisorService
from app.services.analytics.forecasting import ForecastingService
from app.services.analytics.ranges import month_range, shift_month
from app.services.analytics.saving import SavingAnalyticsService
from app.services.deposits import expected_profit
from app.services.finance.calendar import add_months
from app.services.finance.cashflow import growth_percent
from app.services.finance.money import ZERO

STATUS_LABELS = {
    "excellent": "Отлично",
    "good": "Хорошо",
    "average": "Средне",
    "poor": "Слабо",
    "critical": "Критично",
}


class AnalyticsReportService:
    def __init__(self, db: AsyncSession, today: date | None = None) -> None:
        self.db = db
        self.repo = AnalyticsRepository(db)
        self.today = today or date.today()
        self.currency = settings.DEFAULT_CURRENCY

    def _scope(self, user_id: int, start=None, end=None) -> Scope:
        return Scope(user_id, self.currency, start, end)

    async def cash_flow(self, user_id: int) -> CashFlowAnalytics:
        health = await SavingAnalyticsService(self.db).financial_health(user_id)
        return CashFlowAnalytics(
            total_income=health["income"],
            total_expense=health["expense"],
            net_cash_flow=health["balance"],
            savings_rate=float(health["saving_rate"]),
        )

    async def trend(self, user_id: int, months: int) -> list[IncomeExpenseTrend]:
        first = shift_month(self.today, months - 1)
        start = datetime.combine(first, time.min)
        end = datetime.combine(add_months(self.today.replace(day=1), 1), time.min)
        rows = {b.date(): (i, e) for b, i, e in await self.repo.series(self._scope(user_id, start, end), "month")}
        result = []
        for offset in range(months):
            month = add_months(first, offset)
            income, expense = rows.get(month, (ZERO, ZERO))
            result.append(
                IncomeExpenseTrend(period=f"{month.year}-{month.month:02d}", income=income, expense=expense)
            )
        return result

    async def categories(self, user_id: int, limit: int) -> list[CategoryAnalytics]:
        scope = self._scope(user_id)
        total = (await self.repo.totals(scope)).expense
        denominator = total if total > 0 else Decimal("1")
        return [
            CategoryAnalytics(
                category=name,
                amount=amount,
                transaction_count=count,
                percentage=float(round(amount / denominator * 100, 2)),
            )
            for _, name, _, amount, count in await self.repo.by_category(scope, limit=limit)
        ]

    async def forecast(self, user_id: int) -> SpendingForecast:
        summary = await ForecastingService(self.db).forecast_summary(user_id, self.today)
        confidence = 0.8 if summary["predicted_income"] > 0 else 0.3
        return SpendingForecast(
            next_month_expense=summary["predicted_expense"],
            predicted_savings=summary["predicted_balance"],
            confidence=confidence,
        )

    async def savings(self, user_id: int, target: Decimal) -> SavingsAnalytics:
        current = await SavingAnalyticsService(self.db).get_balance(user_id)
        progress = float(round(current / target * 100, 2)) if target > 0 else 0.0
        remaining = target - current
        return SavingsAnalytics(
            current_savings=current,
            target_savings=target,
            progress=max(progress, 0.0),
            remaining=remaining if remaining > 0 else ZERO,
        )

    async def health(self, user_id: int) -> FinancialHealth:
        report = await FinancialAdvisorService(self.db, self.today).generate_advice(user_id)
        recommendation = (
            report["recommendations"][0] if report["recommendations"] else "Финансовое состояние в норме."
        )
        return FinancialHealth(
            score=report["financial_score"],
            status=STATUS_LABELS.get(report["status"], report["status"]),
            recommendation=recommendation,
        )

    async def recommendations(self, user_id: int) -> list[AIRecommendation]:
        report = await FinancialAdvisorService(self.db, self.today).generate_advice(user_id)
        return (
            [AIRecommendation(title="Внимание", description=t, priority="high") for t in report["warnings"]]
            + [AIRecommendation(title="Совет", description=t, priority="medium") for t in report["recommendations"]]
            + [AIRecommendation(title="Возможность", description=t, priority="low") for t in report["opportunities"]]
        )

    async def banks(self, user_id: int) -> list[BankAnalytics]:
        return [
            BankAnalytics(bank_name=name, income=income, expense=expense, transaction_count=count)
            for _, name, income, expense, count in await self.repo.by_bank(self._scope(user_id))
        ]

    async def investment(self, user_id: int) -> InvestmentAnalytics:
        deposits = await DepositRepository(self.db).list_owned(user_id)
        invested = sum((d.amount for d in deposits), ZERO)
        profit = sum((expected_profit(d) for d in deposits), ZERO)
        return InvestmentAnalytics(invested_amount=invested, expected_profit=profit, expected_value=invested + profit)

    async def monthly_comparison(self, user_id: int) -> MonthlyComparison:
        current = await self.repo.totals(self._scope(user_id, *month_range(self.today.year, self.today.month)))
        prev_month = shift_month(self.today, 1)
        previous = await self.repo.totals(self._scope(user_id, *month_range(prev_month.year, prev_month.month)))

        def growth(now: Decimal, before: Decimal) -> float:
            value = growth_percent(now, before)
            return float(value) if value is not None else 0.0

        return MonthlyComparison(
            current_month_income=current.income,
            previous_month_income=previous.income,
            current_month_expense=current.expense,
            previous_month_expense=previous.expense,
            income_growth_percent=growth(current.income, previous.income),
            expense_growth_percent=growth(current.expense, previous.expense),
        )

    async def full(self, user_id: int) -> AnalyticsResponse:
        return AnalyticsResponse(
            cash_flow=await self.cash_flow(user_id),
            monthly_comparison=await self.monthly_comparison(user_id),
            spending_forecast=await self.forecast(user_id),
            savings=await self.savings(user_id, Decimal("500000")),
            investment=await self.investment(user_id),
            financial_health=await self.health(user_id),
            income_expense_trend=await self.trend(user_id, 6),
            categories=await self.categories(user_id, 10),
            banks=await self.banks(user_id),
            recommendations=await self.recommendations(user_id),
        )
