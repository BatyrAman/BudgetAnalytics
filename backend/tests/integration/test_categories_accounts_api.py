from decimal import Decimal

import httpx
import pytest

from tests.integration.helpers import API, bearer, category, create, register, tx


@pytest.fixture
async def alice(client: httpx.AsyncClient) -> dict[str, str]:
    return bearer(await register(client, "alice@example.com"))


@pytest.fixture
async def bob(client: httpx.AsyncClient) -> dict[str, str]:
    return bearer(await register(client, "bob@example.com"))


class TestCategories:
    async def test_defaults_are_visible_and_read_only(
        self, client: httpx.AsyncClient, alice: dict[str, str]
    ) -> None:
        listed = (await client.get(f"{API}/categories", headers=alice)).json()
        system = {c["name"]: c for c in listed if c["is_system"]}
        assert {"Продукты", "Зарплата", "Без категории"} <= system.keys()

        food = system["Продукты"]["id"]
        assert (
            await client.patch(f"{API}/categories/{food}", headers=alice, json={"name": "Еда"})
        ).status_code == 403
        assert (await client.delete(f"{API}/categories/{food}", headers=alice)).status_code == 403
        # A private category may not shadow a system name.
        assert (
            await client.post(f"{API}/categories", headers=alice, json={"name": "Продукты"})
        ).status_code == 409

    async def test_crud_of_own_category(
        self, client: httpx.AsyncClient, alice: dict[str, str]
    ) -> None:
        created = await create(
            client, "/categories", alice, {"name": "Хобби", "color": "#112233", "icon": "star"}
        )
        assert created["is_system"] is False
        cid = created["id"]
        patched = await client.patch(
            f"{API}/categories/{cid}", headers=alice, json={"name": "Хобби и спорт"}
        )
        assert patched.status_code == 200 and patched.json()["name"] == "Хобби и спорт"
        assert (await client.get(f"{API}/categories/{cid}", headers=alice)).status_code == 200
        assert (await client.delete(f"{API}/categories/{cid}", headers=alice)).status_code == 204
        assert (await client.get(f"{API}/categories/{cid}", headers=alice)).status_code == 404

    async def test_other_users_category_is_not_found(
        self, client: httpx.AsyncClient, alice: dict[str, str], bob: dict[str, str]
    ) -> None:
        cid = await category(client, alice, "Секрет")
        for method in ("get", "delete"):
            assert (
                await getattr(client, method)(f"{API}/categories/{cid}", headers=bob)
            ).status_code == 404
        assert (
            await client.patch(f"{API}/categories/{cid}", headers=bob, json={"name": "x2"})
        ).status_code == 404

    async def test_category_in_use_cannot_be_deleted(
        self, client: httpx.AsyncClient, alice: dict[str, str]
    ) -> None:
        cid = await category(client, alice, "Кофе")
        await tx(client, alice, cid, "1500", "expense", "2025-03-01T10:00:00Z")
        response = await client.delete(f"{API}/categories/{cid}", headers=alice)
        assert response.status_code == 409

    @pytest.mark.parametrize(
        "body", [{"name": "A"}, {"name": "Ок", "color": "red"}, {"name": "Ок", "icon": "Bad Icon"}]
    )
    async def test_validation(
        self, client: httpx.AsyncClient, alice: dict[str, str], body: dict
    ) -> None:  # type: ignore[type-arg]
        assert (await client.post(f"{API}/categories", headers=alice, json=body)).status_code == 422

    async def test_patch_rejects_null(
        self, client: httpx.AsyncClient, alice: dict[str, str]
    ) -> None:
        cid = await category(client, alice, "Нулл")
        assert (
            await client.patch(f"{API}/categories/{cid}", headers=alice, json={"name": None})
        ).status_code == 422


