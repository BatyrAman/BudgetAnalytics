"""Deposit maturity.

INPUTS: principal P (>= 0), NOMINAL annual rate in percent (0..1000),
start_date < end_date (a zero or negative term is an input error), a
capitalization mode and a day-count basis (default ACT/365 Fixed).

TERM BOUNDS (input errors, see ``deposit_term_issue``): both dates within
MIN_DEPOSIT_DATE..MAX_DEPOSIT_DATE (1900-01-01..2200-12-31) and
end_date <= add_months(start_date, MAX_DEPOSIT_TERM_MONTHS) (600 months =
50 years). The bound keeps every accepted input inside ``date`` arithmetic
and bounds the capitalization loop; real deposits are far shorter.

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

MIN_DEPOSIT_DATE = date(1900, 1, 1)
MAX_DEPOSIT_DATE = date(2200, 12, 31)
MAX_DEPOSIT_TERM_MONTHS = 600

# Stable, machine-readable codes of a deposit term problem. They carry no
# financial data and are safe to return to the client.
TERM_NOT_POSITIVE = "invalid_date_range"
DATE_OUT_OF_RANGE = "date_out_of_range"
TERM_TOO_LONG = "term_too_long"

_TERM_ISSUE_MESSAGES = {
    TERM_NOT_POSITIVE: "end_date must be after start_date",
    DATE_OUT_OF_RANGE: "Deposit dates must be between 1900-01-01 and 2200-12-31",
    TERM_TOO_LONG: "Deposit term must not exceed 600 months",
}

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


def deposit_term_issue(start_date: date, end_date: date) -> str | None:
    """The code of the first rule a deposit term breaks, or ``None`` if valid.

    Checked in this order: date range, positive term, maximum term. The
    date range goes first so ``add_months`` below never leaves ``date``.
    """

    for d in (start_date, end_date):
        if not MIN_DEPOSIT_DATE <= d <= MAX_DEPOSIT_DATE:
            return DATE_OUT_OF_RANGE
    if end_date <= start_date:
        return TERM_NOT_POSITIVE
    if end_date > add_months(start_date, MAX_DEPOSIT_TERM_MONTHS):
        return TERM_TOO_LONG
    return None


def term_issue_message(code: str) -> str:
    """A user-safe English message for a ``deposit_term_issue`` code."""

    return _TERM_ISSUE_MESSAGES[code]


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
    issue = deposit_term_issue(start_date, end_date)
    if issue == TERM_NOT_POSITIVE:
        raise FinanceInputError("end_date must be after start_date (term must be positive)")
    if issue is not None:
        raise FinanceInputError(term_issue_message(issue))
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


__all__ = [
    "DATE_OUT_OF_RANGE",
    "MAX_DEPOSIT_DATE",
    "MAX_DEPOSIT_TERM_MONTHS",
    "MIN_DEPOSIT_DATE",
    "TERM_NOT_POSITIVE",
    "TERM_TOO_LONG",
    "DepositMaturity",
    "FinanceInputError",
    "add_months",
    "deposit_maturity",
    "deposit_term_issue",
    "term_issue_message",
]
