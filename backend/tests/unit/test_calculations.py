"""Legacy API adapters now delegate to app.services.finance.

These pin what the existing endpoints return. The only intentional change from
the previous inline formulas: exact half-minor-unit results now round HALF_UP
(the central policy) instead of HALF_EVEN — e.g. 0.005 -> 0.01, not 0.00.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.models.deposit import Deposit
from app.models.enums import Capitalization
from app.services.budgets import budget_progress_percent
from app.services.deposits import expected_profit, maturity_of


def make_deposit(
    amount: str,
    rate: str,
    start: date,
    end: date,
    capitalization: Capitalization = Capitalization.NONE,
) -> Deposit:
    return Deposit(
        amount=Decimal(amount),
        interest_rate=Decimal(rate),
        start_date=start,
        end_date=end,
        capitalization=capitalization,
        currency_code="KZT",
    )


class TestDepositAdapter:
    def test_one_year_simple_interest(self) -> None:
        deposit = make_deposit("1000000.00", "14.00", date(2025, 1, 1), date(2026, 1, 1))
        assert expected_profit(deposit) == Decimal("140000.00")
        assert maturity_of(deposit).term_days == 365

    def test_rounds_to_tiyn(self) -> None:
        deposit = make_deposit("100000.00", "10.00", date(2025, 1, 1), date(2025, 1, 31))
        assert expected_profit(deposit) == Decimal("821.92")

    def test_exact_half_tiyn_now_rounds_up(self) -> None:
        # 365 · 0.5 % · 1 / 365 = 0.005 -> 0.01 (was 0.00 with HALF_EVEN).
        deposit = make_deposit("365.00", "0.50", date(2025, 1, 1), date(2025, 1, 2))
        assert expected_profit(deposit) == Decimal("0.01")

    def test_capitalization_is_honored(self) -> None:
        deposit = make_deposit(
            "1000000", "16", date(2025, 1, 1), date(2026, 1, 1), Capitalization.MONTHLY
        )
        assert expected_profit(deposit) == Decimal("172270.80")


class TestBudgetProgressAdapter:
    @pytest.mark.parametrize(
        ("spent", "limit", "expected"),
        [
            (Decimal("0"), Decimal("100000"), 0.0),
            (Decimal("50000"), Decimal("100000"), 50.0),
            (Decimal("1"), Decimal("3"), 33.33),
            (Decimal("150000"), Decimal("100000"), 150.0),
            (Decimal("10"), Decimal("0"), 0.0),  # legacy contract: 0 for a non-positive limit
            (Decimal("10"), Decimal("-5"), 0.0),
        ],
    )
    def test_progress_percent(self, spent: Decimal, limit: Decimal, expected: float) -> None:
        assert budget_progress_percent(spent, limit) == expected
