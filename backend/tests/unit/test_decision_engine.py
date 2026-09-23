from decimal import Decimal

from app.services.decision.engine import (
    FinancialDecisionEngine,
    FinancialSnapshot,
    FindingKind,
    ForecastRisk,
    forecast_risk,
)

D = Decimal
engine = FinancialDecisionEngine()


def snap(**kw):
    base = dict(
        income=D("500000"),
        expense=D("250000"),
        balance=D("250000"),
        saving_rate=D("50"),
        predicted_balance=D("150000"),
    )
    base.update(kw)
    return FinancialSnapshot(**base)


def codes(report):
    return {f.code for f in report.findings}


def test_healthy_profile_matches_legacy_score():
    report = engine.evaluate(snap())
    # 2 возможности (дисциплина, стабильный прогноз), 0 предупреждений → 100
    assert report.score == 100
    assert report.saving_status == "excellent"
    assert report.forecast_risk is ForecastRisk.LOW
    assert report.messages(FindingKind.OPPORTUNITY) == [
        "Отличная финансовая дисциплина.",
        "Финансовый прогноз выглядит стабильно.",
    ]


def test_critical_profile():
    report = engine.evaluate(
        snap(income=D("0"), expense=D("100000"), balance=D("-100000"), saving_rate=D("0"), predicted_balance=D("-5"))
    )
    assert {"NO_INCOME", "EXPENSES_EXCEED_INCOME", "LOW_SAVING_RATE", "NEGATIVE_BALANCE", "FORECAST_DEFICIT"} <= codes(report)
    assert report.score == 25  # 100 - 5*15
    assert report.saving_status == "poor"


def test_debt_load_rules():
    assert "DEBT_LOAD_HIGH" in codes(engine.evaluate(snap(debt_load=D("45"))))
    assert "DEBT_LOAD_CRITICAL" in codes(engine.evaluate(snap(debt_load=D("50"))))
    assert not {"DEBT_LOAD_HIGH", "DEBT_LOAD_CRITICAL"} & codes(engine.evaluate(snap(debt_load=D("40"))))
    assert "DEBT_NOT_AMORTIZING" in codes(engine.evaluate(snap(has_non_amortizing_debt=True)))


def test_findings_carry_facts():
    report = engine.evaluate(snap(debt_load=D("55")))
    finding = next(f for f in report.findings if f.code == "DEBT_LOAD_CRITICAL")
    assert finding.facts == {"debt_load": D("55")}


def test_forecast_risk_thresholds():
    assert forecast_risk(D("100000")) is ForecastRisk.LOW
    assert forecast_risk(D("30000")) is ForecastRisk.MEDIUM
    assert forecast_risk(D("0")) is ForecastRisk.HIGH
    assert forecast_risk(D("-0.01")) is ForecastRisk.CRITICAL


def test_deterministic():
    assert engine.evaluate(snap(debt_load=D("33.33"))) == engine.evaluate(snap(debt_load=D("33.33")))
