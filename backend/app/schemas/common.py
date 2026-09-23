from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from pydantic import Field

from app.services.finance.money import MAX_AMOUNT, MoneyDecimal, PercentDecimal

# Входные денежные значения: Decimal, максимум 2 знака, в пределах Numeric(14,2).
PositiveMoney = Annotated[Decimal, Field(gt=0, le=MAX_AMOUNT, decimal_places=2)]
NonNegativeMoney = Annotated[Decimal, Field(ge=0, le=MAX_AMOUNT, decimal_places=2)]
RatePercent = Annotated[Decimal, Field(ge=0, le=1000, decimal_places=4)]

__all__ = [
    "MoneyDecimal",
    "PercentDecimal",
    "PositiveMoney",
    "NonNegativeMoney",
    "RatePercent",
]
