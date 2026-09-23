from datetime import date, timedelta
from decimal import Decimal

import pytest

pytestmark = pytest.mark.integration

D = Decimal


def debt_body(**overrides):
    body = {
        "name": "Kaspi кредит",
        "debt_type": "consumer_loan",
        "principal": "1000000",
        "annual_rate": "24",
        "payment_day": 10,
        "start_date": "2025-01-10",
        "term_months": 24,
    }
    body.update(overrides)
    return body


async def test_create_computes_annuity_payment(alice):
    response = await alice.post("/debts", json=debt_body(start_date=date.today().isoformat(), term_months=24))
    assert response.status_code == 201, response.text
    debt = response.json()
    # аннуитет 1 000 000 под 24% на 24 платежа = 52 871.10
    assert debt["monthly_payment"] == "52871.10"
    assert debt["balance"] == "1000000.00"
    assert debt["is_amortizing"] is True
    assert debt["projected_months_left"] == 24
    assert D(debt["projected_total_overpayment"]) > 0
    assert debt["paid_percent"] == "0.00"


async def test_revolving_requires_payment(alice):
    response = await alice.post(
        "/debts",
        json=debt_body(debt_type="credit_card", schedule_type="revolving", term_months=None),
    )
    assert response.status_code == 422


async def test_non_amortizing_debt_is_flagged(alice):
    response = await alice.post(
        "/debts",
        json=debt_body(
            debt_type="microloan",
            principal="500000",
            annual_rate="120",
            monthly_payment="10000",  # проценты 50 000 в месяц
            term_months=None,
        ),
    )
    debt = response.json()
    assert debt["is_amortizing"] is False
    assert debt["projected_payoff_date"] is None

    summary = (await alice.get("/debts/summary")).json()
    assert summary["payments_cover_interest"] is False
    assert summary["debt_free_date"] is None


async def test_summary_and_debt_load(alice):
    await alice.post("/debts", json=debt_body(monthly_payment="100000", term_months=None, principal="1200000"))
    await alice.post(
        "/debts",
        json=debt_body(name="Карта", debt_type="credit_card", schedule_type="revolving",
                       principal="200000", annual_rate="30", monthly_payment="20000", term_months=None),
    )
    profile = await alice.put("/auth/me/profile", json={"monthly_income_declared": "400000"})
    assert profile.status_code == 200, profile.text

    summary = (await alice.get("/debts/summary")).json()
    assert summary["active_debts"] == 2
    assert summary["total_balance"] == "1400000.00"
    assert summary["total_monthly_payment"] == "120000.00"
    assert summary["income_source"] == "declared"
    assert summary["debt_load"] == "30.00"
    assert summary["debt_load_level"] == "low"
    assert summary["debt_free_date"] is not None
    assert {t["debt_type"] for t in summary["by_type"]} == {"consumer_loan", "credit_card"}


async def test_calendar(alice):
    today = date.today()
    await alice.post("/debts", json=debt_body(payment_day=today.day, monthly_payment="50000", term_months=None))
    items = (await alice.get("/debts/calendar", params={"days": 70})).json()
    assert len(items) >= 2
    assert items[0]["days_left"] == 0
    assert all(item["amount"] == "50000.00" for item in items)
    assert items == sorted(items, key=lambda i: i["due_date"])


async def test_strategy_simulation(alice):
    await alice.post(
        "/debts",
        json=debt_body(name="Карта", debt_type="credit_card", schedule_type="revolving",
                       principal="300000", annual_rate="36", monthly_payment="15000", term_months=None),
    )
    await alice.post("/debts", json=debt_body(name="Кредит", principal="600000", annual_rate="18",
                                              monthly_payment="30000", term_months=None))
    response = await alice.post("/debts/strategy", json={"extra_payment": "50000", "strategy": "snowball"})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["feasible"] is True
    assert result["monthly_budget"] == "95000.00"
    assert result["recommended_strategy"] == "avalanche"
    assert len(result["timeline"]) == result["months"]
    assert result["timeline"][-1]["total_balance"] == "0.00"
    by_strategy = {c["strategy"]: c for c in result["comparison"]}
    assert D(by_strategy["snowball"]["extra_cost_vs_recommended"]) >= 0
    assert D(by_strategy["avalanche"]["interest_saved_vs_minimum"]) > 0
    assert result["minimum_payments_only"]["months"] > result["months"]


