"""User B must never read, change or delete user A's records (IDOR checks)."""

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bank import Bank
from tests.integration.helpers import bearer, register

API = "/api/v1"


@pytest.fixture
async def bank_id(db_session: AsyncSession) -> int:
    # There is no public endpoint to create a bank (banks are created by imports).
    bank = Bank(name="Test Bank")
    db_session.add(bank)
    await db_session.commit()
    return bank.id


@pytest.fixture
async def two_users(client: httpx.AsyncClient) -> tuple[dict[str, str], dict[str, str]]:
    return (
        bearer(await register(client, "alice@example.com")),
        bearer(await register(client, "bob@example.com")),
    )


async def _create_alice_records(
    client: httpx.AsyncClient, alice: dict[str, str], bank_id: int
) -> dict[str, str]:
    category = await client.post(
        f"{API}/transactions/categories", headers=alice, json={"name": "Продукты для дома"}
    )
    assert category.status_code == 201, category.text

    tx = await client.post(
        f"{API}/transactions",
        headers=alice,
        json={
            "amount": "15000.50",
            "description": "groceries",
            "transaction_type": "expense",
            "transaction_date": "2025-03-01T10:00:00",
            "category_id": category.json()["id"],
            "bank_id": bank_id,
        },
    )
    assert tx.status_code == 201, tx.text

    budget = await client.post(
        f"{API}/budgets", headers=alice, json={"title": "Еда", "monthly_limit": "100000.00"}
    )
    assert budget.status_code == 201, budget.text

    deposit = await client.post(
        f"{API}/investments",
        headers=alice,
        json={
            "amount": "500000.00",
            "interest_rate": "14.00",
            "start_date": "2025-01-01",
            "end_date": "2026-01-01",
            "bank_id": bank_id,
        },
    )
    assert deposit.status_code == 201, deposit.text

    return {
        "transactions": f"{API}/transactions/{tx.json()['id']}",
        "budgets": f"{API}/budgets/{budget.json()['id']}",
        "investments": f"{API}/investments/{deposit.json()['id']}",
    }


async def test_owner_can_read_own_records(
    client: httpx.AsyncClient, two_users: tuple[dict[str, str], dict[str, str]], bank_id: int
) -> None:
    alice, _ = two_users
    urls = await _create_alice_records(client, alice, bank_id)
    for url in urls.values():
        assert (await client.get(url, headers=alice)).status_code == 200

    detail = (await client.get(urls["investments"], headers=alice)).json()
    assert detail["expected_profit"] == "70000.00"  # 500 000 * 14% * 365/365


@pytest.mark.parametrize("resource", ["transactions", "budgets", "investments"])
async def test_other_user_cannot_access_records(
    client: httpx.AsyncClient,
    two_users: tuple[dict[str, str], dict[str, str]],
    bank_id: int,
    resource: str,
) -> None:
    alice, bob = two_users
    url = (await _create_alice_records(client, alice, bank_id))[resource]

    assert (await client.get(url, headers=bob)).status_code == 404
    assert (await client.put(url, headers=bob, json={})).status_code == 404
    assert (await client.delete(url, headers=bob)).status_code == 404
    # Still intact for the owner.
    assert (await client.get(url, headers=alice)).status_code == 200


async def test_lists_and_aggregates_are_scoped_to_the_user(
    client: httpx.AsyncClient, two_users: tuple[dict[str, str], dict[str, str]], bank_id: int
) -> None:
    alice, bob = two_users
    await _create_alice_records(client, alice, bank_id)

    for path in ("/transactions", "/budgets", "/investments"):
        assert (await client.get(f"{API}{path}", headers=bob)).json()["total"] == 0
        assert (await client.get(f"{API}{path}", headers=alice)).json()["total"] == 1

    bob_stats = (await client.get(f"{API}/transactions/statistics", headers=bob)).json()
    assert bob_stats["total_expense"] == "0"

    alice_dashboard = await client.get(f"{API}/dashboard", headers=alice)
    bob_dashboard = await client.get(f"{API}/dashboard", headers=bob)
    assert alice_dashboard.status_code == bob_dashboard.status_code == 200
    assert len(alice_dashboard.json()["recent_transactions"]) == 1
    assert bob_dashboard.json()["recent_transactions"] == []


@pytest.mark.parametrize(
    "path",
    ["/transactions", "/budgets", "/investments", "/dashboard", "/analytics", "/upload/banks"],
)
async def test_protected_endpoints_require_authentication(
    client: httpx.AsyncClient, path: str
) -> None:
    response = await client.get(f"{API}{path}")
    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"
