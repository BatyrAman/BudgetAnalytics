"""GET /budgets/utilization — actual usage of ALL budgets in one call (G-6).

Expected values are computed by hand (month 2025-03, tz Asia/Almaty = UTC+5):

* "Food KZT" (category Food, limit 150 000.00): expenses 70 000 + 50 000,
  refund 1 600 -> spent 118 400.00; remaining 31 600.00;
  118 400 / 150 000 * 100 = 78.9333... -> 78.93 %; not exceeded.
  The Food expense of 9 999 at 2025-03-31T19:30Z is 2025-04-01 00:30 local ->
  April, excluded.
* "All KZT" (no category, limit 100 000.00): 118 400 (Food) + 5 000 + 1 000
  (Transport; the 1 000 at 2025-02-28T19:30Z is 2025-03-01 00:30 local ->
  March) = 124 400.00; remaining -24 400.00; 124.40 %; exceeded.
  Income 300 000 is not spending; Bob's 50 000 is not Alice's.
* "All USD" (no category, limit 500.00): 200.00 -> remaining 300.00; 40.00 %.
* "Food USD" (category Food, limit 100.00): no USD Food spending -> 0.00,
  remaining 100.00, 0.00 %.
"""

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest

from app.main import app
from tests.integration.helpers import API, bearer, category, create, register, tx


@pytest.fixture
async def alice(client: httpx.AsyncClient) -> dict[str, str]:
    return bearer(await register(client, "alice@example.com"))


@pytest.fixture
async def bob(client: httpx.AsyncClient) -> dict[str, str]:
    return bearer(await register(client, "bob@example.com"))


async def _budget(
    client: httpx.AsyncClient, headers: dict[str, str], **body: Any
) -> dict[str, Any]:
    return await create(client, "/budgets", headers, body)


@pytest.fixture
async def data(
    client: httpx.AsyncClient, alice: dict[str, str], bob: dict[str, str]
) -> dict[str, Any]:
    food = await category(client, alice, "Food")
    transport = await category(client, alice, "Transport")
    salary = (await create(client, "/categories", alice, {"name": "Salary", "kind": "income"}))[
        "id"
    ]

    await tx(client, alice, food, "70000.00", "expense", "2025-03-05T10:00:00Z")
    await tx(client, alice, food, "50000.00", "expense", "2025-03-20T10:00:00Z")
    await tx(client, alice, food, "1600.00", "refund", "2025-03-21T10:00:00Z")
    await tx(client, alice, food, "9999.00", "expense", "2025-03-31T19:30:00Z")  # April local
    await tx(client, alice, transport, "5000.00", "expense", "2025-03-12T10:00:00Z")
    await tx(client, alice, transport, "1000.00", "expense", "2025-02-28T19:30:00Z")  # March local
    await tx(client, alice, salary, "300000.00", "income", "2025-03-01T10:00:00Z")
    await tx(client, alice, transport, "200.00", "expense", "2025-03-15T10:00:00Z", currency="USD")

    bob_food = await category(client, bob, "Food")
    await tx(client, bob, bob_food, "50000.00", "expense", "2025-03-05T10:00:00Z")

    budgets = {
        "food_kzt": await _budget(
            client, alice, title="Food KZT", monthly_limit="150000.00", category_id=food
        ),
        "all_kzt": await _budget(client, alice, title="All KZT", monthly_limit="100000.00"),
        "all_usd": await _budget(
            client, alice, title="All USD", monthly_limit="500.00", currency="USD"
        ),
        "food_usd": await _budget(
            client,
            alice,
            title="Food USD",
            monthly_limit="100.00",
            currency="USD",
            category_id=food,
        ),
        "bob": await _budget(client, bob, title="Bob budget", monthly_limit="1000.00"),
    }
    return budgets


EXPECTED = {
    "food_kzt": ("KZT", "150000.00", "118400.00", "31600.00", "78.93", False),
    "all_kzt": ("KZT", "100000.00", "124400.00", "-24400.00", "124.40", True),
    "all_usd": ("USD", "500.00", "200.00", "300.00", "40.00", False),
    "food_usd": ("USD", "100.00", "0.00", "100.00", "0.00", False),
}


def _values(item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        item["currency_code"],
        item["limit"],
        item["spent"],
        item["remaining"],
        item["utilization_percent"],
        item["is_exceeded"],
    )


