"""Analytics use cases: user-scoped SQL aggregates + the pure finance engine.

No financial arithmetic happens here. Repositories return per-type sums
computed in SQL for exactly one user and one currency; every definition
(refunds, transfers, savings rate, shares, rounding) is applied by
``app.services.finance``.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.models.enums import TransactionType
from app.repositories.budget import BudgetRepository
from app.repositories.currency import CurrencyRepository
from app.repositories.transaction import TransactionRepository
from app.services.finance import (
    BudgetUtilization,
    CashflowTotals,
    CurrencySpec,
    FinanceInputError,
    Period,
    PeriodSummary,
    budget_utilization,
    month_period,
    percent_change,
    share_percent,
    totals_from_sums,
    year_period,
)
from app.services.finance.money import calc_context, quantize_money
from app.services.finance.periods import DEFAULT_TIMEZONE

__all__ = ["FinancialSummaryService", "NotFoundError"]


@dataclass(frozen=True)
class CategoryAmount:
    category_id: int
    name: str
    amount: Decimal
    transaction_count: int
    share_percent: Decimal | None
    is_system: bool = False


@dataclass(frozen=True)
class MetricChange:
    current: Decimal
    previous: Decimal
    change: Decimal
    change_percent: Decimal | None


@dataclass(frozen=True)
class MonthComparison:
    current: PeriodSummary
    previous: PeriodSummary
    income: MetricChange
    net_expenses: MetricChange
    net_cash_flow: MetricChange
    savings_rate_change_pp: Decimal | None  # percentage points


class FinancialSummaryService:
    def __init__(self, db: AsyncSession) -> None:
        self.transactions = TransactionRepository(db)
        self.currencies = CurrencyRepository(db)
        self.budgets = BudgetRepository(db)

    async def currency(self, code: str) -> CurrencySpec:
        spec = await self.currencies.get_spec(code)
        if spec is None:
            raise FinanceInputError(f"Unknown currency: {code}")
        return spec

    # ------------------------------------------------------------ totals
    async def totals(
        self,
        user_id: int,
        start: datetime,
        end: datetime,
        currency: CurrencySpec,
        category_id: int | None = None,
    ) -> CashflowTotals:
        sums = await self.transactions.sums_by_type(
            user_id, start, end, currency.code, category_id=category_id
        )
        return totals_from_sums(sums.sums, sums.count, currency)

    async def period_summary(
        self, user_id: int, period: Period, currency: CurrencySpec
    ) -> PeriodSummary:
        return PeriodSummary(period, await self.totals(user_id, period.start, period.end, currency))

    async def yearly_summary(
        self, user_id: int, year: int, currency_code: str, tz: ZoneInfo = DEFAULT_TIMEZONE
    ) -> PeriodSummary:
        return await self.period_summary(
            user_id, year_period(year, tz), await self.currency(currency_code)
        )

    async def monthly_summaries(
        self, user_id: int, year: int, currency_code: str, tz: ZoneInfo = DEFAULT_TIMEZONE
    ) -> list[PeriodSummary]:
        """Twelve months (empty ones included), grouped by LOCAL month in SQL."""

        currency = await self.currency(currency_code)
        year_range = year_period(year, tz)
        by_month = await self.transactions.monthly_sums_by_type(
            user_id, year_range.start, year_range.end, currency.code, tz.key
        )
        summaries = []
        for month in range(1, 13):
            sums = by_month.get((year, month))
            totals = totals_from_sums(
                sums.sums if sums else {}, sums.count if sums else 0, currency
            )
            summaries.append(PeriodSummary(month_period(year, month, tz), totals))
        return summaries

    # ------------------------------------------------------------ breakdown
    async def category_breakdown(
        self,
        user_id: int,
        start: datetime,
        end: datetime,
        currency: CurrencySpec,
        kind: str,
    ) -> tuple[Decimal, list[CategoryAmount]]:
        """``kind="expense"``: net expense per category (expense − refund),
        share of total net expenses. ``kind="income"``: income per category,
        share of total income. Categories with a zero amount are omitted;
        shares are ``None`` when the total is <= 0. Sorted by amount, desc."""

        rows = await self.transactions.sums_by_category(user_id, start, end, currency.code)
        zero = Decimal(0)
        amounts: list[tuple[int, str, Decimal, int, bool]] = []
        with calc_context():
            for row in rows:
                if kind == "expense":
                    value = row.sums.get(TransactionType.EXPENSE, zero) - row.sums.get(
                        TransactionType.REFUND, zero
                    )
                    count = row.count  # includes the category's refunds and transfers
                else:
                    value = row.sums.get(TransactionType.INCOME, zero)
                    count = row.count
                if value != 0:
                    amounts.append(
                        (
                            row.category_id,
                            row.name,
                            quantize_money(value, currency),
                            count,
                            row.is_system,
                        )
                    )
            total = sum((a[2] for a in amounts), zero)
        total = quantize_money(total, currency)
        items = [
            CategoryAmount(cid, name, amount, count, share_percent(amount, total), system)
            for cid, name, amount, count, system in sorted(amounts, key=lambda a: (-a[2], a[1]))
        ]
        return total, items

    # ------------------------------------------------------------ comparison
    async def compare_months(
        self, user_id: int, month: date, currency: CurrencySpec, tz: ZoneInfo
    ) -> MonthComparison:
        current_period = month_period(month.year, month.month, tz)
        prev_year, prev_month = (
            (month.year - 1, 12) if month.month == 1 else (month.year, month.month - 1)
        )
        previous_period = month_period(prev_year, prev_month, tz)
        current = await self.period_summary(user_id, current_period, currency)
        previous = await self.period_summary(user_id, previous_period, currency)

        def change(cur: Decimal, prev: Decimal) -> MetricChange:
            with calc_context():
                delta = cur - prev
            return MetricChange(
                cur, prev, quantize_money(delta, currency), percent_change(cur, prev)
            )

        rate_now, rate_before = current.savings_rate, previous.savings_rate
        rate_pp = None
        if rate_now is not None and rate_before is not None:
            with calc_context():
                rate_pp = rate_now - rate_before
        return MonthComparison(
            current=current,
            previous=previous,
            income=change(current.totals.income, previous.totals.income),
            net_expenses=change(current.totals.net_expenses, previous.totals.net_expenses),
            net_cash_flow=change(current.totals.net_cash_flow, previous.totals.net_cash_flow),
            savings_rate_change_pp=rate_pp,
        )

    # ------------------------------------------------------------ budgets
    async def budget_utilization(
        self,
        user_id: int,
        budget_id: int,
        month: date,
        tz: ZoneInfo = DEFAULT_TIMEZONE,
    ) -> BudgetUtilization:
        """Utilization of one of the user's budgets in the month of ``month``,
        from actual net expenses (expenses − refunds) in the budget's currency
        and, if set, its category. Ignores the legacy manual ``spent`` field."""

        budget = await self.budgets.get_for_user(budget_id, user_id)
        if budget is None:
            raise NotFoundError("Budget not found")
        currency = await self.currency(budget.currency_code)
        period = month_period(month.year, month.month, tz)
        totals = await self.totals(
            user_id, period.start, period.end, currency, category_id=budget.category_id
        )
        return budget_utilization(budget.monthly_limit, totals.net_expenses, currency)
