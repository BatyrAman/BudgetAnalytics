"""
AffordabilityService — «потяну ли я новый платёж?».

Полностью детерминирован: одинаковый вход → одинаковый результат.
Risk level определяет код, а не LLM.

Определения (всё в месяц):
    free_cash_flow        = доход - обязательные расходы - текущие платежи по долгам
    current_debt_load     = текущие платежи / доход * 100
    projected_debt_load   = (текущие платежи + новый платёж) / доход * 100
    recommended_max_payment = min(
        доход * max_dti - текущие платежи,          # лимит долговой нагрузки
        free_cash_flow - доход * min_buffer_ratio,  # остаётся «подушка» в месяц
    ), не меньше 0

Уровни риска по прогнозной долговой нагрузке (policy по умолчанию):
    <= 30% low · <= 40% moderate · < 50% high · >= 50% critical
    плюс: отрицательный остаток после платежа → critical,
          остаток меньше буфера → минимум high.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from app.services.finance.money import ZERO, MoneyError, percent, quantize_money, to_decimal


class RiskLevel(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


_RISK_ORDER = [RiskLevel.LOW, RiskLevel.MODERATE, RiskLevel.HIGH, RiskLevel.CRITICAL]


def _max_risk(a: RiskLevel, b: RiskLevel) -> RiskLevel:
    return a if _RISK_ORDER.index(a) >= _RISK_ORDER.index(b) else b


@dataclass(frozen=True, slots=True)
class AffordabilityPolicy:
    comfortable_dti: Decimal = Decimal("0.30")
    max_dti: Decimal = Decimal("0.40")
    critical_dti: Decimal = Decimal("0.50")
    # Минимальный ежемесячный остаток после всех платежей, доля дохода.
    min_buffer_ratio: Decimal = Decimal("0.10")


@dataclass(frozen=True, slots=True)
class AffordabilityInput:
    monthly_income: Decimal
    mandatory_expenses: Decimal
    existing_debt_payments: Decimal
    new_payment: Decimal = ZERO


@dataclass(frozen=True, slots=True)
class Reason:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class AffordabilityResult:
    affordable: bool
    risk_level: RiskLevel
    monthly_income: Decimal
    mandatory_expenses: Decimal
    existing_debt_payments: Decimal
    new_payment: Decimal
    # В процентах; None, если дохода нет (нагрузку нельзя посчитать).
    current_debt_load: Decimal | None
    projected_debt_load: Decimal | None
    free_cash_flow: Decimal
    free_cash_flow_after: Decimal
    recommended_max_payment: Decimal
    reasons: tuple[Reason, ...] = field(default_factory=tuple)


class AffordabilityService:
    def __init__(self, policy: AffordabilityPolicy | None = None) -> None:
        self.policy = policy or AffordabilityPolicy()

    def assess(self, data: AffordabilityInput) -> AffordabilityResult:
        income = quantize_money(data.monthly_income)
        mandatory = quantize_money(data.mandatory_expenses)
        existing = quantize_money(data.existing_debt_payments)
        new_payment = quantize_money(data.new_payment)
        policy = self.policy

        for name, value in (
            ("monthly_income", income),
            ("mandatory_expenses", mandatory),
            ("existing_debt_payments", existing),
            ("new_payment", new_payment),
        ):
            if value < 0:
                raise MoneyError(f"{name} cannot be negative")

        free_cash_flow = income - mandatory - existing
        free_after = free_cash_flow - new_payment
        buffer = quantize_money(income * to_decimal(policy.min_buffer_ratio))
        reasons: list[Reason] = []

        if income == 0:
            reasons.append(Reason("NO_INCOME", "Нет подтверждённого дохода — новый платёж не по силам."))
            return AffordabilityResult(
                affordable=new_payment == 0 and free_after >= 0,
                risk_level=RiskLevel.CRITICAL,
                monthly_income=income,
                mandatory_expenses=mandatory,
                existing_debt_payments=existing,
                new_payment=new_payment,
                current_debt_load=None,
                projected_debt_load=None,
                free_cash_flow=free_cash_flow,
                free_cash_flow_after=free_after,
                recommended_max_payment=ZERO,
                reasons=tuple(reasons),
            )

        current_load = percent(existing, income)
        projected_load = percent(existing + new_payment, income)
        projected_ratio = (existing + new_payment) / income

        by_dti = quantize_money(income * to_decimal(policy.max_dti)) - existing
        by_cash = free_cash_flow - buffer
        recommended = max(min(by_dti, by_cash), ZERO)

        if projected_ratio <= policy.comfortable_dti:
            risk = RiskLevel.LOW
        elif projected_ratio <= policy.max_dti:
            risk = RiskLevel.MODERATE
            reasons.append(Reason("DTI_ELEVATED", "Долговая нагрузка выше комфортного уровня 30%."))
        elif projected_ratio < policy.critical_dti:
            risk = RiskLevel.HIGH
            reasons.append(Reason("DTI_ABOVE_LIMIT", "Долговая нагрузка превышает рекомендуемый максимум 40%."))
        else:
            risk = RiskLevel.CRITICAL
            reasons.append(Reason("DTI_CRITICAL", "Долговая нагрузка 50% дохода и выше."))

        if free_cash_flow < 0:
            risk = RiskLevel.CRITICAL
            reasons.append(Reason("NEGATIVE_CASH_FLOW", "Уже сейчас расходы и платежи превышают доход."))
        elif free_after < 0:
            risk = RiskLevel.CRITICAL
            reasons.append(Reason("PAYMENT_EXCEEDS_FREE_CASH", "Новый платёж больше свободного остатка."))
        elif free_after < buffer:
            risk = _max_risk(risk, RiskLevel.HIGH)
            reasons.append(Reason("LOW_BUFFER", "После платежа остаётся меньше 10% дохода на непредвиденное."))

        affordable = new_payment <= recommended and risk in (RiskLevel.LOW, RiskLevel.MODERATE)
        if affordable and not reasons:
            reasons.append(Reason("WITHIN_LIMITS", "Платёж укладывается в лимиты нагрузки и остатка."))

        return AffordabilityResult(
            affordable=affordable,
            risk_level=risk,
            monthly_income=income,
            mandatory_expenses=mandatory,
            existing_debt_payments=existing,
            new_payment=new_payment,
            current_debt_load=current_load,
            projected_debt_load=projected_load,
            free_cash_flow=free_cash_flow,
            free_cash_flow_after=free_after,
            recommended_max_payment=recommended,
            reasons=tuple(reasons),
        )
