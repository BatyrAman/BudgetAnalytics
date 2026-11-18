from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_db
from app.models.bank import Bank
from app.models.budget import Budget
from app.models.category import Category
from app.models.deposit import Deposit
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.dashboard import (
    BalanceCard,
    BudgetOverview,
    DashboardResponse,
    DepositOverview,
    ExpenseCategory,
    MonthlySummary,
    RecentTransaction,
)
from app.services.analytics.income import IncomeAnalyticsService
from app.services.analytics.saving import SavingAnalyticsService
from app.services.analytics.spending import SpendingAnalyticsService
from app.services.budgets import budget_progress_percent
from app.services.deposits import expected_profit

# DEPRECATED legacy dashboard (all-time "balance" = income − expenses, default
# currency only). Superseded by GET /dashboard/overview (app/api/overview.py).
router = APIRouter(prefix="/dashboard", tags=["Dashboard (deprecated)"], deprecated=True)


@router.get(
    "",
    response_model=DashboardResponse,
)
async def get_dashboard(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> DashboardResponse:
    """
    Собирает всё для главного экрана: баланс, сводку месяца,
    последние операции, топ категорий расходов, бюджеты и вклады.
    """

    user_id = current_user.id

    income_service = IncomeAnalyticsService(db, current_user.default_currency_code)
    spending_service = SpendingAnalyticsService(db, current_user.default_currency_code)
    saving_service = SavingAnalyticsService(db, current_user.default_currency_code)

    total_income = await income_service.get_total_income(user_id)
    total_expense = await spending_service.get_total_expenses(user_id)
    total_savings = await saving_service.get_balance(user_id)

    balance = BalanceCard(
        total_balance=total_income - total_expense,
        total_income=total_income,
        total_expense=total_expense,
        total_savings=total_savings,
    )

    today = date.today()

    month_income = await income_service.get_monthly_income(user_id, today.year, today.month)
    month_expense = await spending_service.get_monthly_expenses(user_id, today.year, today.month)

    monthly_summary = MonthlySummary(
        month=f"{today.year}-{today.month:02d}",
        income=month_income,
        expense=month_expense,
        balance=month_income - month_expense,
    )

    tx_result = await db.execute(
        select(Transaction)
        .where(
            Transaction.user_id == user_id,
            Transaction.currency_code == current_user.default_currency_code,
        )
        .order_by(Transaction.transaction_date.desc())
        .limit(10)
    )
    recent_tx = tx_result.scalars().all()

    recent_transactions: list[RecentTransaction] = []
    for tx in recent_tx:
        category = await db.get(Category, tx.category_id)
        bank = await db.get(Bank, tx.bank_id)

        recent_transactions.append(
            RecentTransaction(
                id=tx.id,
                description=tx.description,
                amount=tx.amount,
                transaction_type=tx.transaction_type.value,
                category=category.name if category else "—",
                bank=bank.name if bank else "—",
                transaction_date=tx.transaction_date.isoformat(),
            )
        )

    top_categories_raw = await spending_service.get_top_categories(user_id, limit=5)

    total_expense_dec = total_expense if total_expense > 0 else Decimal("1")

    top_expense_categories = [
        ExpenseCategory(
            category=name,
            amount=Decimal(total),
            percentage=float(round((Decimal(total) / total_expense_dec) * 100, 2)),
        )
        for name, total in top_categories_raw
    ]

    budgets_result = await db.execute(select(Budget).where(Budget.user_id == user_id))
    budgets_overview = [
        BudgetOverview(
            budget_name=b.title,
            monthly_limit=b.monthly_limit,
            spent=b.spent,
            remaining=b.monthly_limit - b.spent,
            progress=budget_progress_percent(b.spent, b.monthly_limit),
        )
        for b in budgets_result.scalars().all()
    ]

    deposits_result = await db.execute(select(Deposit).where(Deposit.user_id == user_id))
    deposits_overview: list[DepositOverview] = []
    for d in deposits_result.scalars().all():
        bank = await db.get(Bank, d.bank_id)

        profit = expected_profit(d)

        deposits_overview.append(
            DepositOverview(
                bank_name=bank.name if bank else "—",
                amount=d.amount,
                interest_rate=d.interest_rate,
                expected_profit=profit,
                maturity_date=d.end_date.isoformat(),
            )
        )

    return DashboardResponse(
        balance=balance,
        monthly_summary=monthly_summary,
        recent_transactions=recent_transactions,
        top_expense_categories=top_expense_categories,
        budgets=budgets_overview,
        deposits=deposits_overview,
    )