async def test_all_budgets_hand_computed(
    client: httpx.AsyncClient, alice: dict[str, str], data: dict[str, Any]
) -> None:
    response = await client.get(
        f"{API}/budgets/utilization",
        headers=alice,
        params={"month": "2025-03", "tz": "Asia/Almaty"},
    )
    assert response.status_code == 200, response.text
    items = response.json()

    ids = {key: data[key]["id"] for key in EXPECTED}
    # Every Alice budget, every currency, ordered by id; nothing of Bob's.
    assert [i["budget_id"] for i in items] == sorted(ids.values())
    assert data["bob"]["id"] not in {i["budget_id"] for i in items}
    by_id = {i["budget_id"]: i for i in items}
    for key, expected in EXPECTED.items():
        item = by_id[ids[key]]
        assert item["month"] == "2025-03"
        assert _values(item) == expected, key


async def test_each_item_equals_single_budget_endpoint(
    client: httpx.AsyncClient, alice: dict[str, str], data: dict[str, Any]
) -> None:
    params = {"month": "2025-03", "tz": "Asia/Almaty"}
    items = (await client.get(f"{API}/budgets/utilization", headers=alice, params=params)).json()
    for item in items:
        single = await client.get(
            f"{API}/budgets/{item['budget_id']}/utilization", headers=alice, params=params
        )
        assert single.status_code == 200
        assert single.json() == item


async def test_timezone_moves_month_boundary(
    client: httpx.AsyncClient, alice: dict[str, str], data: dict[str, Any]
) -> None:
    # In UTC the 1 000 on 2025-02-28T19:30Z is February and the 9 999 on
    # 2025-03-31T19:30Z is March: Food KZT = 118 400 + 9 999 = 128 399.00
    # (85.5993... -> 85.60 %), All KZT = 128 399 + 5 000 = 133 399.00 (133.40 %).
    items = (
        await client.get(
            f"{API}/budgets/utilization", headers=alice, params={"month": "2025-03", "tz": "UTC"}
        )
    ).json()
    by_id = {i["budget_id"]: i for i in items}
    food = by_id[data["food_kzt"]["id"]]
    everything = by_id[data["all_kzt"]["id"]]
    assert (food["spent"], food["utilization_percent"]) == ("128399.00", "85.60")
    assert (everything["spent"], everything["utilization_percent"]) == ("133399.00", "133.40")


async def test_other_month_is_empty_spending(
    client: httpx.AsyncClient, alice: dict[str, str], data: dict[str, Any]
) -> None:
    items = (
        await client.get(f"{API}/budgets/utilization", headers=alice, params={"month": "2024-01"})
    ).json()
    assert len(items) == 4
    assert all(i["spent"] == "0.00" and i["utilization_percent"] == "0.00" for i in items)


async def test_tenant_isolation(
    client: httpx.AsyncClient, bob: dict[str, str], data: dict[str, Any]
) -> None:
    items = (
        await client.get(
            f"{API}/budgets/utilization",
            headers=bob,
            params={"month": "2025-03", "tz": "Asia/Almaty"},
        )
    ).json()
    assert [i["budget_id"] for i in items] == [data["bob"]["id"]]
    assert items[0]["spent"] == "50000.00"  # only Bob's own expense
    assert items[0]["utilization_percent"] == "5000.00"


async def test_default_month_is_current_local_month(
    client: httpx.AsyncClient, alice: dict[str, str]
) -> None:
    await _budget(client, alice, title="Any", monthly_limit="10.00")
    items = (await client.get(f"{API}/budgets/utilization", headers=alice)).json()
    expected = f"{datetime.now(ZoneInfo('Asia/Almaty')):%Y-%m}"
    assert [i["month"] for i in items] == [expected]


async def test_no_budgets_and_unauthenticated(
    client: httpx.AsyncClient, alice: dict[str, str]
) -> None:
    response = await client.get(f"{API}/budgets/utilization", headers=alice)
    assert response.status_code == 200
    assert response.json() == []
    unauthenticated = await client.get(f"{API}/budgets/utilization")
    assert unauthenticated.status_code == 401


async def test_legacy_manual_fields_unchanged_and_marked_deprecated(
    client: httpx.AsyncClient, alice: dict[str, str]
) -> None:
    budget = await _budget(client, alice, title="Manual", monthly_limit="1000.00")
    patched = await client.patch(
        f"{API}/budgets/{budget['id']}", headers=alice, json={"spent": "1200.00"}
    )
    assert patched.json()["spent"] == "1200.00"
    detail = (await client.get(f"{API}/budgets/{budget['id']}", headers=alice)).json()
    assert (detail["remaining"], detail["progress"], detail["is_exceeded"]) == (
        "-200.00",
        120.0,
        True,
    )

    schemas = app.openapi()["components"]["schemas"]
    assert "DEPRECATED" in schemas["BudgetResponse"]["properties"]["spent"]["description"]
    for field in ("remaining", "progress", "is_exceeded"):
        description = schemas["BudgetDetail"]["properties"][field]["description"]
        assert "DEPRECATED" in description and "/budgets/utilization" in description
