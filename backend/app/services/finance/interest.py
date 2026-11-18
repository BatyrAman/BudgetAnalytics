"""Interest-rate mathematics.

All rates are ANNUAL and given in PERCENT (``Decimal("14")`` = 14 % p.a.),
and they are NOMINAL unless the name says otherwise. Results follow the
rounding policy in ``money``: money to currency minor units (ROUND_HALF_UP),
rates to 0.0001 %.

Formulas (r = rate / 100):

* Simple interest (day-count ``basis`` = 365 or 360 days per year):
      I = P · r · days / basis
* Compound amount after ``n`` whole periods, ``m`` periods per year:
      A = P · (1 + r/m)^n,       compound interest = A − P
* Effective annual rate (EAR) of a nominal rate compounded m times a year:
      EAR = (1 + r/m)^m − 1
* Real (inflation-adjusted) return, exact Fisher relation:
      real = (1 + nominal) / (1 + inflation) − 1
  (NOT the approximation ``nominal − inflation``).

EAR is a pure compounding conversion. It is NOT the ГЭСВ (годовая эффективная
ставка вознаграждения) published by Kazakhstan banks, which also accounts for
fees and the actual cash-flow schedule. Never present one as the other.

Validation: principal and rates must be >= 0 (negative nominal rates are not
supported); rates above ``MAX_RATE_PERCENT`` are rejected as implausible;
``periods_per_year`` must be >= 1 and ``periods``/``days`` >= 0 integers.
Inflation must be > −100 %; nominal return must be >= −100 %.
"""

import enum
from decimal import Decimal

from app.services.finance.money import (
    HUNDRED,
    KZT,
    ONE,
    CurrencySpec,
    FinanceInputError,
    calc_context,
    quantize_money,
    quantize_rate_percent,
    require_non_negative,
    to_decimal,
)

MAX_RATE_PERCENT = Decimal(1000)


class DayCount(enum.IntEnum):
    """Days-per-year basis for simple interest on a day count.

    ACT_365_FIXED: actual days / 365 (leap years still divide by 365).
    ACT_360:       actual days / 360.
    """

    ACT_365_FIXED = 365
    ACT_360 = 360


def validate_rate_percent(
    rate_percent: Decimal | int, name: str = "annual_rate_percent"
) -> Decimal:
    rate = require_non_negative(rate_percent, name)
    if rate > MAX_RATE_PERCENT:
        raise FinanceInputError(f"{name} above {MAX_RATE_PERCENT}% is not supported")
    return rate


def _non_negative_int(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be int")
    if value < 0:
        raise FinanceInputError(f"{name} must not be negative")
    return value


def _periods_per_year(value: int) -> int:
    value = _non_negative_int(value, "periods_per_year")
    if value < 1:
        raise FinanceInputError("periods_per_year must be at least 1")
    return value


def simple_interest(
    principal: Decimal | int,
    annual_rate_percent: Decimal | int,
    days: int,
    currency: CurrencySpec = KZT,
    day_count: DayCount = DayCount.ACT_365_FIXED,
) -> Decimal:
    p = require_non_negative(principal, "principal")
    r = validate_rate_percent(annual_rate_percent)
    d = _non_negative_int(days, "days")
    with calc_context():
        interest = p * r / HUNDRED * Decimal(d) / Decimal(int(day_count))
    return quantize_money(interest, currency)


def compound_amount_exact(
    principal: Decimal | int,
    annual_rate_percent: Decimal | int,
    periods_per_year: int,
    periods: int,
) -> Decimal:
    """Unrounded A = P · (1 + r/m)^n (for composing further calculations)."""

    p = require_non_negative(principal, "principal")
    r = validate_rate_percent(annual_rate_percent)
    m = _periods_per_year(periods_per_year)
    n = _non_negative_int(periods, "periods")
    with calc_context():
        return p * (ONE + r / HUNDRED / Decimal(m)) ** n


def compound_amount(
    principal: Decimal | int,
    annual_rate_percent: Decimal | int,
    periods_per_year: int,
    periods: int,
    currency: CurrencySpec = KZT,
) -> Decimal:
    """Future value A = P · (1 + r/m)^n, rounded once to minor units."""

    return quantize_money(
        compound_amount_exact(principal, annual_rate_percent, periods_per_year, periods),
        currency,
    )


def compound_interest(
    principal: Decimal | int,
    annual_rate_percent: Decimal | int,
    periods_per_year: int,
    periods: int,
    currency: CurrencySpec = KZT,
) -> Decimal:
    """A − P, computed from the unrounded A and rounded once."""

    exact = compound_amount_exact(principal, annual_rate_percent, periods_per_year, periods)
    with calc_context():
        interest = exact - to_decimal(principal, "principal")
    return quantize_money(interest, currency)


def effective_annual_rate(nominal_rate_percent: Decimal | int, periods_per_year: int) -> Decimal:
    """EAR in percent, rounded to 0.0001 %. ``periods_per_year=1`` returns the
    nominal rate itself."""

    r = validate_rate_percent(nominal_rate_percent, "nominal_rate_percent")
    m = _periods_per_year(periods_per_year)
    with calc_context():
        ear = ((ONE + r / HUNDRED / Decimal(m)) ** m - ONE) * HUNDRED
    return quantize_rate_percent(ear)


def inflation_adjusted_return(
    nominal_return_percent: Decimal | int, inflation_percent: Decimal | int
) -> Decimal:
    """Real return in percent (exact Fisher relation), rounded to 0.0001 %.

    Both inputs are for the SAME period (e.g. both annual). Negative values
    are allowed (loss, deflation) within the stated bounds.
    """

    nominal = to_decimal(nominal_return_percent, "nominal_return_percent")
    inflation = to_decimal(inflation_percent, "inflation_percent")
    if nominal < -HUNDRED:
        raise FinanceInputError("nominal_return_percent must be at least -100")
    if inflation <= -HUNDRED:
        raise FinanceInputError("inflation_percent must be greater than -100")
    if nominal > MAX_RATE_PERCENT or inflation > MAX_RATE_PERCENT:
        raise FinanceInputError(f"rates above {MAX_RATE_PERCENT}% are not supported")
    with calc_context():
        real = ((ONE + nominal / HUNDRED) / (ONE + inflation / HUNDRED) - ONE) * HUNDRED
    return quantize_rate_percent(real)
