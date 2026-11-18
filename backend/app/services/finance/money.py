"""Monetary primitives and the central rounding policy.

POLICY (applies to every function in ``app.services.finance``):

* Inputs must be ``Decimal`` (or ``int``). ``float`` is rejected with
  ``TypeError`` — binary floating point cannot represent most decimal amounts.
  NaN and ±Infinity are rejected with ``FinanceInputError``.
* Intermediate arithmetic runs in a local Decimal context with
  ``CALC_PRECISION`` significant digits and NO intermediate rounding to
  currency units. Rounding happens exactly once, on the final result.
* Money is rounded to the currency's ``minor_units`` (KZT/USD/EUR/RUB: 2)
  with ``ROUND_HALF_UP`` (commercial rounding: 0.005 -> 0.01).
* Rates are returned in PERCENT rounded to ``RATE_PERCENT_PLACES`` (4)
  decimal places, e.g. ``Decimal("12.6825")`` = 12.6825 %.
* Ratios shown to users (savings rate, budget utilization) are percentages
  rounded to ``RATIO_PERCENT_PLACES`` (2) decimal places.

Real banks may round differently (per day, per capitalization period, or with
banker's rounding); results can therefore differ by a few minor units from a
bank statement. This is stated in every user-facing calculation.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import (
    ROUND_HALF_EVEN,
    ROUND_HALF_UP,
    Decimal,
    DivisionByZero,
    InvalidOperation,
    Overflow,
    localcontext,
)

MONEY_ROUNDING = ROUND_HALF_UP
CALC_PRECISION = 50
RATE_PERCENT_PLACES = 4
RATIO_PERCENT_PLACES = 2
HUNDRED = Decimal(100)
ZERO = Decimal(0)
ONE = Decimal(1)


class FinanceInputError(ValueError):
    """Invalid input for a financial calculation (negative principal, empty
    term, mixed currencies, ...). Message is safe to show to the user."""


@dataclass(frozen=True)
class CurrencySpec:
    """Currency identity and precision. ``minor_units`` comes from the
    ``currencies`` table (ISO 4217)."""

    code: str
    minor_units: int = 2

    def __post_init__(self) -> None:
        if len(self.code) != 3 or not self.code.isalpha() or not self.code.isupper():
            raise FinanceInputError(f"Invalid ISO 4217 currency code: {self.code!r}")
        if not 0 <= self.minor_units <= 4:
            raise FinanceInputError(f"Invalid minor units for {self.code}: {self.minor_units}")


KZT = CurrencySpec("KZT", 2)


@contextmanager
def calc_context() -> Iterator[None]:
    """High-precision context for intermediate results; traps invalid
    operations, division by zero and overflow instead of returning NaN/Inf."""

    with localcontext() as ctx:
        ctx.prec = CALC_PRECISION
        ctx.rounding = ROUND_HALF_EVEN
        ctx.traps[InvalidOperation] = True
        ctx.traps[DivisionByZero] = True
        ctx.traps[Overflow] = True
        yield


def to_decimal(value: Decimal | int, name: str) -> Decimal:
    """Validate a numeric input. Accepts Decimal and int only."""

    if isinstance(value, bool) or not isinstance(value, Decimal | int):
        raise TypeError(f"{name} must be Decimal or int, got {type(value).__name__}")
    result = Decimal(value)
    if not result.is_finite():
        raise FinanceInputError(f"{name} must be a finite number")
    return result


def require_non_negative(value: Decimal | int, name: str) -> Decimal:
    result = to_decimal(value, name)
    if result < 0:
        raise FinanceInputError(f"{name} must not be negative")
    return result


def require_positive(value: Decimal | int, name: str) -> Decimal:
    result = to_decimal(value, name)
    if result <= 0:
        raise FinanceInputError(f"{name} must be greater than zero")
    return result


def quantize_money(amount: Decimal, currency: CurrencySpec = KZT) -> Decimal:
    exponent = ONE.scaleb(-currency.minor_units)
    with calc_context():
        return amount.quantize(exponent, rounding=MONEY_ROUNDING)


def quantize_rate_percent(value: Decimal) -> Decimal:
    with calc_context():
        return value.quantize(ONE.scaleb(-RATE_PERCENT_PLACES), rounding=MONEY_ROUNDING)


def quantize_ratio_percent(value: Decimal) -> Decimal:
    with calc_context():
        return value.quantize(ONE.scaleb(-RATIO_PERCENT_PLACES), rounding=MONEY_ROUNDING)
