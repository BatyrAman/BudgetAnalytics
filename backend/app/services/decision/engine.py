"""
FinancialDecisionEngine — детерминированный слой правил.

    FinancialSnapshot (числа)
        ↓
    risk detection
        ↓
    financial facts
        ↓
    warnings / recommendations / opportunities + score

Правила перенесены из services/ai/advisor.py без изменения порогов
и текстов (API /analytics/health и /recommendations отвечают как
раньше) и дополнены правилами долговой нагрузки. Каждая находка
имеет машинный code и факты — будущий AI Coach объясняет их, но
не вычисляет и не придумывает.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any

from app.services.finance.affordability import AffordabilityPolicy
from app.services.finance.money import ZERO


class FindingKind(StrEnum):
    WARNING = "warning"
    RECOMMENDATION = "recommendation"
    OPPORTUNITY = "opportunity"


class ForecastRisk(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


def forecast_risk(predicted_balance: Decimal) -> ForecastRisk:
    """Риск следующего месяца по прогнозному остатку (пороги v0.1)."""

    if predicted_balance >= 100_000:
        return ForecastRisk.LOW
    if predicted_balance >= 30_000:
        return ForecastRisk.MEDIUM
    if predicted_balance >= 0:
        return ForecastRisk.HIGH
    return ForecastRisk.CRITICAL


def saving_status(rate: Decimal) -> str:
    if rate >= 40:
        return "excellent"
    if rate >= 20:
        return "good"
    if rate >= 10:
        return "average"
    if rate >= 0:
        return "poor"
    return "critical"


@dataclass(frozen=True, slots=True)
class FinancialSnapshot:
    income: Decimal
    expense: Decimal
    balance: Decimal
    saving_rate: Decimal
    predicted_balance: Decimal
    # ежемесячные платежи по долгам / доход * 100; None — неизвестно
    debt_load: Decimal | None = None
    has_non_amortizing_debt: bool = False


@dataclass(frozen=True, slots=True)
class Finding:
    code: str
    kind: FindingKind
    message: str
    facts: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DecisionReport:
    score: int
    saving_status: str
    forecast_risk: ForecastRisk
    findings: tuple[Finding, ...]

    def messages(self, kind: FindingKind) -> list[str]:
        return [f.message for f in self.findings if f.kind is kind]


class FinancialDecisionEngine:
    def __init__(self, policy: AffordabilityPolicy | None = None) -> None:
        self.policy = policy or AffordabilityPolicy()

    def evaluate(self, s: FinancialSnapshot) -> DecisionReport:
        findings: list[Finding] = []

        def add(code: str, kind: FindingKind, message: str, **facts: Any) -> None:
            findings.append(Finding(code, kind, message, facts))

        W, R, O = FindingKind.WARNING, FindingKind.RECOMMENDATION, FindingKind.OPPORTUNITY

        if s.income == 0:
            add("NO_INCOME", W, "У вас пока отсутствуют доходы.")

        if s.expense > s.income:
            add("EXPENSES_EXCEED_INCOME", W, "Расходы превышают доходы.", income=s.income, expense=s.expense)
            add("CUT_DISCRETIONARY", R, "Необходимо сократить необязательные расходы.")

        if s.saving_rate >= 40:
            add("HIGH_SAVING_RATE", O, "Отличная финансовая дисциплина.", saving_rate=s.saving_rate)
            add("START_INVESTING", R, "Можно начать инвестировать свободные средства.")
        elif s.saving_rate >= 20:
            add("RAISE_SAVINGS", R, "Попробуйте увеличить накопления до 30–40%.", saving_rate=s.saving_rate)
        elif s.saving_rate >= 10:
            add("REDUCE_DAILY_SPENDING", R, "Стоит сократить ежедневные расходы.", saving_rate=s.saving_rate)
        else:
            add("LOW_SAVING_RATE", W, "Очень низкий процент накоплений.", saving_rate=s.saving_rate)
            add("BUILD_EMERGENCY_FUND", R, "Создайте резервный фонд минимум на 3 месяца.")

        if s.balance < 0:
            add("NEGATIVE_BALANCE", W, "Ваш баланс отрицательный.", balance=s.balance)
        elif s.balance > 300_000:
            add("FREE_CASH_AVAILABLE", O, "У вас достаточно свободных средств для инвестирования.", balance=s.balance)

        risk = forecast_risk(s.predicted_balance)
        if risk is ForecastRisk.CRITICAL:
            add("FORECAST_DEFICIT", W, "Высокий риск дефицита бюджета в следующем месяце.",
                predicted_balance=s.predicted_balance)
        elif risk is ForecastRisk.HIGH:
            add("FORECAST_TIGHT", R, "Следующий месяц может быть финансово напряженным.",
                predicted_balance=s.predicted_balance)
        elif risk is ForecastRisk.LOW:
            add("FORECAST_STABLE", O, "Финансовый прогноз выглядит стабильно.",
                predicted_balance=s.predicted_balance)

        # --- долговая нагрузка (новые правила) ---
        if s.debt_load is not None:
            ratio = s.debt_load / 100
            if ratio >= self.policy.critical_dti:
                add("DEBT_LOAD_CRITICAL", W,
                    "Платежи по долгам забирают половину дохода и больше — новые кредиты брать не стоит.",
                    debt_load=s.debt_load)
                add("DEBT_STRATEGY", R, "Составьте план погашения: начните с самых дорогих долгов.")
            elif ratio > self.policy.max_dti:
                add("DEBT_LOAD_HIGH", W, "Долговая нагрузка выше рекомендуемых 40% дохода.", debt_load=s.debt_load)
                add("DEBT_STRATEGY", R, "Составьте план погашения: начните с самых дорогих долгов.")
        if s.has_non_amortizing_debt:
            add("DEBT_NOT_AMORTIZING", W,
                "По одному из долгов платёж не покрывает проценты — долг растёт.")

        warnings = sum(1 for f in findings if f.kind is W)
        opportunities = sum(1 for f in findings if f.kind is O)
        score = max(0, min(100 - warnings * 15 + opportunities * 5, 100))

        return DecisionReport(
            score=score,
            saving_status=saving_status(s.saving_rate),
            forecast_risk=risk,
            findings=tuple(findings),
        )


__all__ = [
    "DecisionReport",
    "FinancialDecisionEngine",
    "FinancialSnapshot",
    "Finding",
    "FindingKind",
    "ForecastRisk",
    "forecast_risk",
    "saving_status",
    "ZERO",
]
