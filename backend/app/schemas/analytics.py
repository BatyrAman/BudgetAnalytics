from pydantic import BaseModel

from app.schemas.common import MoneyDecimal


class IncomeExpenseTrend(BaseModel):
    period: str
    income: MoneyDecimal
    expense: MoneyDecimal


class CategoryAnalytics(BaseModel):
    category: str
    amount: MoneyDecimal
    transaction_count: int
    percentage: float


class CashFlowAnalytics(BaseModel):
    total_income: MoneyDecimal
    total_expense: MoneyDecimal
    net_cash_flow: MoneyDecimal
    savings_rate: float


class MonthlyComparison(BaseModel):
    current_month_income: MoneyDecimal
    previous_month_income: MoneyDecimal

    current_month_expense: MoneyDecimal
    previous_month_expense: MoneyDecimal

    income_growth_percent: float
    expense_growth_percent: float


class SpendingForecast(BaseModel):
    next_month_expense: MoneyDecimal
    predicted_savings: MoneyDecimal
    confidence: float


class SavingsAnalytics(BaseModel):
    current_savings: MoneyDecimal
    target_savings: MoneyDecimal
    progress: float
    remaining: MoneyDecimal


class InvestmentAnalytics(BaseModel):
    invested_amount: MoneyDecimal
    expected_profit: MoneyDecimal
    expected_value: MoneyDecimal


class BankAnalytics(BaseModel):
    bank_name: str
    income: MoneyDecimal
    expense: MoneyDecimal
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