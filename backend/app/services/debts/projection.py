"""
Связка модели Debt с чистыми калькуляторами finance/*.

Прогноз строится от текущего остатка при текущем обязательном
платеже: так работают и аннуитет (платёж фиксирован договором),
и кредитки/личные долги (известен только минимальный платёж).
Для дифференцированного графика с известной датой окончания
строится дифференцированный график на оставшийся срок.
"""

from __future__ import annotations

from datetime import date

from app.models.debt import Debt
from app.models.enums import DebtScheduleType
from app.services.finance.calendar import add_months, count_payment_dates, next_payment_date
from app.services.finance.debt_strategy import DebtInput
from app.services.finance.loans import (
    LoanError,
    LoanSchedule,
    ScheduleType,
    annuity_payment,
    build_schedule,
    schedule_with_fixed_payment,
)


def remaining_months_by_contract(debt: Debt, today: date) -> int | None:
    if debt.end_date is None:
        return None
    return max(count_payment_dates(today, debt.end_date, debt.payment_day), 1)


def schedule_anchor(debt: Debt, today: date) -> date:
    """Дата, от которой отсчитываются платежи: предыдущий день платежа."""

    first = next_payment_date(today, debt.payment_day)
    return add_months(first, -1, debt.payment_day)


def project(debt: Debt, today: date) -> LoanSchedule | None:
    """График оставшихся платежей; None — долг закрыт или не амортизируется."""

    if debt.balance <= 0:
        return None
    anchor = schedule_anchor(debt, today)
    try:
        if debt.schedule_type == DebtScheduleType.DIFFERENTIAL and debt.end_date is not None:
            return build_schedule(
                debt.balance,
                debt.annual_rate,
                remaining_months_by_contract(debt, today),
                ScheduleType.DIFFERENTIAL,
                start_date=anchor,
                payment_day=debt.payment_day,
            )
        return schedule_with_fixed_payment(
            debt.balance,
            debt.annual_rate,
            debt.monthly_payment,
            start_date=anchor,
            payment_day=debt.payment_day,
        )
    except LoanError:
        return None


def initial_payment(
    balance,
    annual_rate,
    schedule_type: DebtScheduleType,
    term_months: int,
):
    """Обязательный платёж, если пользователь не указал его сам."""

    if schedule_type == DebtScheduleType.DIFFERENTIAL:
        return build_schedule(balance, annual_rate, term_months, ScheduleType.DIFFERENTIAL).first_payment
    return annuity_payment(balance, annual_rate, term_months)


def to_strategy_input(debt: Debt) -> DebtInput:
    return DebtInput(
        id=debt.id,
        name=debt.name,
        debt_type=debt.debt_type,
        balance=debt.balance,
        annual_rate=debt.annual_rate,
        minimum_payment=debt.monthly_payment,
    )
