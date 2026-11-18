"""Derived indicators and account balances.

* ``percent_change(current, previous)`` = (current − previous) / |previous| × 100,
  rounded to 0.01 %. ``None`` when previous = 0 (a change from zero has no
  meaningful percentage — it is not reported as 100 % or infinity).
* ``share_percent(part, total)`` = part / total × 100, rounded to 0.01 %.
  ``None`` when total <= 0.
* ``expense_to_income_percent`` = net_expenses / income × 100 (``None`` when
  income = 0). Equals 100 − savings rate.
* ``emergency_fund_months(balance, average_monthly_expenses)`` = how many
  months the balance would cover at the average net spending, rounded to
  0.01 months. ``None`` when average spending <= 0. A negative balance gives
  0 months.
* ``account_balance(opening, sums)`` = opening + income + refund + transfer_in
  − expense − transfer_out, rounded to minor units. It is the balance of ONE
  account in ONE currency, from transactions linked to that account.
* ``average(values)`` = arithmetic mean, rounded to minor units; ``None`` for
  an empty list.
* ``months_until(today, target)`` = calendar months from today's month to the
  target month (e.g. 2025-03-20 -> 2025-06-01 = 3). ``None`` when the target
  month is the current month or in the past.
* ``required_monthly_saving(remaining, months)`` = remaining / months, rounded
  UP-half to minor units; 0 when nothing remains. Assumes equal monthly
  contributions and no interest.

Rounding: money ROUND_HALF_UP to currency minor units, percentages and
months to 0.01 (see ``money``).
"""

from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal

from app.models.enums import TransactionType
from app.services.finance.money import (
    HUNDRED,
    ZERO,
    CurrencySpec,
    FinanceInputError,
    calc_context,
    quantize_money,
    quantize_ratio_percent,
    to_decimal,
)

_INFLOWS = (TransactionType.INCOME, TransactionType.REFUND, TransactionType.TRANSFER_IN)
_OUTFLOWS = (TransactionType.EXPENSE, TransactionType.TRANSFER_OUT)


def percent_change(current: Decimal, previous: Decimal) -> Decimal | None:
    current = to_decimal(current, "current")
    previous = to_decimal(previous, "previous")
    if previous == 0:
        return None
    with calc_context():
        change = (current - previous) / abs(previous) * HUNDRED
    return quantize_ratio_percent(change)


def share_percent(part: Decimal, total: Decimal) -> Decimal | None:
    part = to_decimal(part, "part")
    total = to_decimal(total, "total")
    if total <= 0:
        return None
    with calc_context():
        share = part / total * HUNDRED
    return quantize_ratio_percent(share)


def expense_to_income_percent(income: Decimal, net_expenses: Decimal) -> Decimal | None:
    income = to_decimal(income, "income")
    if income < 0:
        raise FinanceInputError("income must not be negative")
    if income == 0:
        return None
    return share_percent(to_decimal(net_expenses, "net_expenses"), income)


def emergency_fund_months(balance: Decimal, average_monthly_expenses: Decimal) -> Decimal | None:
    balance = to_decimal(balance, "balance")
    average = to_decimal(average_monthly_expenses, "average_monthly_expenses")
    if average <= 0:
        return None
    with calc_context():
        months = max(balance, ZERO) / average
    return quantize_ratio_percent(months)  # 0.01 months, HALF_UP


def average(values: Sequence[Decimal], currency: CurrencySpec) -> Decimal | None:
    if not values:
        return None
    with calc_context():
        total = sum((to_decimal(v, "value") for v in values), ZERO)
        mean = total / Decimal(len(values))
    return quantize_money(mean, currency)


def account_balance(
    opening_balance: Decimal,
    sums: Mapping[TransactionType, Decimal],
    currency: CurrencySpec,
) -> Decimal:
    opening = to_decimal(opening_balance, "opening_balance")
    with calc_context():
        inflow = sum((to_decimal(sums.get(t, ZERO), "sum") for t in _INFLOWS), ZERO)
        outflow = sum((to_decimal(sums.get(t, ZERO), "sum") for t in _OUTFLOWS), ZERO)
        balance = opening + inflow - outflow
    return quantize_money(balance, currency)


def months_until(today: date, target: date) -> int | None:
    months = (target.year * 12 + target.month) - (today.year * 12 + today.month)
    return months if months > 0 else None


def required_monthly_saving(remaining: Decimal, months: int, currency: CurrencySpec) -> Decimal:
    remaining = to_decimal(remaining, "remaining")
    if isinstance(months, bool) or not isinstance(months, int) or months < 1:
        raise FinanceInputError("months must be a positive integer")
    if remaining <= 0:
        return quantize_money(ZERO, currency)
    with calc_context():
        monthly = remaining / Decimal(months)
    return quantize_money(monthly, currency)


__all__ = [
    "account_balance",
    "average",
    "emergency_fund_months",
    "expense_to_income_percent",
    "months_until",
    "percent_change",
    "required_monthly_saving",
    "share_percent",
]
