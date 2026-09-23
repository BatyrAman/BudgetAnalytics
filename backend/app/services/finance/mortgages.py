"""Ипотечный калькулятор поверх loans.build_schedule."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.services.finance.loans import LoanError, LoanSchedule, ScheduleType, build_schedule
from app.services.finance.money import ZERO, percent, quantize_money, to_decimal

DEFAULT_MAX_DEBT_TO_INCOME = Decimal("0.40")
MAX_MORTGAGE_YEARS = 35


@dataclass(frozen=True, slots=True)
class MortgageResult:
    price: Decimal
    down_payment: Decimal
    down_payment_percent: Decimal
    loan_amount: Decimal
    annual_rate: Decimal
    term_months: int
    schedule_type: ScheduleType
    monthly_payment: Decimal
    max_monthly_payment: Decimal
    total_payment: Decimal
    total_interest: Decimal
    overpayment: Decimal
    # Минимальный доход, при котором платёж укладывается в max_dti
    # (с учётом уже существующих платежей по долгам).
    required_monthly_income: Decimal
    schedule: LoanSchedule


def calculate_mortgage(
    price,
    down_payment,
    annual_rate,
    term_years: int,
    schedule_type: ScheduleType = ScheduleType.ANNUITY,
    *,
    existing_debt_payments=ZERO,
    max_debt_to_income: Decimal = DEFAULT_MAX_DEBT_TO_INCOME,
) -> MortgageResult:
    price = quantize_money(price)
    down_payment = quantize_money(down_payment)
    existing = quantize_money(existing_debt_payments)
    max_dti = to_decimal(max_debt_to_income)

    if price <= 0:
        raise LoanError("Property price must be positive")
    if down_payment < 0:
        raise LoanError("Down payment cannot be negative")
    if down_payment >= price:
        raise LoanError("Down payment must be less than the price")
    if not 1 <= term_years <= MAX_MORTGAGE_YEARS:
        raise LoanError(f"Mortgage term must be 1..{MAX_MORTGAGE_YEARS} years")
    if not ZERO < max_dti <= 1:
        raise LoanError("max_debt_to_income must be in (0, 1]")

    loan_amount = price - down_payment
    schedule = build_schedule(loan_amount, annual_rate, term_years * 12, schedule_type)

    # Для дифференцированного графика самый большой платёж — первый.
    max_payment = max(i.payment for i in schedule.installments)
    required_income = quantize_money((max_payment + existing) / max_dti)

    return MortgageResult(
        price=price,
        down_payment=down_payment,
        down_payment_percent=percent(down_payment, price),
        loan_amount=loan_amount,
        annual_rate=to_decimal(annual_rate),
        term_months=schedule.term_months,
        schedule_type=ScheduleType(schedule_type),
        monthly_payment=schedule.first_payment,
        max_monthly_payment=max_payment,
        total_payment=schedule.total_payment,
        total_interest=schedule.total_interest,
        overpayment=schedule.overpayment,
        required_monthly_income=required_income,
        schedule=schedule,
    )
