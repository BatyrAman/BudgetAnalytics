"""Dashboard overview: a composition of engine results for one user, one
currency and the current local month. No arithmetic beyond the engine."""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.budget import Budget
from app.models.deposit import Deposit
from app.schemas.reports import (
    AccountBalance,
    BudgetStatus,
    Indicators,
    OverviewResponse,
)
from app.services.accounts import AccountService
from app.services.deposits import maturity_of, valid_deposits
from app.services.finance import (
    CurrencySpec,
    average,
    emergency_fund_months,
    expense_to_income_percent,
    month_period,
)
from app.services.finance.money import calc_context, quantize_money
from app.services.financial_summary import FinancialSummaryService

NOTES = [
    "current_balance is the sum of your account balances in this currency "
    "(opening balance + linked transactions); it is null if you have no accounts in it.",
    "Monthly figures cover the current calendar month in the selected time zone; "
    "refunds reduce expenses and transfers between own accounts are excluded.",
    "Deposit interest is an estimate; the bank's figures may differ.",
]


@dataclass(frozen=True)
class _Month:
    year: int
    month: int


def _shift(month: _Month, delta: int) -> _Month:
    index = month.year * 12 + (month.month - 1) + delta
    return _Month(index // 12, index % 12 + 1)


class OverviewService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.summary = FinancialSummaryService(db)

    async def build(self, user_id: int, currency: CurrencySpec, tz: ZoneInfo) -> OverviewResponse:
        now = datetime.now(UTC)
        local_today = now.astimezone(tz).date()
        this_month = _Month(local_today.year, local_today.month)

        # Accounts and balances (active accounts only).
        accounts = await AccountService(self.db).list(user_id, include_archived=False)
        in_currency = [a for a in accounts if a.account.currency_code == currency.code]
        current_balance = None
        if in_currency:
            with calc_context():
                total = sum((a.balance for a in in_currency), Decimal(0))
            current_balance = quantize_money(total, currency)

        # This month vs the previous one.
        comparison = await self.summary.compare_months(
            user_id, local_today.replace(day=1), currency, tz
        )
        totals = comparison.current.totals

        # Average net expenses of the last 3 complete months.
        previous_expenses = []
        for delta in (-1, -2, -3):
            m = _shift(this_month, delta)
            period = month_period(m.year, m.month, tz)
            previous_expenses.append(
                (await self.summary.period_summary(user_id, period, currency)).totals.net_expenses
            )
        avg_3m = average(previous_expenses, currency)
        fund_months = (
            emergency_fund_months(current_balance, avg_3m)
            if current_balance is not None and avg_3m is not None
            else None
        )

        # Budgets in this currency, utilization from actual transactions.
        budgets = list(
            await self.db.scalars(
                select(Budget)
                .where(Budget.user_id == user_id, Budget.currency_code == currency.code)
                .order_by(Budget.id)
            )
        )
        statuses = []
        for budget in budgets:
            u = await self.summary.budget_utilization(user_id, budget.id, local_today, tz)
            statuses.append(
                BudgetStatus(
                    budget_id=budget.id,
                    title=budget.title,
                    limit=u.limit,
                    spent=u.spent,
                    utilization_percent=u.utilization_percent,
                    is_exceeded=u.is_exceeded,
                )
            )

        # Deposits in this currency; legacy rows with a data_issue are excluded.
        deposits = valid_deposits(
            await self.db.scalars(
                select(Deposit).where(
                    Deposit.user_id == user_id, Deposit.currency_code == currency.code
                )
            )
        )
        with calc_context():
            principal = sum((d.amount for d in deposits), Decimal(0))
            interest = sum((maturity_of(d).interest for d in deposits), Decimal(0))

        return OverviewResponse(
            generated_at=now,
            timezone=tz.key,
            currency_code=currency.code,
            month=comparison.current.period.label,
            current_balance=current_balance,
            accounts=[
                AccountBalance(
                    account_id=a.account.id,
                    name=a.account.name,
                    currency_code=a.account.currency_code,
                    balance=a.balance,
                )
                for a in accounts
            ],
            monthly_income=totals.income,
            monthly_expenses=totals.net_expenses,
            monthly_net_cash_flow=totals.net_cash_flow,
            budgets=statuses,
            indicators=Indicators(
                savings_rate=totals.savings_rate,
                expense_to_income_percent=expense_to_income_percent(
                    totals.income, totals.net_expenses
                ),
                expense_change_percent=comparison.net_expenses.change_percent,
                income_change_percent=comparison.income.change_percent,
                average_monthly_expenses_3m=avg_3m,
                emergency_fund_months=fund_months,
                budgets_exceeded=sum(1 for s in statuses if s.is_exceeded),
                budgets_total=len(statuses),
                deposits_principal=quantize_money(principal, currency),
                deposits_expected_interest=quantize_money(interest, currency),
            ),
            notes=NOTES,
        )
