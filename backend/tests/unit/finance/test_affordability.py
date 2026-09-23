from decimal import Decimal

import pytest

from app.services.finance.affordability import (
    AffordabilityInput,
    AffordabilityService,
    RiskLevel,
)
from app.services.finance.money import MoneyError

D = Decimal
service = AffordabilityService()


def assess(income, mandatory, existing, new):
    return service.assess(AffordabilityInput(D(income), D(mandatory), D(existing), D(new)))


def codes(result):
    return {r.code for r in result.reasons}


def test_comfortable_payment():
    result = assess(500_000, 200_000, 50_000, 50_000)
    assert result.affordable
    assert result.risk_level is RiskLevel.LOW
    assert result.current_debt_load == D("10.00")
    assert result.projected_debt_load == D("20.00")
    assert result.free_cash_flow == D("250000.00")
    assert result.free_cash_flow_after == D("200000.00")
    # min(500k*0.4 - 50k = 150k, 250k - 50k buffer = 200k)
    assert result.recommended_max_payment == D("150000.00")


def test_example_from_spec():
    result = assess(420_000, 315_000, 145_000, 30_000)
    assert not result.affordable
    assert result.risk_level is RiskLevel.CRITICAL
    assert result.free_cash_flow == D("-40000.00")
    assert result.recommended_max_payment == D("0.00")
    assert "NEGATIVE_CASH_FLOW" in codes(result)


def test_recommended_max_is_itself_affordable():
    base = assess(600_000, 250_000, 100_000, 0)
    at_limit = assess(600_000, 250_000, 100_000, base.recommended_max_payment)
    assert at_limit.affordable
    above = assess(600_000, 250_000, 100_000, base.recommended_max_payment + D("0.01"))
    assert not above.affordable


@pytest.mark.parametrize(
    "new, expected",
    [
        (100_000, RiskLevel.LOW),       # 20%
        (150_000, RiskLevel.LOW),       # 30% (граница включительно)
        (200_000, RiskLevel.MODERATE),  # 40% (граница включительно)
        (225_000, RiskLevel.HIGH),      # 45%
        (250_000, RiskLevel.CRITICAL),  # 50%
    ],
)
def test_risk_thresholds(new, expected):
    # доход 500k, иных платежей нет, обязательные расходы 0 → dti = new/500k
    result = assess(500_000, 0, 0, new)
    assert result.risk_level is expected


def test_zero_income():
    result = assess(0, 0, 0, 10_000)
    assert not result.affordable
    assert result.risk_level is RiskLevel.CRITICAL
    assert result.current_debt_load is None
    assert result.recommended_max_payment == 0
    assert codes(result) == {"NO_INCOME"}


def test_low_buffer_raises_risk():
    # dti 20% (ok), но после платежа остаётся 5% дохода
    result = assess(100_000, 75_000, 0, 20_000)
    assert result.risk_level is RiskLevel.HIGH
    assert "LOW_BUFFER" in codes(result)
    assert not result.affordable


def test_payment_bigger_than_free_cash():
    result = assess(100_000, 90_000, 0, 20_000)
    assert result.risk_level is RiskLevel.CRITICAL
    assert "PAYMENT_EXCEEDS_FREE_CASH" in codes(result)


def test_negative_input_rejected():
    with pytest.raises(MoneyError):
        assess(100_000, -1, 0, 0)


def test_deterministic():
    a = assess(333_333, 111_111, 22_222, 44_444)
    b = assess(333_333, 111_111, 22_222, 44_444)
    assert a == b
