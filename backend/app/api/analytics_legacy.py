from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_db
from app.models.bank import Bank
from app.models.category import Category
from app.models.enums import TransactionType
from app.models.transaction import Transaction
from app.models.user import User
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
from app.services.analytics.income import IncomeAnalyticsService
from app.services.analytics.saving import SavingAnalyticsService
from app.services.analytics.spending import SpendingAnalyticsService

# DEPRECATED legacy analytics: all-time figures in the user's default currency,
# income/expense only (refunds and transfers ignored). Superseded by the
# engine-based endpoints in app/api/analytics.py.
router = APIRouter(prefix="/analytics", tags=["Analytics (deprecated)"], deprecated=True)


def _shift_month(base: date, months_back: int) -> date:
    """Возвращает дату, сдвинутую на `months_back` месяцев назад."""

    month_index = base.month - 1 - months_back
    year = base.year + month_index // 12
    month = month_index % 12 + 1

    return date(year, month, 1)


_STATUS_LABELS = {
    "excellent": "Отлично",
    "good": "Хорошо",
    "average": "Средне",
    "poor": "Слабо",
    "critical": "Критично",
}


@router.get(
    "/cash-flow",
    response_model=CashFlowAnalytics,
)
async def get_cash_flow(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> CashFlowAnalytics:

    saving_service = SavingAnalyticsService(db, current_user.default_currency_code)
    health = await saving_service.financial_health(current_user.id)

    return CashFlowAnalytics(
        total_income=health["income"],
        total_expense=health["expense"],
        net_cash_flow=health["balance"],
        savings_rate=float(health["saving_rate"]),
    )


@router.get(
    "/trend",
    response_model=list[IncomeExpenseTrend],
)
async def get_trend(
    months: int = Query(default=6, ge=1, le=24),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> list[IncomeExpenseTrend]:
    """
    Динамика доходов/расходов помесячно за последние `months` месяцев.
    """

    income_service = IncomeAnalyticsService(db, current_user.default_currency_code)
    spending_service = SpendingAnalyticsService(db, current_user.default_currency_code)

    today = date.today()
    trend: list[IncomeExpenseTrend] = []

    for offset in range(months - 1, -1, -1):
        target = _shift_month(today, offset)

        income = await income_service.get_monthly_income(current_user.id, target.year, target.month)
        expense = await spending_service.get_monthly_expenses(
            current_user.id, target.year, target.month
        )

        trend.append(
            IncomeExpenseTrend(
                period=f"{target.year}-{target.month:02d}",
                income=income,
                expense=expense,
            )
        )

    return trend


@router.get(
    "/categories",
    response_model=list[CategoryAnalytics],
)
async def get_categories(
    limit: int = Query(default=10, ge=1, le=50),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> list[CategoryAnalytics]:

    spending_service = SpendingAnalyticsService(db, current_user.default_currency_code)

    total_expense = await spending_service.get_total_expenses(current_user.id)
    rows = await spending_service.get_top_categories(current_user.id, limit=limit)

    counts_result = await db.execute(
        select(Category.name, func.count(Transaction.id))
        .join(Category, Category.id == Transaction.category_id)
        .where(
            Transaction.user_id == current_user.id,
            Transaction.currency_code == current_user.default_currency_code,
            Transaction.transaction_type == TransactionType.EXPENSE,
        )
        .group_by(Category.name)
    )
    counts_by_name = dict(counts_result.all())

    denominator = total_expense if total_expense > 0 else Decimal("1")

    categories: list[CategoryAnalytics] = []
    for name, total in rows:
        amount = Decimal(total)
        categories.append(
            CategoryAnalytics(
                category=name,
                amount=amount,
                transaction_count=counts_by_name.get(name, 0),
                percentage=float(round((amount / denominator) * 100, 2)),
            )
        )

    return categories


@router.get(
    "/forecast",
    response_model=SpendingForecast,
)
async def get_forecast(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> SpendingForecast:

    forecasting_service = ForecastingService(db, current_user.default_currency_code)
    summary = await forecasting_service.forecast_summary(current_user.id)

    confidence = 0.8 if summary["predicted_income"] > 0 else 0.3

    return SpendingForecast(
        next_month_expense=summary["predicted_expense"],
        predicted_savings=summary["predicted_balance"],
        confidence=confidence,
    )


@router.get(
    "/savings",
    response_model=SavingsAnalytics,
)
async def get_savings(
    target: Decimal = Query(default=Decimal("500000")),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> SavingsAnalytics:

    saving_service = SavingAnalyticsService(db, current_user.default_currency_code)
    current_savings = await saving_service.get_balance(current_user.id)

    progress = float(round((current_savings / target) * 100, 2)) if target > 0 else 0.0
    remaining = target - current_savings

    return SavingsAnalytics(
        current_savings=current_savings,
        target_savings=target,
        progress=max(progress, 0.0),
        remaining=remaining if remaining > 0 else Decimal("0"),
    )


@router.get(
    "/health",
    response_model=FinancialHealth,
)
async def get_health(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> FinancialHealth:

    advisor = FinancialAdvisorService(db, current_user.default_currency_code)
    report = await advisor.generate_advice(current_user.id)

    saving_service = SavingAnalyticsService(db, current_user.default_currency_code)
    health = await saving_service.financial_health(current_user.id)

    recommendation = (
        report["recommendations"][0]
        if report["recommendations"]
        else "Финансовое состояние в норме."
    )

    return FinancialHealth(
        score=report["financial_score"],
        status=_STATUS_LABELS.get(health["status"], health["status"]),
        recommendation=recommendation,
    )


@router.get(
    "/recommendations",
    response_model=list[AIRecommendation],
)
async def get_recommendations(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> list[AIRecommendation]:

    advisor = FinancialAdvisorService(db, current_user.default_currency_code)
    report = await advisor.generate_advice(current_user.id)

    recommendations: list[AIRecommendation] = []

    for text in report["warnings"]:
        recommendations.append(
            AIRecommendation(title="Внимание", description=text, priority="high")
        )

    for text in report["recommendations"]:
        recommendations.append(AIRecommendation(title="Совет", description=text, priority="medium"))

    for text in report["opportunities"]:
        recommendations.append(
            AIRecommendation(title="Возможность", description=text, priority="low")
        )

    return recommendations


@router.get(
    "/banks",
    response_model=list[BankAnalytics],
)
async def get_bank_analytics(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> list[BankAnalytics]:

    from sqlalchemy import case

    stmt = (
        select(
            Bank.name,
            func.sum(
                case(
                    (Transaction.transaction_type == TransactionType.INCOME, Transaction.amount),
                    else_=0,
                )
            ),
            func.sum(
                case(
                    (Transaction.transaction_type == TransactionType.EXPENSE, Transaction.amount),
                    else_=0,
                )
            ),
            func.count(Transaction.id),
        )
        .join(Bank, Bank.id == Transaction.bank_id)
        .where(
            Transaction.user_id == current_user.id,
            Transaction.currency_code == current_user.default_currency_code,
        )
        .group_by(Bank.name)
    )

    result = await db.execute(stmt)

    return [
        BankAnalytics(
            bank_name=name,
            income=Decimal(income or 0),
            expense=Decimal(expense or 0),
            transaction_count=count,
        )
        for name, income, expense, count in result.all()
    ]


@router.get(
    "",
    response_model=AnalyticsResponse,
)
async def get_full_analytics(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> AnalyticsResponse:
    """
    Полный аналитический отчёт: собирает все секции в один объект
    для главного экрана аналитики.
    """

    cash_flow = await get_cash_flow(current_user, db)
    forecast = await get_forecast(current_user, db)
    savings = await get_savings(Decimal("500000"), current_user, db)
    health = await get_health(current_user, db)
    trend = await get_trend(6, current_user, db)
    categories = await get_categories(10, current_user, db)
    banks = await get_bank_analytics(current_user, db)
    recommendations = await get_recommendations(current_user, db)

    income_service = IncomeAnalyticsService(db, current_user.default_currency_code)
    spending_service = SpendingAnalyticsService(db, current_user.default_currency_code)

    today = date.today()
    previous = _shift_month(today, 1)

    current_month_income = await income_service.get_monthly_income(
        current_user.id, today.year, today.month
    )
    previous_month_income = await income_service.get_monthly_income(
        current_user.id, previous.year, previous.month
    )
    current_month_expense = await spending_service.get_monthly_expenses(
        current_user.id, today.year, today.month
    )
    previous_month_expense = await spending_service.get_monthly_expenses(
        current_user.id, previous.year, previous.month
    )

    def _growth(current: Decimal, previous_value: Decimal) -> float:
        if previous_value <= 0:
            return 0.0
        return float(round((current - previous_value) / previous_value * 100, 2))

    monthly_comparison = MonthlyComparison(
        current_month_income=current_month_income,
        previous_month_income=previous_month_income,
        current_month_expense=current_month_expense,
        previous_month_expense=previous_month_expense,
        income_growth_percent=_growth(current_month_income, previous_month_income),
        expense_growth_percent=_growth(current_month_expense, previous_month_expense),
    )

    investment = InvestmentAnalytics(
        invested_amount=Decimal("0"),
        expected_profit=Decimal("0"),
        expected_value=Decimal("0"),
    )

    return AnalyticsResponse(
        cash_flow=cash_flow,
        monthly_comparison=monthly_comparison,
        spending_forecast=forecast,
        savings=savings,
        investment=investment,
        financial_health=health,
        income_expense_trend=trend,
        categories=categories,
        banks=banks,
        recommendations=recommendations,
    )
