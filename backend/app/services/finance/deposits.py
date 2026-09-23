"""
Депозитный калькулятор.

* simple_interest — доход по вкладу без капитализации за период
  между датами (используется существующим API /investments).
* calculate_deposit — помесячная модель с капитализацией или без,
  с ежемесячным пополнением.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext
from enum import StrEnum

from app.services.finance.calendar import add_months
from app.services.finance.money import (
    HUNDRED,
    ONE,
    ZERO,
    MoneyError,
    quantize_money,
    quantize_percent,
    to_decimal,
)


class Capitalization(StrEnum):
    NONE = "none"
    MONTHLY = "monthly"


class DayCount(StrEnum):
    # Фиксированный 365-дневный год (исторически использовался API).
    ACT_365 = "ACT/365"
    # Фактические дни / дни в году (366 в високосном).
    ACT_ACT = "ACT/ACT"


class DepositError(MoneyError):
    pass


def _year_fraction(start: date, end: date, day_count: DayCount) -> Decimal:
    if end <= start:
        return ZERO
    if day_count is DayCount.ACT_365:
        return Decimal((end - start).days) / Decimal(365)

    fraction = ZERO
    cursor = start
    while cursor < end:
        year_end = date(cursor.year + 1, 1, 1)
        segment_end = min(year_end, end)
        days_in_year = 366 if _is_leap(cursor.year) else 365
        fraction += Decimal((segment_end - cursor).days) / Decimal(days_in_year)
        cursor = segment_end
    return fraction


def _is_leap(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def simple_interest(
    amount,
    annual_rate,
    start: date,
    end: date,
    day_count: DayCount = DayCount.ACT_365,
) -> Decimal:
    amount = to_decimal(amount)
    rate = to_decimal(annual_rate)
    if amount < 0:
        raise DepositError("Amount cannot be negative")
    if rate < 0:
        raise DepositError("Rate cannot be negative")
    with localcontext() as ctx:
        ctx.prec = 40
        return quantize_money(amount * rate / HUNDRED * _year_fraction(start, end, DayCount(day_count)))


@dataclass(frozen=True, slots=True)
class DepositMonth:
    month: int
    date: date | None
    interest: Decimal
    contribution: Decimal
    balance: Decimal


@dataclass(frozen=True, slots=True)
class DepositResult:
    amount: Decimal
    annual_rate: Decimal
    term_months: int
    capitalization: Capitalization
    monthly_topup: Decimal
    total_contributions: Decimal
    total_interest: Decimal
    final_amount: Decimal
    effective_annual_rate: Decimal
    months: tuple[DepositMonth, ...]


def calculate_deposit(
    amount,
    annual_rate,
    term_months: int,
    capitalization: Capitalization = Capitalization.MONTHLY,
    *,
    monthly_topup=ZERO,
    start_date: date | None = None,
) -> DepositResult:
    amount = quantize_money(amount)
    rate = to_decimal(annual_rate)
    topup = quantize_money(monthly_topup)
    capitalization = Capitalization(capitalization)

    if amount <= 0:
        raise DepositError("Deposit amount must be positive")
    if rate < 0:
        raise DepositError("Rate cannot be negative")
    if topup < 0:
        raise DepositError("Top-up cannot be negative")
    if not 1 <= term_months <= 600:
        raise DepositError("Term must be 1..600 months")

    r = rate / HUNDRED / Decimal(12)
    principal = amount  # сумма, на которую начисляются проценты
    paid_out_interest = ZERO
    total_interest = ZERO
    months: list[DepositMonth] = []

    for month in range(1, term_months + 1):
        interest = quantize_money(principal * r)
        total_interest += interest
        if capitalization is Capitalization.MONTHLY:
            principal += interest
        else:
            paid_out_interest += interest
        contribution = topup if month < term_months else ZERO
        principal += contribution
        months.append(
            DepositMonth(
                month=month,
                date=add_months(start_date, month) if start_date else None,
                interest=interest,
                contribution=contribution,
                balance=principal + paid_out_interest,
            )
        )

    contributions = amount + topup * (term_months - 1)

    with localcontext() as ctx:
        ctx.prec = 40
        if capitalization is Capitalization.MONTHLY:
            effective = ((ONE + r) ** 12 - ONE) * HUNDRED
        else:
            effective = rate

    return DepositResult(
        amount=amount,
        annual_rate=rate,
        term_months=term_months,
        capitalization=capitalization,
        monthly_topup=topup,
        total_contributions=contributions,
        total_interest=total_interest,
        final_amount=contributions + total_interest,
        effective_annual_rate=quantize_percent(effective),
        months=tuple(months),
    )