class TestAccounts:
    async def test_balance_is_opening_plus_linked_flows(
        self, client: httpx.AsyncClient, alice: dict[str, str]
    ) -> None:
        account = await create(
            client,
            "/accounts",
            alice,
            {
                "name": "Kaspi Gold",
                "account_type": "card",
                "last4": "1234",
                "opening_balance": "100000.00",
                "opening_balance_at": "2025-03-01T00:00:00Z",
            },
        )
        assert account["currency_code"] == "KZT" and account["balance"] == "100000.00"
        aid = account["id"]
        cid = await category(client, alice, "Разное")
        for amount, kind, when in [
            ("250000", "income", "2025-03-05T10:00:00Z"),
            ("80000", "expense", "2025-03-06T10:00:00Z"),
            ("3000", "refund", "2025-03-07T10:00:00Z"),
            ("20000", "transfer_out", "2025-03-08T10:00:00Z"),
            ("50000", "transfer_in", "2025-03-09T10:00:00Z"),
            ("999", "expense", "2025-02-28T10:00:00Z"),  # before opening_balance_at: not counted
        ]:
            await tx(client, alice, cid, amount, kind, when, account_id=aid)
        await tx(client, alice, cid, "7777", "expense", "2025-03-10T10:00:00Z")  # unlinked

        # 100 000 + 250 000 − 80 000 + 3 000 − 20 000 + 50 000 = 303 000
        response = await client.get(f"{API}/accounts/{aid}", headers=alice)
        assert response.json()["balance"] == "303000.00"

    async def test_currency_must_match_account(
        self, client: httpx.AsyncClient, alice: dict[str, str]
    ) -> None:
        usd = await create(
            client,
            "/accounts",
            alice,
            {"name": "USD card", "account_type": "card", "currency": "USD"},
        )
        cid = await category(client, alice, "Путешествия")
        mismatch = await client.post(
            f"{API}/transactions",
            headers=alice,
            json={
                "amount": "10",
                "transaction_type": "expense",
                "transaction_date": "2025-03-01T00:00:00Z",
                "category_id": cid,
                "account_id": usd["id"],
                "currency": "KZT",
            },
        )
        assert mismatch.status_code == 400
        inherited = await tx(
            client, alice, cid, "10", "expense", "2025-03-01T00:00:00Z", account_id=usd["id"]
        )
        assert inherited["currency_code"] == "USD"

    async def test_other_users_account(
        self, client: httpx.AsyncClient, alice: dict[str, str], bob: dict[str, str]
    ) -> None:
        aid = (await create(client, "/accounts", alice, {"name": "Cash", "account_type": "cash"}))[
            "id"
        ]
        assert (await client.get(f"{API}/accounts/{aid}", headers=bob)).status_code == 404
        assert (
            await client.patch(f"{API}/accounts/{aid}", headers=bob, json={"name": "x"})
        ).status_code == 404
        assert (await client.delete(f"{API}/accounts/{aid}", headers=bob)).status_code == 404
        bob_cat = await category(client, bob, "Моё")
        linked = await client.post(
            f"{API}/transactions",
            headers=bob,
            json={
                "amount": "1",
                "transaction_type": "expense",
                "transaction_date": "2025-03-01T00:00:00Z",
                "category_id": bob_cat,
                "account_id": aid,
            },
        )
        assert linked.status_code == 400 and linked.json()["detail"] == "Account not found"
        assert (await client.get(f"{API}/accounts", headers=bob)).json() == []

    async def test_delete_and_archive(
        self, client: httpx.AsyncClient, alice: dict[str, str]
    ) -> None:
        aid = (
            await create(client, "/accounts", alice, {"name": "Old", "account_type": "current"})
        )["id"]
        cid = await category(client, alice, "X1")
        await tx(client, alice, cid, "5", "expense", "2099-01-01T00:00:00Z", account_id=aid)
        assert (await client.delete(f"{API}/accounts/{aid}", headers=alice)).status_code == 409
        archived = await client.patch(
            f"{API}/accounts/{aid}", headers=alice, json={"is_archived": True}
        )
        assert archived.json()["is_archived"] is True
        assert (await client.get(f"{API}/accounts", headers=alice)).json() == []
        assert (
            len((await client.get(f"{API}/accounts?include_archived=true", headers=alice)).json())
            == 1
        )

    @pytest.mark.parametrize(
        "body",
        [
            {
                "name": "C",
                "account_type": "card",
                "last4": "4400430012345678",
            },  # full number refused
            {"name": "C", "account_type": "crypto"},
            {"name": "C", "account_type": "card", "currency": "XYZ"},
            {"name": " ", "account_type": "card"},
        ],
    )
    async def test_validation(
        self, client: httpx.AsyncClient, alice: dict[str, str], body: dict
    ) -> None:  # type: ignore[type-arg]
        response = await client.post(f"{API}/accounts", headers=alice, json=body)
        assert response.status_code == 422
        assert "4400430012345678" not in response.text

    async def test_duplicate_name(self, client: httpx.AsyncClient, alice: dict[str, str]) -> None:
        await create(client, "/accounts", alice, {"name": "Main", "account_type": "card"})
        again = await client.post(
            f"{API}/accounts", headers=alice, json={"name": "Main", "account_type": "cash"}
        )
        assert again.status_code == 409


async def test_decimal_amounts_round_trip_exactly(
    client: httpx.AsyncClient, alice: dict[str, str]
) -> None:
    cid = await category(client, alice, "Точность")
    created = await tx(client, alice, cid, "0.10", "expense", "2025-03-01T00:00:00Z")
    assert Decimal(created["amount"]) == Decimal("0.10")
    assert isinstance(created["amount"], str)  # serialized as a decimal string, not a float
