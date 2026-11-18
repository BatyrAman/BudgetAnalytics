from decimal import Decimal

from pydantic import BaseModel


class BalanceCard(BaseModel):
    total_balance: Decimal
    total_income: Decimal
    total_expense: Decimal
    total_savings: Decimal


class MonthlySummary(BaseModel):
    month: str
    income: Decimal
    expense: Decimal
    balance: Decimal


class ExpenseCategory(BaseModel):
    category: str
    amount: Decimal
    percentage: float


class RecentTransaction(BaseModel):
    id: int
    description: str | None
    amount: Decimal
    transaction_type: str
    category: str
    bank: str
    transaction_date: str


class BudgetOverview(BaseModel):
    budget_name: str
    monthly_limit: Decimal
    spent: Decimal
    remaining: Decimal
    progress: float


class DepositOverview(BaseModel):
    bank_name: str
    amount: Decimal
    interest_rate: Decimal
    expected_profit: Decimal
    maturity_date: str


class DashboardResponse(BaseModel):
    balance: BalanceCard

    monthly_summary: MonthlySummary

    recent_transactions: list[RecentTransaction]

    top_expense_categories: list[ExpenseCategory]

    budgets: list[BudgetOverview]

    deposits: list[DepositOverview]
