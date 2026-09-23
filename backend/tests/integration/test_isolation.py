"""
Горизонтальная эскалация привилегий: пользователь B не может
прочитать, изменить или удалить ресурсы пользователя A, подменив ID
в URL или в теле запроса. Ответ — 404 (без раскрытия существования).
"""

import pytest

from tests.integration.conftest import system_category

pytestmark = pytest.mark.integration


@pytest.fixture
async def alice_data(alice, session, kaspi_id):
    food = await system_category(session, "Продукты")
    category = (await alice.post("/transactions/categories", json={"name": "Личное"})).json()
    card = (await alice.post("/cards", json={"bank_id": kaspi_id, "last4": "1234"})).json()
    tx = (await alice.post("/transactions", json={
        "amount": "100", "transaction_type": "expense", "transaction_date": "2025-01-01T10:00:00",
        "category_id": food, "bank_id": kaspi_id, "card_id": card["id"]})).json()
    budget = (await alice.post("/budgets", json={"title": "Еда", "monthly_limit": "1000"})).json()
    deposit = (await alice.post("/investments", json={
        "amount": "1000", "interest_rate": "10", "start_date": "2025-01-01", "end_date": "2026-01-01",
        "bank_id": kaspi_id})).json()
    debt = (await alice.post("/debts", json={
        "name": "Кредит", "debt_type": "consumer_loan", "principal": "100000", "annual_rate": "20",
        "monthly_payment": "10000", "payment_day": 5, "start_date": "2025-01-01"})).json()
    payment = (await alice.post(f"/debts/{debt['id']}/payments", json={"amount": "10000"})).json()
    upload = (await alice.post("/upload/kaspi", files={"file": ("s.csv", b"date,description,amount\n2025-01-01,x,-1\n", "text/csv")})).json()
    return {
        "category": category["id"], "card": card["id"], "tx": tx["id"], "budget": budget["id"],
        "deposit": deposit["id"], "debt": debt["id"], "payment": payment["id"], "import": upload["import_id"],
    }


READ_PATHS = [
    "/transactions/{tx}",
    "/cards/{card}",
    "/budgets/{budget}",
    "/investments/{deposit}",
    "/investments/{deposit}/forecast",
    "/debts/{debt}",
    "/debts/{debt}/schedule",
    "/debts/{debt}/payments",
    "/imports/{import}",
]


@pytest.mark.parametrize("template", READ_PATHS)
async def test_cannot_read_foreign_resources(alice_data, bob, template):
    response = await bob.get(template.format(**alice_data))
    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"].endswith("NOT_FOUND")


@pytest.mark.parametrize(
    "template, body",
    [
        ("/transactions/{tx}", {"amount": "1"}),
        ("/transactions/categories/{category}", {"name": "Взлом"}),
        ("/cards/{card}", {"nickname": "pwned"}),
        ("/budgets/{budget}", {"title": "pwned"}),
        ("/investments/{deposit}", {"amount": "1"}),
        ("/debts/{debt}", {"balance": "0"}),
    ],
)
async def test_cannot_modify_foreign_resources(alice_data, alice, bob, template, body):
    path = template.format(**alice_data)
    assert (await bob.put(path, json=body)).status_code == 404


@pytest.mark.parametrize(
    "template",
    [
        "/transactions/{tx}",
        "/transactions/categories/{category}",
        "/cards/{card}",
        "/budgets/{budget}",
        "/investments/{deposit}",
        "/debts/{debt}",
        "/debts/{debt}/payments/{payment}",
    ],
)
async def test_cannot_delete_foreign_resources(alice_data, alice, bob, template):
    path = template.format(**alice_data)
    assert (await bob.delete(path)).status_code == 404


async def test_resources_survive_foreign_attempts(alice_data, alice, bob):
    await bob.put(f"/transactions/{alice_data['tx']}", json={"amount": "1"})
    await bob.delete(f"/debts/{alice_data['debt']}")
    assert (await alice.get(f"/transactions/{alice_data['tx']}")).json()["amount"] == "100.00"
    assert (await alice.get(f"/debts/{alice_data['debt']}")).status_code == 200


async def test_cannot_act_on_foreign_debt(alice_data, bob):
    debt = alice_data["debt"]
    assert (await bob.post(f"/debts/{debt}/payments", json={"amount": "1"})).status_code == 404
    assert (await bob.post(f"/debts/{debt}/prepayment", json={"amount": "1"})).status_code == 404


async def test_cannot_reference_foreign_ids_in_body(alice_data, bob, kaspi_id):
    body = {"amount": "1", "transaction_type": "expense", "transaction_date": "2025-01-01T10:00:00",
            "bank_id": kaspi_id}
    foreign_category = await bob.post("/transactions", json={**body, "category_id": alice_data["category"]})
    assert foreign_category.json()["error"]["code"] == "CATEGORY_NOT_FOUND"
    budget = await bob.post("/budgets", json={"title": "x1", "monthly_limit": "1", "category_id": alice_data["category"]})
    assert budget.json()["error"]["code"] == "CATEGORY_NOT_FOUND"
    upload = await bob.post("/upload/kaspi", params={"card_id": alice_data["card"]},
                            files={"file": ("s.csv", b"date,amount\n2025-01-01,-1\n", "text/csv")})
    assert upload.status_code == 404


async def test_lists_never_contain_foreign_data(alice_data, bob):
    for path in ("/transactions", "/budgets", "/investments"):
        assert (await bob.get(path)).json()["total"] == 0, path
    for path in ("/cards", "/debts", "/imports", "/debts/calendar", "/investments/chart", "/budgets/progress"):
        assert (await bob.get(path)).json() == [], path
    names = [c["name"] for c in (await bob.get("/transactions/categories")).json()]
    assert "Личное" not in names
    assert (await bob.get("/transactions/statistics")).json()["total_transactions"] == 0
    dashboard = (await bob.get("/dashboard")).json()
    assert dashboard["recent_transactions"] == [] and dashboard["deposits"] == []


async def test_unauthenticated_requests_are_rejected(client):
    from tests.integration.conftest import API

    for path in ("/transactions", "/debts", "/cards", "/analytics/overview", "/dashboard"):
        response = await client.get(API + path)
        assert response.status_code == 401
        assert response.headers.get("www-authenticate") == "Bearer"


async def test_health_endpoints(client):
    assert (await client.get("/health")).json()["status"] == "healthy"
    assert (await client.get("/health/ready")).json() == {"status": "ready"}
