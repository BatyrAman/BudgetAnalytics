from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import DebtPaymentStatus, DebtScheduleType
from app.schemas.common import MoneyDecimal, NonNegativeMoney, PercentDecimal, PositiveMoney, RatePercent
from app.services.finance.affordability import RiskLevel
from app.services.finance.debt_strategy import DebtType, Strategy
from app.services.finance.loans import PrepaymentMode


class DebtCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    debt_type: DebtType
    bank_id: int | None = None
    principal: PositiveMoney = Field(description="Исходная сумма долга")
    balance: NonNegativeMoney | None = Field(
        default=None, description="Текущий остаток; по умолчанию = principal"
    )
    annual_rate: RatePercent = Field(description="Номинальная годовая ставка, %")
    gesv: RatePercent | None = Field(default=None, description="ГЭСВ из договора, %")
    monthly_payment: NonNegativeMoney | None = Field(
        default=None,
        description="Обязательный платёж. Если не указан — рассчитывается по сроку.",
    )
    payment_day: int = Field(ge=1, le=31)
    start_date: date
    end_date: date | None = None
    term_months: int | None = Field(default=None, ge=1, le=600)
    schedule_type: DebtScheduleType = DebtScheduleType.ANNUITY

    @model_validator(mode="after")
    def _check(self) -> "DebtCreate":
        if self.end_date is not None and self.end_date <= self.start_date:
            raise ValueError("end_date must be after start_date")
        if self.monthly_payment is None:
            if self.schedule_type is DebtScheduleType.REVOLVING:
                raise ValueError("monthly_payment is required for revolving debts")
            if self.end_date is None and self.term_months is None:
                raise ValueError("Provide monthly_payment, end_date or term_months")
        return self


class DebtUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    bank_id: int | None = None
    balance: NonNegativeMoney | None = None
    annual_rate: RatePercent | None = None
    gesv: RatePercent | None = None
    monthly_payment: NonNegativeMoney | None = None
    payment_day: int | None = Field(default=None, ge=1, le=31)
    end_date: date | None = None
    is_active: bool | None = None


class DebtResponse(BaseModel):
    id: int
    name: str
    debt_type: DebtType
    bank_id: int | None
    principal: MoneyDecimal
    balance: MoneyDecimal
    annual_rate: PercentDecimal
    gesv: PercentDecimal | None
    monthly_payment: MoneyDecimal
    payment_day: int
    start_date: date
    end_date: date | None
    schedule_type: DebtScheduleType
    currency: str
    is_active: bool
    closed_at: datetime | None
    created_at: datetime

    # --- расчётные поля (детерминированный прогноз при текущем платеже) ---
    paid_percent: PercentDecimal
    interest_paid: MoneyDecimal
    projected_months_left: int | None
    projected_payoff_date: date | None
    projected_remaining_interest: MoneyDecimal | None
    projected_total_overpayment: MoneyDecimal | None
    is_amortizing: bool

    model_config = ConfigDict(from_attributes=True)


class DebtTypeTotal(BaseModel):
    debt_type: DebtType
    count: int
    balance: MoneyDecimal


class UpcomingPayment(BaseModel):
    debt_id: int
    name: str
    debt_type: DebtType
    due_date: date
    amount: MoneyDecimal
    days_left: int
    is_paid: bool


class DebtSummary(BaseModel):
    currency: str
    active_debts: int
    total_balance: MoneyDecimal
    total_monthly_payment: MoneyDecimal
    monthly_income: MoneyDecimal | None
    income_source: str
    # платежи / доход * 100; null, если доход неизвестен
    debt_load: PercentDecimal | None
    debt_load_level: RiskLevel | None
    debt_free_date: date | None
    months_to_debt_free: int | None
    total_remaining_interest: MoneyDecimal | None
    payments_cover_interest: bool
    by_type: list[DebtTypeTotal]
    next_payment: UpcomingPayment | None


class StrategyRequest(BaseModel):
    extra_payment: NonNegativeMoney = Decimal("0")
    strategy: Strategy = Strategy.AVALANCHE
    include_timeline: bool = True


class PayoffItem(BaseModel):
    debt_id: int
    name: str
    month: int
    date: date
    interest_paid: MoneyDecimal
    total_paid: MoneyDecimal


class TimelinePoint(BaseModel):
    month: int
    date: date
    total_balance: MoneyDecimal
    interest: MoneyDecimal
    payment: MoneyDecimal
    balances: dict[str, MoneyDecimal]
    payments: dict[str, MoneyDecimal]


class StrategyOutcome(BaseModel):
    strategy: Strategy | None
    feasible: bool
    months: int
    payoff_date: date | None
    total_interest: MoneyDecimal
    total_paid: MoneyDecimal
    interest_saved_vs_minimum: MoneyDecimal | None = None
    extra_cost_vs_recommended: MoneyDecimal | None = None


class StrategyResponse(BaseModel):
    strategy: Strategy
    extra_payment: MoneyDecimal
    monthly_budget: MoneyDecimal
    feasible: bool
    reason: str | None
    months: int
    payoff_date: date | None
    total_interest: MoneyDecimal
    total_paid: MoneyDecimal
    payoff_order: list[PayoffItem]
    timeline: list[TimelinePoint]
    recommended_strategy: Strategy
    minimum_payments_only: StrategyOutcome
    comparison: list[StrategyOutcome]


class PrepaymentRequest(BaseModel):
    amount: PositiveMoney
    mode: PrepaymentMode = PrepaymentMode.SHORTEN_TERM


class PrepaymentResponse(BaseModel):
    debt_id: int
    mode: PrepaymentMode
    amount: MoneyDecimal
    fully_repaid: bool
    balance_before: MoneyDecimal
    balance_after: MoneyDecimal
    payment_before: MoneyDecimal
    payment_after: MoneyDecimal
    term_before: int
    term_after: int
    payoff_date_before: date | None
    payoff_date_after: date | None
    interest_before: MoneyDecimal
    interest_after: MoneyDecimal
    interest_saved: MoneyDecimal
    months_saved: int
    payment_reduced_by: MoneyDecimal


class InstallmentResponse(BaseModel):
    number: int
    due_date: date | None
    payment: MoneyDecimal
    principal: MoneyDecimal
    interest: MoneyDecimal
    balance_after: MoneyDecimal


class DebtScheduleResponse(BaseModel):
    debt_id: int
    is_amortizing: bool
    months: int
    total_payment: MoneyDecimal
    total_interest: MoneyDecimal
    installments: list[InstallmentResponse]


class DebtPaymentCreate(BaseModel):
    amount: PositiveMoney
    paid_at: date | None = None
    due_date: date | None = None
    transaction_id: int | None = None


class DebtPaymentResponse(BaseModel):
    id: int
    debt_id: int
    due_date: date
    amount: MoneyDecimal
    principal_part: MoneyDecimal
    interest_part: MoneyDecimal
    paid_at: date
    status: DebtPaymentStatus
    transaction_id: int | None

    model_config = ConfigDict(from_attributes=True)
