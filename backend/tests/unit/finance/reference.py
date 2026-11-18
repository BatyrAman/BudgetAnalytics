"""Independent reference implementation for test oracles.

Uses exact rational arithmetic (``fractions.Fraction``) and its own
half-up rounding and anniversary logic. It shares NO code with
``app.services.finance`` so a bug there cannot be mirrored here.
"""

import calendar
from datetime import date
from decimal import Decimal
from fractions import Fraction


def frac(value: str | int) -> Fraction:
    return Fraction(value)


def round_half_up(value: Fraction, places: int) -> Decimal:
    scaled = value * 10**places
    sign = -1 if scaled < 0 else 1
    magnitude = abs(scaled)
    whole = magnitude.numerator // magnitude.denominator
    if magnitude - whole >= Fraction(1, 2):
        whole += 1
    return Decimal(sign * whole).scaleb(-places)


def simple_interest(principal: str, rate_percent: str, days: int, basis: int = 365) -> Decimal:
    value = frac(principal) * frac(rate_percent) / 100 * days / basis
    return round_half_up(value, 2)


def compound_amount(principal: str, rate_percent: str, per_year: int, periods: int) -> Decimal:
    value = frac(principal) * (1 + frac(rate_percent) / 100 / per_year) ** periods
    return round_half_up(value, 2)


def effective_annual_rate(rate_percent: str, per_year: int) -> Decimal:
    value = ((1 + frac(rate_percent) / 100 / per_year) ** per_year - 1) * 100
    return round_half_up(value, 4)


def real_return(nominal_percent: str, inflation_percent: str) -> Decimal:
    value = ((1 + frac(nominal_percent) / 100) / (1 + frac(inflation_percent) / 100) - 1) * 100
    return round_half_up(value, 4)


def _anniversary(start: date, months: int) -> date:
    year, month = start.year, start.month
    for _ in range(months):
        month += 1
        if month == 13:
            year, month = year + 1, 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(start.day, last_day))


def compounded_deposit_interest(
    principal: str, rate_percent: str, start: date, end: date, months_per_period: int
) -> tuple[Decimal, int, int]:
    """(interest, full periods, stub days) per the documented convention."""

    periods = 0
    while _anniversary(start, (periods + 1) * months_per_period) <= end:
        periods += 1
    stub_days = (end - _anniversary(start, periods * months_per_period)).days
    rate = frac(rate_percent) / 100
    balance = frac(principal) * (1 + rate * months_per_period / 12) ** periods
    total = balance + balance * rate * stub_days / 365
    return round_half_up(total - frac(principal), 2), periods, stub_days
