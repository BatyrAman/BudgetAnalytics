"""
Подушка безопасности.

Правило выбора целевого срока (детерминированное):
* 3 месяца обязательных расходов — стабильный доход и нет иждивенцев;
* 6 месяцев — есть иждивенцы или доход нестабильный;
* target_months можно передать явно (1..24).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal
from enum import StrEnum

from app.services.finance.money import ZERO, MoneyError, quantize_money, to_decimal


class IncomeStability(StrEnum):
    STABLE = "stable"
    VARIABLE = "variable"


@dataclass(frozen=True, slots=True)
class EmergencyFundResult:
    monthly_mandatory_expenses: Decimal
    target_months: int
    target_amount: Decimal
    current_savings: Decimal
    gap: Decimal
    coverage_months: Decimal
    monthly_contribution: Decimal
    months_to_goal: int | None
    is_reached: bool


def recommended_months(dependents: int, stability: IncomeStability) -> int:
    if dependents > 0 or stability is IncomeStability.VARIABLE:
        return 6
    return 3


def calculate_emergency_fund(
    monthly_mandatory_expenses,
    current_savings=ZERO,
    monthly_contribution=ZERO,
    *,
    target_months: int | None = None,
    dependents: int = 0,
    income_stability: IncomeStability = IncomeStability.STABLE,
) -> EmergencyFundResult:
    expenses = quantize_money(monthly_mandatory_expenses)
    savings = quantize_money(current_savings)
    contribution = quantize_money(monthly_contribution)

    if expenses < 0 or savings < 0 or contribution < 0:
        raise MoneyError("Amounts cannot be negative")
    if dependents < 0:
        raise MoneyError("Dependents cannot be negative")

    months = target_months or recommended_months(dependents, IncomeStability(income_stability))
    if not 1 <= months <= 24:
        raise MoneyError("target_months must be 1..24")

    target = expenses * months
    gap = max(target - savings, ZERO)

    if gap == 0:
        months_to_goal: int | None = 0
    elif contribution > 0:
        months_to_goal = int((gap / contribution).to_integral_value(rounding=ROUND_CEILING))
    else:
        months_to_goal = None

    coverage = (
        (savings / expenses).quantize(Decimal("0.1")) if expenses > 0 else Decimal("0.0")
    )

    return EmergencyFundResult(
        monthly_mandatory_expenses=expenses,
        target_months=months,
        target_amount=target,
        current_savings=savings,
        gap=gap,
        coverage_months=coverage,
        monthly_contribution=contribution,
        months_to_goal=months_to_goal,
        is_reached=gap == 0,
    )
