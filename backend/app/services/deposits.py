"""Adapter between the ``Deposit`` model and the finance engine.

All deposit math lives in ``app.services.finance.deposit``; this module only
maps a stored deposit to engine inputs, so the API endpoints (investments,
dashboard) share one implementation.

Stored currencies always have 2 minor units (see ``app.models.types``).
"""

from decimal import Decimal

from app.models.deposit import Deposit
from app.models.types import SUPPORTED_MINOR_UNITS
from app.services.finance import CurrencySpec, DepositMaturity, deposit_maturity


def maturity_of(deposit: Deposit) -> DepositMaturity:
    return deposit_maturity(
        principal=deposit.amount,
        annual_rate_percent=deposit.interest_rate,
        start_date=deposit.start_date,
        end_date=deposit.end_date,
        capitalization=deposit.capitalization,
        currency=CurrencySpec(deposit.currency_code, SUPPORTED_MINOR_UNITS),
    )


def expected_profit(deposit: Deposit) -> Decimal:
    return maturity_of(deposit).interest
