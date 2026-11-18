from decimal import Decimal

import pytest

from app.services.finance import KZT, FinanceInputError, budget_utilization


@pytest.mark.parametrize(
    ("limit", "spent", "percent", "remaining", "exceeded"),
    [
        ("100000.00", "0", "0.00", "100000.00", False),
        ("100000.00", "50000.00", "50.00", "50000.00", False),
        ("100000.00", "33333.33", "33.33", "66666.67", False),
        ("100000.00", "100000.00", "100.00", "0.00", False),  # exactly at the limit
        ("100000.00", "100000.01", "100.00", "-0.01", True),  # 100.00001 % -> 100.00, but over
        ("100000.00", "150000.00", "150.00", "-50000.00", True),
        ("400.00", "0.02", "0.01", "399.98", False),  # 0.005 % -> HALF_UP 0.01 (not 0.00)
        ("0.01", "0.01", "100.00", "0.00", False),  # smallest amounts
    ],
)
def test_utilization(limit: str, spent: str, percent: str, remaining: str, exceeded: bool) -> None:
    result = budget_utilization(Decimal(limit), Decimal(spent), KZT)
    assert result.utilization_percent == Decimal(percent)
    assert result.remaining == Decimal(remaining)
    assert result.is_exceeded is exceeded


def test_negative_net_spending_counts_as_zero() -> None:
    result = budget_utilization(Decimal("1000"), Decimal("-250"), KZT)
    assert result.spent == Decimal("0.00")
    assert result.utilization_percent == Decimal("0.00")
    assert result.remaining == Decimal("1000.00")


@pytest.mark.parametrize("limit", ["0", "-100"])
def test_non_positive_limit_is_rejected(limit: str) -> None:
    with pytest.raises(FinanceInputError, match="limit"):
        budget_utilization(Decimal(limit), Decimal("10"), KZT)
