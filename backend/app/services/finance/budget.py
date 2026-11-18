"""Budget utilization.

    effective_spent     = max(spent, 0)
    remaining           = limit − effective_spent        (negative = overspent)
    utilization_percent = effective_spent / limit × 100   rounded to 0.01 %
    is_exceeded         = effective_spent > limit         (exactly at the limit
                                                           is NOT exceeded)

``spent`` is the NET expense of the budget's scope for the period (expenses
minus refunds); if refunds exceed expenses it is negative and counts as 0
spent. ``limit`` must be > 0 — a zero limit makes utilization undefined.
Money is rounded to the currency's minor units (ROUND_HALF_UP).
"""

from dataclasses import dataclass
from decimal import Decimal

from app.services.finance.money import (
    HUNDRED,
    ZERO,
    CurrencySpec,
    calc_context,
    quantize_money,
    quantize_ratio_percent,
    require_positive,
    to_decimal,
)


@dataclass(frozen=True)
class BudgetUtilization:
    currency_code: str
    limit: Decimal
    spent: Decimal
    remaining: Decimal
    utilization_percent: Decimal
    is_exceeded: bool


def budget_utilization(limit: Decimal, spent: Decimal, currency: CurrencySpec) -> BudgetUtilization:
    limit = require_positive(limit, "limit")
    effective_spent = max(to_decimal(spent, "spent"), ZERO)

    with calc_context():
        remaining = limit - effective_spent
        utilization = effective_spent / limit * HUNDRED

    return BudgetUtilization(
        currency_code=currency.code,
        limit=quantize_money(limit, currency),
        spent=quantize_money(effective_spent, currency),
        remaining=quantize_money(remaining, currency),
        utilization_percent=quantize_ratio_percent(utilization),
        is_exceeded=effective_spent > limit,
    )
