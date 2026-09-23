from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.core.errors import ERROR_RESPONSES
from app.schemas.analytics import (
    AIRecommendation,
    AnalyticsResponse,
    BankAnalytics,
    CashFlowAnalytics,
    CategoryAnalytics,
    FinancialHealth,
    IncomeExpenseTrend,
    SavingsAnalytics,
    SpendingForecast,
)
from app.schemas.analytics_overview import AnalyticsOverview
from app.services.analytics.overview import AnalyticsOverviewService
from app.services.analytics.periods import Period
from app.services.analytics.reports import AnalyticsReportService

router = APIRouter(prefix="/analytics", tags=["Analytics"], responses=ERROR_RESPONSES)


@router.get("/overview", response_model=AnalyticsOverview)
async def get_overview(
    user: CurrentUser,
    db: DbSession,
    period: Period = Query(default=Period.MONTH),
    date_from: date | None = Query(default=None, description="Для произвольного периода (включительно)"),
    date_to: date | None = Query(default=None, description="Для произвольного периода (включительно)"),
    card_id: int | None = Query(default=None),
) -> AnalyticsOverview:
    """
    Универсальная аналитика за период: summary (итоги + сравнение с
    предыдущим таким же периодом), series (точки графика без пропусков),
    categories, top_merchants, top_expenses, recurring, banks, cards,
    weekdays. Суммы — строки с двумя знаками, валюта в period.currency.
    """

    return await AnalyticsOverviewService(db).overview(user.id, period, date_from, date_to, card_id)


@router.get("/cash-flow", response_model=CashFlowAnalytics)
async def get_cash_flow(user: CurrentUser, db: DbSession):
    return await AnalyticsReportService(db).cash_flow(user.id)


@router.get("/trend", response_model=list[IncomeExpenseTrend])
async def get_trend(user: CurrentUser, db: DbSession, months: int = Query(default=6, ge=1, le=24)):
    """Доходы/расходы помесячно за последние `months` месяцев (один запрос)."""

    return await AnalyticsReportService(db).trend(user.id, months)


@router.get("/categories", response_model=list[CategoryAnalytics])
async def get_categories(user: CurrentUser, db: DbSession, limit: int = Query(default=10, ge=1, le=50)):
    return await AnalyticsReportService(db).categories(user.id, limit)


@router.get("/forecast", response_model=SpendingForecast)
async def get_forecast(user: CurrentUser, db: DbSession):
    return await AnalyticsReportService(db).forecast(user.id)


@router.get("/savings", response_model=SavingsAnalytics)
async def get_savings(user: CurrentUser, db: DbSession, target: Decimal = Query(default=Decimal("500000"), ge=0)):
    return await AnalyticsReportService(db).savings(user.id, target)


@router.get("/health", response_model=FinancialHealth)
async def get_health(user: CurrentUser, db: DbSession):
    return await AnalyticsReportService(db).health(user.id)


@router.get("/recommendations", response_model=list[AIRecommendation])
async def get_recommendations(user: CurrentUser, db: DbSession):
    """Рекомендации детерминированного FinancialDecisionEngine (без LLM)."""

    return await AnalyticsReportService(db).recommendations(user.id)


@router.get("/banks", response_model=list[BankAnalytics])
async def get_bank_analytics(user: CurrentUser, db: DbSession):
    return await AnalyticsReportService(db).banks(user.id)


@router.get("", response_model=AnalyticsResponse)
async def get_full_analytics(user: CurrentUser, db: DbSession):
    """Полный аналитический отчёт для главного экрана аналитики."""

    return await AnalyticsReportService(db).full(user.id)
