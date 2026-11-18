"""Response schemas of the engine-based analytics and dashboard endpoints.

All money is ``Decimal`` (serialized as a JSON string), rounded to the
currency's minor units. Percentages are ``Decimal`` with 2 decimals.
``null`` means "undefined" (e.g. savings rate with zero income), never 0.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

CASH_FLOW_NOTE = (
    "Net cash flow covers only the transactions in the period; it is not an account balance. "
    "Refunds reduce expenses; transfers between own accounts are excluded."
)


class PeriodInfo(BaseModel):
    date_from: date
    date_to: date = Field(description="Inclusive")
    timezone: str


class SummaryResponse(BaseModel):
    period: PeriodInfo
    currency_code: str
    income: Decimal
    gross_expenses: Decimal
    refunds: Decimal
    net_expenses: Decimal
    net_cash_flow: Decimal
    transfers_in: Decimal
    transfers_out: Decimal
    savings_rate: Decimal | None = Field(description="% of income; null when income is 0")
    transaction_count: int
    note: str = CASH_FLOW_NOTE


class CategoryAmountResponse(BaseModel):
    category_id: int
    name: str
    amount: Decimal
    transaction_count: int
    share_percent: Decimal | None


class IncomeSummaryResponse(BaseModel):
    period: PeriodInfo
    currency_code: str
    total: Decimal
    by_category: list[CategoryAmountResponse]


class ExpenseSummaryResponse(BaseModel):
    period: PeriodInfo
    currency_code: str
    gross_expenses: Decimal
    refunds: Decimal
    net_expenses: Decimal
    by_category: list[CategoryAmountResponse]


class SavingsRateResponse(BaseModel):
    period: PeriodInfo
    currency_code: str
    income: Decimal
    net_expenses: Decimal
    savings_rate: Decimal | None
    expense_to_income_percent: Decimal | None


class CategoryBreakdownResponse(BaseModel):
    period: PeriodInfo
    currency_code: str
    kind: Literal["expense", "income"]
    total: Decimal
    items: list[CategoryAmountResponse]


class MonthSummary(BaseModel):
    month: str = Field(examples=["2025-03"])
    income: Decimal
    net_expenses: Decimal
    net_cash_flow: Decimal
    savings_rate: Decimal | None
    transaction_count: int


class MonthlyResponse(BaseModel):
    year: int
    timezone: str
    currency_code: str
    months: list[MonthSummary]
    total: MonthSummary


class MetricChangeResponse(BaseModel):
    current: Decimal
    previous: Decimal
    change: Decimal
    change_percent: Decimal | None = Field(description="null when the previous value is 0")


class ComparisonResponse(BaseModel):
    timezone: str
    currency_code: str
    current: MonthSummary
    previous: MonthSummary
    income: MetricChangeResponse
    net_expenses: MetricChangeResponse
    net_cash_flow: MetricChangeResponse
    savings_rate_change_pp: Decimal | None = Field(description="Percentage points")


# ---------------------------------------------------------------- dashboard
class AccountBalance(BaseModel):
    account_id: int
    name: str
    currency_code: str
    balance: Decimal


class BudgetStatus(BaseModel):
    budget_id: int
    title: str
    limit: Decimal
    spent: Decimal
    utilization_percent: Decimal
    is_exceeded: bool


class Indicators(BaseModel):
    savings_rate: Decimal | None
    expense_to_income_percent: Decimal | None
    expense_change_percent: Decimal | None = Field(description="vs previous month")
    income_change_percent: Decimal | None = Field(description="vs previous month")
    average_monthly_expenses_3m: Decimal | None = Field(
        description="Average net expenses of the last 3 complete months"
    )
    emergency_fund_months: Decimal | None = Field(
        description="current_balance / average_monthly_expenses_3m; null if either is unavailable"
    )
    budgets_exceeded: int
    budgets_total: int
    deposits_principal: Decimal
    deposits_expected_interest: Decimal


class OverviewResponse(BaseModel):
    generated_at: datetime
    timezone: str
    currency_code: str
    month: str
    current_balance: Decimal | None = Field(
        description="Sum of the user's active account balances in this currency; "
        "null when the user has no accounts in it"
    )
    accounts: list[AccountBalance]
    monthly_income: Decimal
    monthly_expenses: Decimal = Field(description="Net expenses (expenses − refunds)")
    monthly_net_cash_flow: Decimal
    budgets: list[BudgetStatus]
    indicators: Indicators
    notes: list[str]
