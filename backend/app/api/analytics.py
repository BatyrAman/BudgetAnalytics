"""Engine-based analytics (current API).

Common query parameters:
* ``date_from`` / ``date_to`` — inclusive local dates (default: current month);
* ``tz`` — IANA time zone for day/month boundaries (default Asia/Almaty);
* ``currency`` — ISO code (default: the user's default currency). Amounts in
  other currencies are never converted or mixed in.
"""

from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    DateRange,
    get_currency,
    get_current_active_user,
    get_date_range,
    get_db,
    get_timezone,
    parse_month,
)
from app.core.errors import ErrorResponse
from app.models.user import User
from app.schemas.reports import (
    CategoryAmountResponse,
    CategoryBreakdownResponse,
    ComparisonResponse,
    ExpenseSummaryResponse,
    IncomeSummaryResponse,
    MetricChangeResponse,
    MonthlyResponse,
    MonthSummary,
    PeriodInfo,
    SavingsRateResponse,
    SummaryResponse,
)
from app.services.finance import (
    CurrencySpec,
    PeriodSummary,
    expense_to_income_percent,
    year_period,
)
from app.services.financial_summary import CategoryAmount, FinancialSummaryService, MetricChange

router = APIRouter(prefix="/analytics", tags=["Analytics"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}


def _period(r: DateRange) -> PeriodInfo:
    return PeriodInfo(date_from=r.date_from, date_to=r.date_to, timezone=r.tz.key)


def _categories(items: list[CategoryAmount]) -> list[CategoryAmountResponse]:
    return [
        CategoryAmountResponse(
            category_id=i.category_id,
            name=i.name,
            amount=i.amount,
            transaction_count=i.transaction_count,
            share_percent=i.share_percent,
        )
        for i in items
    ]


def _month(summary: PeriodSummary) -> MonthSummary:
    t = summary.totals
    return MonthSummary(
        month=summary.period.label,
        income=t.income,
        net_expenses=t.net_expenses,
        net_cash_flow=t.net_cash_flow,
        savings_rate=t.savings_rate,
        transaction_count=t.transaction_count,
    )


def _change(c: MetricChange) -> MetricChangeResponse:
    return MetricChangeResponse(
        current=c.current, previous=c.previous, change=c.change, change_percent=c.change_percent
    )


@router.get("/summary", response_model=SummaryResponse, responses=_ERRORS)
async def get_summary(
    period: DateRange = Depends(get_date_range),
    currency: CurrencySpec = Depends(get_currency),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> SummaryResponse:
    """Income, expenses, refunds, transfers, net cash flow and savings rate."""

    t = await FinancialSummaryService(db).totals(
        current_user.id, period.start, period.end, currency
    )
    return SummaryResponse(
        period=_period(period),
        currency_code=currency.code,
        income=t.income,
        gross_expenses=t.gross_expenses,
        refunds=t.refunds,
        net_expenses=t.net_expenses,
        net_cash_flow=t.net_cash_flow,
        transfers_in=t.transfers_in,
        transfers_out=t.transfers_out,
        savings_rate=t.savings_rate,
        transaction_count=t.transaction_count,
    )


@router.get("/income", response_model=IncomeSummaryResponse, responses=_ERRORS)
async def get_income(
    period: DateRange = Depends(get_date_range),
    currency: CurrencySpec = Depends(get_currency),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> IncomeSummaryResponse:
    total, items = await FinancialSummaryService(db).category_breakdown(
        current_user.id, period.start, period.end, currency, "income"
    )
    return IncomeSummaryResponse(
        period=_period(period),
        currency_code=currency.code,
        total=total,
        by_category=_categories(items),
    )


@router.get("/expenses", response_model=ExpenseSummaryResponse, responses=_ERRORS)
async def get_expenses(
    period: DateRange = Depends(get_date_range),
    currency: CurrencySpec = Depends(get_currency),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ExpenseSummaryResponse:
    """Gross expenses, refunds and net expenses with a per-category breakdown."""

    service = FinancialSummaryService(db)
    totals = await service.totals(current_user.id, period.start, period.end, currency)
    _, items = await service.category_breakdown(
        current_user.id, period.start, period.end, currency, "expense"
    )
    return ExpenseSummaryResponse(
        period=_period(period),
        currency_code=currency.code,
        gross_expenses=totals.gross_expenses,
        refunds=totals.refunds,
        net_expenses=totals.net_expenses,
        by_category=_categories(items),
    )


@router.get("/savings-rate", response_model=SavingsRateResponse, responses=_ERRORS)
async def get_savings_rate(
    period: DateRange = Depends(get_date_range),
    currency: CurrencySpec = Depends(get_currency),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> SavingsRateResponse:
    """(income − net expenses) / income × 100; null when there is no income."""

    t = await FinancialSummaryService(db).totals(
        current_user.id, period.start, period.end, currency
    )
    return SavingsRateResponse(
        period=_period(period),
        currency_code=currency.code,
        income=t.income,
        net_expenses=t.net_expenses,
        savings_rate=t.savings_rate,
        expense_to_income_percent=expense_to_income_percent(t.income, t.net_expenses),
    )


@router.get("/category-breakdown", response_model=CategoryBreakdownResponse, responses=_ERRORS)
async def get_category_breakdown(
    kind: str = Query(default="expense", pattern="^(expense|income)$"),
    period: DateRange = Depends(get_date_range),
    currency: CurrencySpec = Depends(get_currency),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> CategoryBreakdownResponse:
    """Per category: net expenses (expenses − refunds) or income, with shares
    of the total (null when the total is not positive)."""

    total, items = await FinancialSummaryService(db).category_breakdown(
        current_user.id, period.start, period.end, currency, kind
    )
    return CategoryBreakdownResponse(
        period=_period(period),
        currency_code=currency.code,
        kind=kind,
        total=total,
        items=_categories(items),
    )


@router.get("/monthly", response_model=MonthlyResponse, responses=_ERRORS)
async def get_monthly(
    year: int = Query(ge=1900, le=2200),
    tz: ZoneInfo = Depends(get_timezone),
    currency: CurrencySpec = Depends(get_currency),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> MonthlyResponse:
    """Twelve local calendar months (empty months included) and the year total."""

    service = FinancialSummaryService(db)
    months = await service.monthly_summaries(current_user.id, year, currency.code, tz)
    year_total = await service.period_summary(current_user.id, year_period(year, tz), currency)
    return MonthlyResponse(
        year=year,
        timezone=tz.key,
        currency_code=currency.code,
        months=[_month(m) for m in months],
        total=_month(year_total),
    )


@router.get("/comparison", response_model=ComparisonResponse, responses=_ERRORS)
async def get_comparison(
    month: str | None = Query(
        default=None, pattern=r"^\d{4}-\d{2}$", description="YYYY-MM; default: current"
    ),
    tz: ZoneInfo = Depends(get_timezone),
    currency: CurrencySpec = Depends(get_currency),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ComparisonResponse:
    """A month vs the previous calendar month (local to ``tz``)."""

    result = await FinancialSummaryService(db).compare_months(
        current_user.id, parse_month(month, tz), currency, tz
    )
    return ComparisonResponse(
        timezone=tz.key,
        currency_code=currency.code,
        current=_month(result.current),
        previous=_month(result.previous),
        income=_change(result.income),
        net_expenses=_change(result.net_expenses),
        net_cash_flow=_change(result.net_cash_flow),
        savings_rate_change_pp=result.savings_rate_change_pp,
    )
