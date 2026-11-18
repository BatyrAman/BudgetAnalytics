from decimal import Decimal

from pydantic import BaseModel


class IncomeExpenseTrend(BaseModel):
    period: str
    income: Decimal
    expense: Decimal


class CategoryAnalytics(BaseModel):
    category: str
    amount: Decimal
    transaction_count: int
    percentage: float


class CashFlowAnalytics(BaseModel):
    total_income: Decimal
    total_expense: Decimal
    net_cash_flow: Decimal
    savings_rate: float


class MonthlyComparison(BaseModel):
    current_month_income: Decimal
    previous_month_income: Decimal

    current_month_expense: Decimal
    previous_month_expense: Decimal

    income_growth_percent: float
    expense_growth_percent: float


class SpendingForecast(BaseModel):
    next_month_expense: Decimal
    predicted_savings: Decimal
    confidence: float


class SavingsAnalytics(BaseModel):
    current_savings: Decimal
    target_savings: Decimal
    progress: float
    remaining: Decimal


class InvestmentAnalytics(BaseModel):
    invested_amount: Decimal
    expected_profit: Decimal
    expected_value: Decimal


class BankAnalytics(BaseModel):
    bank_name: str
    income: Decimal
    expense: Decimal
    transaction_count: int


class FinancialHealth(BaseModel):
    score: int
    status: str
    recommendation: str


class AIRecommendation(BaseModel):
    title: str
    description: str
    priority: str


class AnalyticsResponse(BaseModel):
    cash_flow: CashFlowAnalytics

    monthly_comparison: MonthlyComparison

    spending_forecast: SpendingForecast

    savings: SavingsAnalytics

    investment: InvestmentAnalytics

    financial_health: FinancialHealth

    income_expense_trend: list[IncomeExpenseTrend]

    categories: list[CategoryAnalytics]

    banks: list[BankAnalytics]

    recommendations: list[AIRecommendation]
