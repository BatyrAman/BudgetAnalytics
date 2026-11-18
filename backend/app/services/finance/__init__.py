"""Deterministic financial calculation engine.

Pure functions over ``Decimal``: no database, no HTTP, no LLM, no clock (the
current date is always passed in). Every number a user sees about money,
rates or savings must originate here or in SQL aggregates of stored amounts.
An LLM may only *explain* results produced by this package; it must never
compute, change or invent them.

Modules and their documented assumptions:

* ``money``    — input validation, Decimal context, rounding policy, currencies
* ``cashflow`` — income, expenses, refunds, transfers, net cash flow, savings rate
* ``periods``  — month/year boundaries in a time zone, monthly/yearly summaries
* ``budget``   — budget utilization
* ``interest`` — simple/compound interest, effective annual rate, real return
* ``deposit``  — deposit maturity with or without capitalization
* ``indicators`` — percent change, shares, account balance, emergency fund
"""

from app.services.finance.budget import BudgetUtilization, budget_utilization
from app.services.finance.cashflow import (
    CashflowItem,
    CashflowTotals,
    net_cash_flow,
    savings_rate,
    summarize,
    summarize_by_currency,
    total_expenses,
    total_income,
    totals_from_sums,
)
from app.services.finance.deposit import DepositMaturity, add_months, deposit_maturity
from app.services.finance.indicators import (
    account_balance,
    average,
    emergency_fund_months,
    expense_to_income_percent,
    percent_change,
    share_percent,
)
from app.services.finance.interest import (
    DayCount,
    compound_amount,
    compound_interest,
    effective_annual_rate,
    inflation_adjusted_return,
    simple_interest,
)
from app.services.finance.money import KZT, CurrencySpec, FinanceInputError
from app.services.finance.periods import (
    Period,
    PeriodSummary,
    month_period,
    monthly_summaries,
    summarize_period,
    year_period,
    yearly_summary,
)

__all__ = [
    "KZT",
    "BudgetUtilization",
    "CashflowItem",
    "CashflowTotals",
    "CurrencySpec",
    "DayCount",
    "DepositMaturity",
    "FinanceInputError",
    "Period",
    "PeriodSummary",
    "account_balance",
    "add_months",
    "average",
    "budget_utilization",
    "compound_amount",
    "compound_interest",
    "deposit_maturity",
    "effective_annual_rate",
    "emergency_fund_months",
    "expense_to_income_percent",
    "inflation_adjusted_return",
    "month_period",
    "monthly_summaries",
    "net_cash_flow",
    "percent_change",
    "savings_rate",
    "share_percent",
    "simple_interest",
    "summarize",
    "summarize_by_currency",
    "summarize_period",
    "total_expenses",
    "total_income",
    "totals_from_sums",
    "year_period",
    "yearly_summary",
]
