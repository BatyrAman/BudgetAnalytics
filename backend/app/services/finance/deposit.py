"""Deposit maturity.

INPUTS: principal P (>= 0), NOMINAL annual rate in percent (0..1000),
start_date < end_date (a zero or negative term is an input error), a
capitalization mode and a day-count basis (default ACT/365 Fixed).

CAPITALIZATION = NONE (simple interest, paid at maturity):

    interest = P · r · term_days / 365

    This is exactly the formula the API used before capitalization existed.

CAPITALIZATION = MONTHLY / QUARTERLY / ANNUALLY (k = 1 / 3 / 12 months):

    Capitalization dates are the k-month anniversaries of ``start_date``,
    computed from the start each time with end-of-month clamping
    (31 Jan -> 28/29 Feb -> 31 Mar). Let n be the number of anniversaries
    on or before ``end_date`` and ``stub_days`` the days from the last
    anniversary to ``end_date``. Then

        balance_n = P · (1 + r · k/12)^n          (periodic rate r·k/12,
                                                   independent of month length)
        stub      = balance_n · r · stub_days / 365     (simple, not compounded)
        interest  = balance_n + stub − P

ROUNDING: no intermediate rounding; the total interest is rounded once to the
currency's minor units (ROUND_HALF_UP) and maturity = P + interest.

LIMITATIONS (stated to users): banks typically accrue interest daily on the
actual balance, may round at each capitalization, apply contract-specific
rules for early withdrawal/top-ups and publish an effective rate (ГЭСВ) that
includes conditions not modelled here. Results are estimates and may differ
from the bank's figures.
"""

import calendar
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.models.enums import Capitalization
from app.services.finance.interest import (
    DayCount,
    compound_amount_exact,
    simple_interest,
    validate_rate_percent,
)
from app.services.finance.money import (
    HUNDRED,
    KZT,
    CurrencySpec,
    FinanceInputError,
    calc_context,
    quantize_money,
    require_non_negative,
)

_MONTHS_PER_PERIOD = {
    Capitalization.MONTHLY: 1,
    Capitalization.QUARTERLY: 3,
    Capitalization.ANNUALLY: 12,
}


@dataclass(frozen=True)
class DepositMaturity:
    currency_code: str
    principal: Decimal
    start_date: date
    maturity_date: date
    term_days: int
    capitalization: Capitalization
    capitalization_periods: int
    stub_days: int
    interest: Decimal
    maturity_amount: Decimal


def add_months(start: date, months: int) -> date:
    """``start`` shifted by ``months`` calendar months, clamped to month end."""

    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def deposit_maturity(
    principal: Decimal | int,
    annual_rate_percent: Decimal | int,
    start_date: date,
    end_date: date,
    capitalization: Capitalization = Capitalization.NONE,
    currency: CurrencySpec = KZT,
    day_count: DayCount = DayCount.ACT_365_FIXED,
) -> DepositMaturity:
    p = require_non_negative(principal, "principal")
    r = validate_rate_percent(annual_rate_percent)
    if not isinstance(start_date, date) or not isinstance(end_date, date):
        raise TypeError("start_date and end_date must be dates")
    if end_date <= start_date:
        raise FinanceInputError("end_date must be after start_date (term must be positive)")
    capitalization = Capitalization(capitalization)
    term_days = (end_date - start_date).days

    if capitalization is Capitalization.NONE:
        interest = simple_interest(p, r, term_days, currency, day_count)
        periods, stub_days = 0, term_days
    else:
        months = _MONTHS_PER_PERIOD[capitalization]
        periods = 0
        while add_months(start_date, (periods + 1) * months) <= end_date:
            periods += 1
        last_capitalization = add_months(start_date, periods * months)
        stub_days = (end_date - last_capitalization).days

        balance = compound_amount_exact(p, r, 12 // months, periods)
        with calc_context():
            stub = balance * r / HUNDRED * Decimal(stub_days) / Decimal(int(day_count))
            interest = quantize_money(balance + stub - p, currency)

    return DepositMaturity(
        currency_code=currency.code,
        principal=quantize_money(p, currency),
        start_date=start_date,
        maturity_date=end_date,
        term_days=term_days,
        capitalization=capitalization,
        capitalization_periods=periods,
        stub_days=stub_days,
        interest=interest,
        maturity_amount=quantize_money(p + interest, currency),
    )


__all__ = ["DepositMaturity", "add_months", "deposit_maturity", "FinanceInputError"]
