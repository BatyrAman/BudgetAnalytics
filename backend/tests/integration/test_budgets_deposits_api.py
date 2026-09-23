from datetime import date

import pytest

from tests.integration.conftest import system_category

pytestmark = pytest.mark.integration


async def test_category_budget_spent_is_computed(alice, session, kaspi_id):
    food = await system_category(session, "Продукты")
    today = date.today()
    for amount in ("300.00", "200.00"):
        await alice.post(
            "/transactions",
            json={
                "amount": amount,
                "transaction_type": "expense",
                "transaction_date": f"{today.isoformat()}T10:00:00",
                "category_id": food,
                "bank_id": kaspi_id,
            },
        )
    # операция прошлого года не учитывается
    await alice.post(
        "/transactions",
        json={
            "amount": "999.00",
            "transaction_type": "expense",
            "transaction_date": f"{today.year - 1}-01-15T10:00:00",
            "category_id": food,
            "bank_id": kaspi_id,
        },
    )

    budget = (await alice.post("/budgets", json={"title": "Еда", "monthly_limit": "600", "category_id": food})).json()
    assert budget["spent"] == "500.00"
    assert budget["spent_source"] == "transactions"

    manual = (await alice.post("/budgets", json={"title": "Ручной", "monthly_limit": "100"})).json()
    await alice.put(f"/budgets/{manual['id']}", json={"spent": "90"})

    detail = (await alice.get(f"/budgets/{budget['id']}")).json()
    assert detail["remaining"] == "100.00"
    assert detail["is_exceeded"] is False

    stats = (await alice.get("/budgets/statistics")).json()
    assert stats["total_budget"] == "700.00"
    assert stats["total_spent"] == "590.00"

    alerts = (await alice.get("/budgets/alerts", params={"threshold": 80})).json()
    assert {a["title"] for a in alerts} == {"Еда", "Ручной"}


async def test_budget_rejects_income_category(alice, session):
    salary = await system_category(session, "Зарплата", "income")
    response = await alice.post("/budgets", json={"title": "x1", "monthly_limit": "1", "category_id": salary})
    assert response.json()["error"]["code"] == "CATEGORY_KIND_MISMATCH"


async def test_deposit_profit_uses_decimal_calculator(alice, kaspi_id):
    body = {
        "amount": "1000000",
        "interest_rate": "14.5",
        "start_date": "2025-01-01",
        "end_date": "2025-07-01",
        "bank_id": kaspi_id,
    }
    deposit = (await alice.post("/investments", json=body)).json()
    detail = (await alice.get(f"/investments/{deposit['id']}")).json()
    assert detail["expected_profit"] == "71904.11"
    assert detail["expected_amount"] == "1071904.11"
    assert detail["bank_name"] == "Kaspi Bank"

    bad = await alice.post("/investments", json={**body, "end_date": "2024-12-31"})
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "INVALID_DATE_RANGE"

    bad_update = await alice.put(f"/investments/{deposit['id']}", json={"end_date": "2024-01-01"})
    assert bad_update.status_code == 400

    chart = (await alice.get("/investments/chart")).json()
    assert chart == [{"label": "Kaspi Bank", "amount": "1000000.00"}]
