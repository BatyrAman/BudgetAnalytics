"""Transaction CRUD, filtering, pagination and date ranges."""

import httpx
import pytest

from tests.integration.helpers import API, bearer, category, create, register, tx


@pytest.fixture
async def setup(client: httpx.AsyncClient) -> dict[str, object]:
    alice = bearer(await register(client, "alice@example.com"))
    food = await category(client, alice, "Еда")
    taxi = await category(client, alice, "Такси")
    card = await create(
        client,
        "/accounts",
        alice,
        {"name": "Card", "account_type": "card", "opening_balance_at": "2020-01-01T00:00:00Z"},
    )
    rows = [
        (food, "1000.00", "expense", "2025-03-01T00:00:00Z", {"description": "Magnum супермаркет"}),
        (food, "2500.50", "expense", "2025-03-15T12:00:00Z", {"account_id": card["id"]}),
        (taxi, "3000.00", "expense", "2025-03-31T23:59:59Z", {"description": "Yandex Go"}),
        (food, "500.00", "refund", "2025-04-01T00:00:00Z", {}),
        (taxi, "50.00", "expense", "2025-04-02T00:00:00Z", {"currency": "USD"}),
    ]
    for cat, amount, kind, when, extra in rows:
        await tx(client, alice, cat, amount, kind, when, **extra)
    return {"alice": alice, "food": food, "taxi": taxi, "card": card["id"]}


async def _list(client: httpx.AsyncClient, headers: dict[str, str], **params: object) -> dict:  # type: ignore[type-arg]
    response = await client.get(f"{API}/transactions", headers=headers, params=params)
    assert response.status_code == 200, response.text
    return response.json()


async def test_pagination_is_newest_first_and_stable(
    client: httpx.AsyncClient, setup: dict
) -> None:  # type: ignore[type-arg]
    page1 = await _list(client, setup["alice"], limit=2, offset=0)
    page2 = await _list(client, setup["alice"], limit=2, offset=2)
    page3 = await _list(client, setup["alice"], limit=2, offset=4)
    assert page1["total"] == 5 and (page1["limit"], page1["offset"]) == (2, 0)
    dates = [t["transaction_date"] for p in (page1, page2, page3) for t in p["items"]]
    assert dates == sorted(dates, reverse=True) and len(dates) == 5


@pytest.mark.parametrize(
    ("params", "expected_amounts"),
    [
        (
            {"start_date": "2025-03-01T00:00:00Z", "end_date": "2025-03-31T23:59:59Z"},
            {"1000.00", "2500.50", "3000.00"},
        ),
        ({"start_date": "2025-04-01T00:00:00Z"}, {"500.00", "50.00"}),
        ({"transaction_type": "refund"}, {"500.00"}),
        ({"currency": "USD"}, {"50.00"}),
        ({"min_amount": "1000", "max_amount": "2500.50"}, {"1000.00", "2500.50"}),
        ({"search": "magnum"}, {"1000.00"}),  # case-insensitive
        ({"search": "100%"}, set()),  # LIKE wildcards are escaped
    ],
)
async def test_filters(
    client: httpx.AsyncClient, setup: dict, params: dict, expected_amounts: set
) -> None:  # type: ignore[type-arg]
    body = await _list(client, setup["alice"], **params)
    assert {t["amount"] for t in body["items"]} == expected_amounts
    assert body["total"] == len(expected_amounts)


async def test_filter_by_category_and_account(client: httpx.AsyncClient, setup: dict) -> None:  # type: ignore[type-arg]
    assert (await _list(client, setup["alice"], category_id=setup["taxi"]))["total"] == 2
    by_account = await _list(client, setup["alice"], account_id=setup["card"])
    assert [t["amount"] for t in by_account["items"]] == ["2500.50"]


@pytest.mark.parametrize(
    "params",
    [
        {"start_date": "2025-04-01T00:00:00Z", "end_date": "2025-03-01T00:00:00Z"},
        {"min_amount": "10", "max_amount": "5"},
        {"limit": 0},
        {"limit": 201},
        {"currency": "kzt"},
        {"transaction_type": "gift"},
    ],
)
async def test_invalid_filters(client: httpx.AsyncClient, setup: dict, params: dict) -> None:  # type: ignore[type-arg]
    response = await client.get(f"{API}/transactions", headers=setup["alice"], params=params)
    assert response.status_code == 422


async def test_patch_update_and_delete(client: httpx.AsyncClient, setup: dict) -> None:  # type: ignore[type-arg]
    tid = (await _list(client, setup["alice"], search="Yandex"))["items"][0]["id"]
    patched = await client.patch(
        f"{API}/transactions/{tid}",
        headers=setup["alice"],
        json={"amount": "3100.00", "transaction_type": "expense", "account_id": setup["card"]},
    )
    assert patched.status_code == 200
    assert (patched.json()["amount"], patched.json()["account_id"]) == ("3100.00", setup["card"])
    unlinked = await client.patch(
        f"{API}/transactions/{tid}", headers=setup["alice"], json={"account_id": None}
    )
    assert unlinked.json()["account_id"] is None
    assert (
        await client.patch(
            f"{API}/transactions/{tid}", headers=setup["alice"], json={"amount": None}
        )
    ).status_code == 422
    detail = (await client.get(f"{API}/transactions/{tid}", headers=setup["alice"])).json()
    assert detail["category_name"] == "Такси" and detail["bank_name"] == "—"
    assert (
        await client.delete(f"{API}/transactions/{tid}", headers=setup["alice"])
    ).status_code == 204
    assert (
        await client.get(f"{API}/transactions/{tid}", headers=setup["alice"])
    ).status_code == 404


async def test_other_user_cannot_touch_transactions(client: httpx.AsyncClient, setup: dict) -> None:  # type: ignore[type-arg]
    bob = bearer(await register(client, "bob@example.com"))
    tid = (await _list(client, setup["alice"], limit=1))["items"][0]["id"]
    assert (await client.get(f"{API}/transactions/{tid}", headers=bob)).status_code == 404
    assert (
        await client.patch(f"{API}/transactions/{tid}", headers=bob, json={"amount": "1"})
    ).status_code == 404
    assert (await client.delete(f"{API}/transactions/{tid}", headers=bob)).status_code == 404
    assert (await _list(client, bob))["total"] == 0


async def test_openapi_documents_every_module_and_hides_secrets(client: httpx.AsyncClient) -> None:
    schema = (await client.get("/openapi.json")).json()
    paths = schema["paths"]
    for path in [
        "/api/v1/auth/logout",
        "/api/v1/auth/logout-all",
        "/api/v1/categories/{category_id}",
        "/api/v1/accounts/{account_id}",
        "/api/v1/transactions/{transaction_id}",
        "/api/v1/budgets/{budget_id}/utilization",
        "/api/v1/deposits/calculate",
        "/api/v1/analytics/summary",
        "/api/v1/analytics/comparison",
        "/api/v1/dashboard/overview",
    ]:
        assert path in paths, path
    assert paths["/api/v1/dashboard"]["get"].get("deprecated") is True
    assert paths["/api/v1/analytics/cash-flow"]["get"].get("deprecated") is True
    text = str(schema)
    assert "hashed_password" not in text and "SECRET_KEY" not in text
