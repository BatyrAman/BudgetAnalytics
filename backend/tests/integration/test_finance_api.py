from decimal import Decimal

import pytest

pytestmark = pytest.mark.integration


async def test_loan_calculator(alice):
    response = await alice.post(
        "/finance/loan",
        json={"amount": "1000000", "annual_rate": "12", "term_months": 12, "upfront_fees": "20000",
              "include_schedule": True},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["monthly_payment"] == "88848.79"
    assert data["total_interest"] == "66185.45"
    assert data["overpayment"] == "86185.45"
    assert Decimal(data["effective_annual_rate"]) > Decimal("12.68")
    assert len(data["schedule"]) == 12
    assert data["schedule"][-1]["balance_after"] == "0.00"


async def test_loan_calculator_validation(alice):
    assert (await alice.post("/finance/loan", json={"amount": "0", "annual_rate": "10", "term_months": 12})).status_code == 422
    assert (await alice.post("/finance/loan", json={"amount": "100", "annual_rate": "10", "term_months": 0})).status_code == 422
    # float-подобные значения с лишними знаками отклоняются
    assert (await alice.post("/finance/loan", json={"amount": "100.001", "annual_rate": "10", "term_months": 1})).status_code == 422


async def test_mortgage_accounts_for_existing_debts(alice):
    body = {"price": "30000000", "down_payment": "6000000", "annual_rate": "18", "term_years": 20}
    base = (await alice.post("/finance/mortgage", json=body)).json()
    await alice.post("/debts", json={"name": "Кредит", "debt_type": "consumer_loan", "principal": "500000",
                                     "annual_rate": "20", "monthly_payment": "100000", "payment_day": 1,
                                     "start_date": "2025-01-01"})
    loaded = (await alice.post("/finance/mortgage", json=body)).json()
    assert loaded["existing_debt_payments"] == "100000.00"
    # Decimal, не float: 1175986.93 - 925986.93 во float != 250000.0
    assert Decimal(loaded["required_monthly_income"]) - Decimal(base["required_monthly_income"]) == Decimal("250000.00")
    bad = await alice.post("/finance/mortgage", json={**body, "down_payment": "30000000"})
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "INVALID_CALCULATION_INPUT"


async def test_deposit_calculator(alice):
    data = (await alice.post("/finance/deposit", json={"amount": "1000000", "annual_rate": "12", "term_months": 12})).json()
    assert data["final_amount"] == "1126825.02"
    assert data["effective_annual_rate"] == "12.68"


async def test_affordability_uses_profile_and_overrides(alice):
    await alice.put("/auth/me/profile", json={"monthly_income_declared": "420000"})
    await alice.post("/debts", json={"name": "Кредит", "debt_type": "consumer_loan", "principal": "2000000",
                                     "annual_rate": "20", "monthly_payment": "145000", "payment_day": 1,
                                     "start_date": "2025-01-01"})
    result = (await alice.post(
        "/finance/affordability", json={"new_payment": "30000", "mandatory_expenses": "315000"}
    )).json()
    assert result["affordable"] is False
    assert result["risk_level"] == "critical"
    assert result["monthly_income"] == "420000.00"
    assert result["existing_debt_payments"] == "145000.00"
    assert result["current_debt_load"] == "34.52"
    assert result["free_cash_flow"] == "-40000.00"
    assert result["recommended_max_payment"] == "0.00"
    assert result["sources"] == {
        "monthly_income": "declared",
        "mandatory_expenses": "request",
        "existing_debt_payments": "debts",
        "new_payment": "request",
    }
    assert "NEGATIVE_CASH_FLOW" in {r["code"] for r in result["reasons"]}


async def test_affordability_with_loan_params(alice):
    result = (await alice.post("/finance/affordability", json={
        "monthly_income": "800000", "mandatory_expenses": "200000", "existing_debt_payments": "0",
        "loan": {"amount": "2000000", "annual_rate": "20", "term_months": 24},
    })).json()
    assert result["sources"]["new_payment"] == "loan"
    assert result["affordable"] is True
    assert result["risk_level"] == "low"


async def test_affordability_requires_exactly_one_payment_source(alice):
    both = await alice.post("/finance/affordability", json={
        "new_payment": "1", "loan": {"amount": "1", "annual_rate": "1", "term_months": 1}})
    none = await alice.post("/finance/affordability", json={})
    assert both.status_code == none.status_code == 422


async def test_emergency_fund_and_profile(alice):
    await alice.put("/auth/me/profile", json={"dependents": 2})
    fund = (await alice.post("/finance/emergency-fund", json={
        "monthly_mandatory_expenses": "200000", "current_savings": "300000", "monthly_contribution": "100000"})).json()
    assert fund["target_months"] == 6
    assert fund["target_amount"] == "1200000.00"
    assert fund["months_to_goal"] == 9

    profile = (await alice.get("/finance/profile")).json()
    assert profile["dependents"] == 2
    assert profile["income_source"] == "none"
    assert "email" not in profile and "full_name" not in profile
