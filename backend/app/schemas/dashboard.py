from pydantic import BaseModel

from app.schemas.common import MoneyDecimal, PercentDecimal


class BalanceCard(BaseModel):
    # Внимание: это «доходы минус расходы за всё время» по загруженным
    # операциям, а не остаток на счёте (выписки могут быть неполными).
    total_balance: MoneyDecimal
    total_income: MoneyDecimal
    total_expense: MoneyDecimal
    total_savings: MoneyDecimal


class MonthlySummary(BaseModel):
    month: str
    income: MoneyDecimal
    expense: MoneyDecimal
    balance: MoneyDecimal


class ExpenseCategory(BaseModel):
    category: str
    amount: MoneyDecimal
    percentage: float


class RecentTransaction(BaseModel):
    id: int
    description: str | None
    amount: MoneyDecimal
    transaction_type: str
    category: str
    bank: str
    transaction_date: str


class BudgetOverview(BaseModel):
    budget_name: str
    monthly_limit: MoneyDecimal
    spent: MoneyDecimal
    remaining: MoneyDecimal
    progress: float


class DepositOverview(BaseModel):
    bank_name: str
    amount: MoneyDecimal
    interest_rate: PercentDecimal
    expected_profit: MoneyDecimal
    maturity_date: str


class DashboardResponse(BaseModel):
    balance: BalanceCard

    monthly_summary: MonthlySummary

    recent_transactions: list[RecentTransaction]

    top_expense_categories: list[ExpenseCategory]

    budgets: list[BudgetOverview]

    deposits: list[DepositOverview]
