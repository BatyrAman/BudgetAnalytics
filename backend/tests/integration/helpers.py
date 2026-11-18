from typing import Any

import httpx

API = "/api/v1"


async def register(client: httpx.AsyncClient, email: str, password: str = "Pa55-word") -> str:
    """Register a user and return its access token."""

    response = await client.post(
        f"{API}/auth/register",
        json={"full_name": "Test User", "email": email, "password": password},
    )
    assert response.status_code == 201, response.text
    return response.json()["access_token"]


async def register_full(
    client: httpx.AsyncClient, email: str, password: str = "Pa55-word"
) -> dict[str, str]:
    response = await client.post(
        f"{API}/auth/register",
        json={"full_name": "Test User", "email": email, "password": password},
    )
    assert response.status_code == 201, response.text
    return response.json()


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def create(
    client: httpx.AsyncClient, path: str, headers: dict[str, str], body: dict[str, Any]
) -> dict[str, Any]:
    response = await client.post(f"{API}{path}", headers=headers, json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def category(client: httpx.AsyncClient, headers: dict[str, str], name: str) -> int:
    return (await create(client, "/categories", headers, {"name": name}))["id"]


async def tx(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    category_id: int,
    amount: str,
    kind: str,
    when: str,
    **extra: Any,
) -> dict[str, Any]:
    body = {
        "amount": amount,
        "transaction_type": kind,
        "transaction_date": when,
        "category_id": category_id,
        **extra,
    }
    return await create(client, "/transactions", headers, body)
