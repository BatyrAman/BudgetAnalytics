from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.repositories.analytics import AnalyticsRepository, Scope
from app.repositories.deposits import DepositRepository
from app.repositories.transactions import TransactionRepository
from app.schemas.dashboard import (
    BalanceCard,
    BudgetOverview,
    DashboardResponse,
    DepositOverview,
    ExpenseCategory,
    MonthlySummary,
    RecentTransaction,
)
from app.services.analytics.ranges import month_range
from app.services.budgets import BudgetService
from app.services.deposits import expected_profit


class DashboardService:
    """
    Главный экран. Фиксированное число запросов (~7) независимо от
    количества операций: последние операции грузятся одним JOIN
    (раньше — db.get() на каждую операцию), вклады — вместе с банком.
    """

    def __init__(self, db: AsyncSession, today: date | None = None):
        self.db = db
        self.analytics = AnalyticsRepository(db)
        self.transactions = TransactionRepository(db)
        self.deposits = DepositRepository(db)
        self.today = today or date.today()

    async def get_dashboard(self, user_id: int) -> DashboardResponse:
        currency = settings.DEFAULT_CURRENCY
        all_time = await self.analytics.totals(Scope(user_id, currency))
        start, end = month_range(self.today.year, self.today.month)
        month = await self.analytics.totals(Scope(user_id, currency, start, end))

        balance = all_time.income - all_time.expense
        recent = await self.transactions.recent_detailed(user_id, 10)
        top = await self.analytics.by_category(Scope(user_id, currency), limit=5)
        budgets = await BudgetService(self.db, self.today).all_views(user_id)
        deposits = await self.deposits.list_with_bank(user_id)

        denominator = all_time.expense if all_time.expense > 0 else Decimal("1")
        return DashboardResponse(
            balance=BalanceCard(
                total_balance=balance,
                total_income=all_time.income,
                total_expense=all_time.expense,
                total_savings=balance,
            ),
            monthly_summary=MonthlySummary(
                month=f"{self.today.year}-{self.today.month:02d}",
                income=month.income,
                expense=month.expense,
                balance=month.income - month.expense,
            ),
            recent_transactions=[
                RecentTransaction(
                    id=tx.id,
                    description=tx.description,
                    amount=tx.amount,
                    transaction_type=tx.transaction_type.value,
                    category=tx.category.name if tx.category else "—",
                    bank=tx.bank.name if tx.bank else "—",
                    transaction_date=tx.transaction_date.isoformat(),
                )
                for tx in recent
            ],
            top_expense_categories=[
                ExpenseCategory(
                    category=name,
                    amount=total,
                    percentage=float(round(total / denominator * 100, 2)),
                )
                for _, name, _, total, _ in top
            ],
            budgets=[
                BudgetOverview(
                    budget_name=v.budget.title,
                    monthly_limit=v.budget.monthly_limit,
                    spent=v.spent,
                    remaining=v.remaining,
                    progress=v.progress,
                )
                for v in budgets
            ],
            deposits=[
                DepositOverview(
                    bank_name=d.bank.name if d.bank else "—",
                    amount=d.amount,
                    interest_rate=d.interest_rate,
                    expected_profit=expected_profit(d),
                    maturity_date=d.end_date.isoformat(),
                )
                for d in deposits
            ],
        )
