from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import MoneyDecimal, NonNegativeMoney, PercentDecimal, PositiveMoney, RatePercent
from app.schemas.debt import InstallmentResponse
from app.services.finance.affordability import RiskLevel
from app.services.finance.deposits import Capitalization
from app.services.finance.emergency_fund import IncomeStability
from app.services.finance.loans import ScheduleType


class LoanParams(BaseModel):
    amount: PositiveMoney
    annual_rate: RatePercent
    term_months: int = Field(ge=1, le=600)
    schedule_type: ScheduleType = ScheduleType.ANNUITY


class LoanCalcRequest(LoanParams):
    upfront_fees: NonNegativeMoney = Decimal("0")
    monthly_fee: NonNegativeMoney = Decimal("0")
    start_date: date | None = None
    include_schedule: bool = False


class LoanCalcResponse(BaseModel):
    amount: MoneyDecimal
    annual_rate: PercentDecimal
    term_months: int
    schedule_type: ScheduleType
    monthly_payment: MoneyDecimal
    last_payment: MoneyDecimal
    total_payment: MoneyDecimal
    total_interest: MoneyDecimal
    total_fees: MoneyDecimal
    overpayment: MoneyDecimal
    effective_annual_rate: PercentDecimal
    schedule: list[InstallmentResponse] = []


class MortgageCalcRequest(BaseModel):
    price: PositiveMoney
    down_payment: NonNegativeMoney
    annual_rate: RatePercent
    term_years: int = Field(ge=1, le=35)
    schedule_type: ScheduleType = ScheduleType.ANNUITY
    include_schedule: bool = False


class MortgageCalcResponse(BaseModel):
    price: MoneyDecimal
    down_payment: MoneyDecimal
    down_payment_percent: PercentDecimal
    loan_amount: MoneyDecimal
    annual_rate: PercentDecimal
    term_months: int
    schedule_type: ScheduleType
    monthly_payment: MoneyDecimal
    max_monthly_payment: MoneyDecimal
    total_payment: MoneyDecimal
    total_interest: MoneyDecimal
    overpayment: MoneyDecimal
    required_monthly_income: MoneyDecimal
    existing_debt_payments: MoneyDecimal
    schedule: list[InstallmentResponse] = []


class DepositCalcRequest(BaseModel):
    amount: PositiveMoney
    annual_rate: RatePercent
    term_months: int = Field(ge=1, le=600)
    capitalization: Capitalization = Capitalization.MONTHLY
    monthly_topup: NonNegativeMoney = Decimal("0")


class DepositCalcResponse(BaseModel):
    amount: MoneyDecimal
    annual_rate: PercentDecimal
    term_months: int
    capitalization: Capitalization
    monthly_topup: MoneyDecimal
    total_contributions: MoneyDecimal
    total_interest: MoneyDecimal
    final_amount: MoneyDecimal
    effective_annual_rate: PercentDecimal


class AffordabilityRequest(BaseModel):
    """
    Новый платёж — напрямую (new_payment) или через параметры кредита
    (loan). Доход, обязательные расходы и текущие платежи по умолчанию
    берутся из профиля пользователя; их можно переопределить.
    """

    new_payment: NonNegativeMoney | None = None
    loan: LoanParams | None = None
    monthly_income: NonNegativeMoney | None = None
    mandatory_expenses: NonNegativeMoney | None = None
    existing_debt_payments: NonNegativeMoney | None = None

    @model_validator(mode="after")
    def _one_payment_source(self) -> "AffordabilityRequest":
        if (self.new_payment is None) == (self.loan is None):
            raise ValueError("Provide exactly one of new_payment or loan")
        return self


class AffordabilityReason(BaseModel):
    code: str
    message: str


class AffordabilityResponse(BaseModel):
    affordable: bool
    risk_level: RiskLevel
    current_debt_load: PercentDecimal | None
    projected_debt_load: PercentDecimal | None
    free_cash_flow: MoneyDecimal
    free_cash_flow_after: MoneyDecimal
    recommended_max_payment: MoneyDecimal
    new_payment: MoneyDecimal
    monthly_income: MoneyDecimal
    mandatory_expenses: MoneyDecimal
    existing_debt_payments: MoneyDecimal
    reasons: list[AffordabilityReason]
    # откуда взяты входные цифры: request | declared | transactions | debts | none
    sources: dict[str, str]


class EmergencyFundRequest(BaseModel):
    monthly_mandatory_expenses: NonNegativeMoney | None = None
    current_savings: NonNegativeMoney = Decimal("0")
    monthly_contribution: NonNegativeMoney = Decimal("0")
    target_months: int | None = Field(default=None, ge=1, le=24)
    income_stability: IncomeStability = IncomeStability.STABLE


class EmergencyFundResponse(BaseModel):
    monthly_mandatory_expenses: MoneyDecimal
    target_months: int
    target_amount: MoneyDecimal
    current_savings: MoneyDecimal
    gap: MoneyDecimal
    coverage_months: Decimal
    monthly_contribution: MoneyDecimal
    months_to_goal: int | None
    is_reached: bool


class FinancialProfileSummary(BaseModel):
    """Агрегаты без персональных данных — безопасно для AI-контекста."""

    currency: str
    monthly_income: MoneyDecimal | None
    income_source: str
    average_monthly_expenses: MoneyDecimal
    mandatory_expenses: MoneyDecimal
    debt_payments: MoneyDecimal
    debt_balance: MoneyDecimal
    active_debts: int
    dependents: int
    months_of_data: int
