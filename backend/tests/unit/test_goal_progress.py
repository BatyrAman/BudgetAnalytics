"""Goal progress (app.services.goals.goal_progress) with a fixed "today".
Expected values are computed by hand."""

from datetime import date
from decimal import Decimal

import pytest

from app.models.goal import FinancialGoal
from app.services.goals import goal_progress

TODAY = date(2025, 1, 31)


def _goal(target: str, saved: str, target_date: date | None) -> FinancialGoal:
    return FinancialGoal(
        name="g",
        target_amount=Decimal(target),
        saved_amount=Decimal(saved),
        currency_code="KZT",
        target_date=target_date,
    )


@pytest.mark.parametrize(
    ("target", "saved", "target_date", "expected"),
    [
        # 100/300 = 33.333…% → 33.33; Jan→Apr = 3 months; 200/3 = 66.666… → 66.67
        ("300.00", "100.00", date(2025, 4, 1), ("33.33", "200.00", False, 3, "66.67")),
        # Calendar months: Jan 31 → Feb 1 is one month.
        ("100.00", "0", date(2025, 2, 1), ("0.00", "100.00", False, 1, "100.00")),
        # Same month or past: no month count, no monthly requirement.
        ("100.00", "0", date(2025, 1, 31), ("0.00", "100.00", False, None, None)),
        ("100.00", "0", date(2024, 12, 1), ("0.00", "100.00", False, None, None)),
        # Reached exactly / over-saved.
        ("100.00", "100.00", date(2026, 1, 1), ("100.00", "0.00", True, 12, None)),
        ("100.00", "250.50", None, ("250.50", "0.00", True, None, None)),
        # Smallest amounts; 0.01 over 2 months = 0.005 → 0.01 (ROUND_HALF_UP)
        ("0.02", "0.01", date(2025, 3, 15), ("50.00", "0.01", False, 2, "0.01")),
        # Leap-day target: Jan 2025 → Feb 2028 = 37 months; 1000/37 = 27.027… → 27.03
        ("1000.00", "0", date(2028, 2, 29), ("0.00", "1000.00", False, 37, "27.03")),
    ],
)
def test_goal_progress(
    target: str,
    saved: str,
    target_date: date | None,
    expected: tuple[str, str, bool, int | None, str | None],
) -> None:
    p = goal_progress(_goal(target, saved, target_date), TODAY)
    progress, remaining, reached, months, monthly = expected
    assert p.progress_percent == Decimal(progress)
    assert str(p.remaining) == remaining
    assert p.is_reached is reached
    assert p.months_left == months
    assert (
        None if p.required_monthly_saving is None else str(p.required_monthly_saving)
    ) == monthly