async def test_strategy_without_debts(alice):
    response = await alice.post("/debts/strategy", json={"extra_payment": "0"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "NO_ACTIVE_DEBTS"


async def test_prepayment_modes(alice):
    debt = (await alice.post("/debts", json=debt_body(monthly_payment="52874.64", term_months=None))).json()
    term = (await alice.post(f"/debts/{debt['id']}/prepayment", json={"amount": "200000", "mode": "term"})).json()
    pay = (await alice.post(f"/debts/{debt['id']}/prepayment", json={"amount": "200000", "mode": "payment"})).json()
    assert term["months_saved"] > 0
    assert term["payment_after"] == term["payment_before"]
    assert pay["months_saved"] == 0
    assert D(pay["payment_reduced_by"]) > 0
    assert D(term["interest_saved"]) > D(pay["interest_saved"]) > 0

    full = (await alice.post(f"/debts/{debt['id']}/prepayment", json={"amount": "5000000"})).json()
    assert full["fully_repaid"] is True
    assert full["balance_after"] == "0.00"


async def test_record_payment_splits_interest_and_closes_debt(alice):
    debt = (await alice.post("/debts", json=debt_body(principal="100000", annual_rate="12",
                                                     monthly_payment="50000", term_months=None))).json()
    first = await alice.post(f"/debts/{debt['id']}/payments", json={"amount": "50000"})
    assert first.status_code == 201, first.text
    assert first.json()["interest_part"] == "1000.00"
    assert first.json()["principal_part"] == "49000.00"
    assert (await alice.get(f"/debts/{debt['id']}")).json()["balance"] == "51000.00"

    too_much = await alice.post(f"/debts/{debt['id']}/payments", json={"amount": "60000"})
    assert too_much.json()["error"]["code"] == "PAYMENT_EXCEEDS_BALANCE"

    await alice.post(f"/debts/{debt['id']}/payments", json={"amount": "51510"})
    closed = (await alice.get(f"/debts/{debt['id']}")).json()
    assert closed["balance"] == "0.00"
    assert closed["is_active"] is False
    assert closed["paid_percent"] == "100.00"
    assert closed["interest_paid"] == "1510.00"

    payments = (await alice.get(f"/debts/{debt['id']}/payments")).json()
    await alice.delete(f"/debts/{debt['id']}/payments/{payments[0]['id']}")
    reopened = (await alice.get(f"/debts/{debt['id']}")).json()
    assert reopened["is_active"] is True
    assert reopened["balance"] == "51000.00"


async def test_payment_linked_transaction_must_be_own_expense(alice, bob, session, kaspi_id):
    from tests.integration.conftest import system_category

    loans = await system_category(session, "Погашение кредитов")
    tx_bob = (await bob.post("/transactions", json={
        "amount": "1000", "transaction_type": "expense", "transaction_date": "2025-01-01T10:00:00",
        "category_id": loans, "bank_id": kaspi_id})).json()
    debt = (await alice.post("/debts", json=debt_body(monthly_payment="50000", term_months=None))).json()
    response = await alice.post(f"/debts/{debt['id']}/payments", json={"amount": "1000", "transaction_id": tx_bob["id"]})
    assert response.json()["error"]["code"] == "TRANSACTION_NOT_FOUND"

    tx = (await alice.post("/transactions", json={
        "amount": "1000", "transaction_type": "expense", "transaction_date": "2025-01-01T10:00:00",
        "category_id": loans, "bank_id": kaspi_id})).json()
    assert (await alice.post(f"/debts/{debt['id']}/payments", json={"amount": "1000", "transaction_id": tx["id"]})).status_code == 201
    again = await alice.post(f"/debts/{debt['id']}/payments", json={"amount": "1000", "transaction_id": tx["id"]})
    assert again.status_code == 409
