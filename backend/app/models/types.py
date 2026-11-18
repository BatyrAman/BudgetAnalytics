"""Shared column types for the financial domain.

Money is stored as NUMERIC(18, 2): up to 9 999 999 999 999 999.99 with exact
decimal arithmetic. In this release every stored currency must have exactly 2
minor units (CHECK on ``currencies.minor_units``), so stored amounts and
currency precision always agree. Supporting 0- or 3-decimal currencies (JPY,
KWD) requires an explicit schema change; the finance engine itself already
handles any precision.

Annual rates are stored in percent as NUMERIC(7, 4), e.g. ``14.5000`` = 14.5 %.
"""

from sqlalchemy import CHAR, Numeric

MONEY_PRECISION = 18
MONEY_SCALE = 2
SUPPORTED_MINOR_UNITS = MONEY_SCALE

RATE_PRECISION = 7
RATE_SCALE = 4


def Money() -> Numeric:  # noqa: N802 - reads like a type in column definitions
    return Numeric(MONEY_PRECISION, MONEY_SCALE, asdecimal=True)


def RatePercent() -> Numeric:  # noqa: N802
    return Numeric(RATE_PRECISION, RATE_SCALE, asdecimal=True)


def CurrencyCode() -> CHAR:  # noqa: N802
    return CHAR(3)
