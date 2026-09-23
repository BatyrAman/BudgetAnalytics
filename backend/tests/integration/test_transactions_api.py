
import pytest

from tests.integration.conftest import system_category

pytestmark = pytest.mark.integration


async def _create(user, category_id, bank_id, **overrides):
    body = {
        "amount": "15000.50",
        "description": "Magnum Almaty",
        "transaction_type": "expense",
        "transaction_date": "2025-03-10T12:00:00",
        "category_id": category_id,
        "bank_id": bank_id,
    }
    body.update(overrides)
    return await user.post("/transactions", json=body)


async def test_crud_roundtrip(alice, session, kaspi_id):
    food = await system_category(session, "Продукты")
    created = await _create(alice, food, kaspi_id)
    assert created.status_code == 201, created.text
    data = created.json()
    assert data["amount"] == "15000.50"
    assert data["merchant"] == "MAGNUM ALMATY"
    assert data["category_source"] == "user"

    detail = await alice.get(f"/transactions/{data['id']}")
    assert detail.status_code == 200
    assert detail.json()["category_name"] == "Продукты"
    assert detail.json()["bank_name"] == "Kaspi Bank"

    updated = await alice.put(f"/transactions/{data['id']}", json={"amount": "100.00"})
    assert updated.json()["amount"] == "100.00"

    listed = await alice.get("/transactions", params={"min_amount": "50"})
    assert listed.json()["total"] == 1

    assert (await alice.delete(f"/transactions/{data['id']}")).status_code == 204
    missing = await alice.get(f"/transactions/{data['id']}")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "TRANSACTION_NOT_FOUND"


async def test_validation_errors_have_unified_format(alice, session, kaspi_id):
    food = await system_category(session, "Продукты")
    response = await _create(alice, food, kaspi_id, amount="-5")
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "input" not in str(body["error"]["details"])

    too_precise = await _create(alice, food, kaspi_id, amount="1.001")
    assert too_precise.status_code == 422


async def test_unknown_references_are_rejected(alice, session, kaspi_id):
    food = await system_category(session, "Продукты")
    assert (await _create(alice, 999_999, kaspi_id)).json()["error"]["code"] == "CATEGORY_NOT_FOUND"
    assert (await _create(alice, food, 999_999)).json()["error"]["code"] == "BANK_NOT_FOUND"
    assert (await _create(alice, food, kaspi_id, card_id=999_999)).json()["error"]["code"] == "CARD_NOT_FOUND"


async def test_category_kind_must_match_type(alice, session, kaspi_id):
    salary = await system_category(session, "Зарплата", "income")
    response = await _create(alice, salary, kaspi_id)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "CATEGORY_KIND_MISMATCH"
    ok = await _create(alice, salary, kaspi_id, transaction_type="income")
    assert ok.status_code == 201


async def test_statistics_and_chart_aggregate_in_sql(alice, session, kaspi_id):
    food = await system_category(session, "Продукты")
    salary = await system_category(session, "Зарплата", "income")
    await _create(alice, food, kaspi_id, amount="100.00", transaction_date="2025-01-05T10:00:00")
    await _create(alice, food, kaspi_id, amount="300.00", transaction_date="2025-02-05T10:00:00")
    await _create(alice, salary, kaspi_id, amount="1000.00", transaction_type="income",
                  transaction_date="2025-02-01T09:00:00")

    stats = (await alice.get("/transactions/statistics")).json()
    assert stats == {
        "total_transactions": 3,
        "total_income": "1000.00",
        "total_expense": "400.00",
        "current_balance": "600.00",
        "average_expense": "200.00",
        "average_income": "1000.00",
    }

    chart = (await alice.get("/transactions/chart", params={"months": 6})).json()
    assert chart == [
        {"label": "2025-01", "income": "0.00", "expense": "100.00"},
        {"label": "2025-02", "income": "1000.00", "expense": "300.00"},
    ]


async def test_user_categories(alice, bob):
    created = await alice.post("/transactions/categories", json={"name": "Хобби", "kind": "expense"})
    assert created.status_code == 201
    assert created.json()["is_system"] is False

    dup = await alice.post("/transactions/categories", json={"name": "хобби"})
    assert dup.status_code == 409

    # Bob может создать категорию с тем же именем — нет глобального unique
    assert (await bob.post("/transactions/categories", json={"name": "Хобби"})).status_code == 201

    names_alice = [c["name"] for c in (await alice.get("/transactions/categories")).json()]
    assert names_alice.count("Хобби") == 1
    assert "Продукты" in names_alice


async def test_system_category_cannot_be_modified(alice, session):
    food = await system_category(session, "Продукты")
    assert (await alice.put(f"/transactions/categories/{food}", json={"name": "Еда"})).status_code == 404
    assert (await alice.delete(f"/transactions/categories/{food}")).status_code == 404


async def test_deleting_category_keeps_transactions(alice, kaspi_id):
    category = (await alice.post("/transactions/categories", json={"name": "Разное"})).json()
    tx = (await _create(alice, category["id"], kaspi_id)).json()
    assert (await alice.delete(f"/transactions/categories/{category['id']}")).status_code == 204
    detail = (await alice.get(f"/transactions/{tx['id']}")).json()
    assert detail["category_id"] is None
    assert detail["category_name"] == "—"


async def test_cards_store_only_last4(alice, kaspi_id):
    rejected = await alice.post("/cards", json={"bank_id": kaspi_id, "last4": "4400430012345678"})
    assert rejected.status_code == 422
    card = await alice.post(
        "/cards", json={"bank_id": kaspi_id, "last4": "1234", "card_type": "credit", "credit_limit": "500000"}
    )
    assert card.status_code == 201, card.text
    assert card.json()["bank_name"] == "Kaspi Bank"
    assert card.json()["credit_limit"] == "500000.00"
    debit_limit = await alice.post("/cards", json={"bank_id": kaspi_id, "last4": "1111", "credit_limit": "1"})
    assert debit_limit.status_code == 422
