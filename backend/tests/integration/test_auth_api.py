import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.helpers import bearer, register

AUTH = "/api/v1/auth"


async def test_register_login_me_refresh_flow(client: httpx.AsyncClient) -> None:
    access = await register(client, "flow@example.com", "Sm0ke-pass")

    me = await client.get(f"{AUTH}/me", headers=bearer(access))
    assert me.status_code == 200
    body = me.json()
    assert body["email"] == "flow@example.com"
    assert "hashed_password" not in body

    login = await client.post(
        f"{AUTH}/login", json={"email": "flow@example.com", "password": "Sm0ke-pass"}
    )
    assert login.status_code == 200
    tokens = login.json()

    refreshed = await client.post(
        f"{AUTH}/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"]


async def test_duplicate_email_is_rejected(client: httpx.AsyncClient) -> None:
    await register(client, "dup@example.com")
    response = await client.post(
        f"{AUTH}/register",
        json={"full_name": "Other", "email": "dup@example.com", "password": "Another-pass-1"},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "email_taken"


async def test_wrong_password_and_unknown_email_look_the_same(client: httpx.AsyncClient) -> None:
    await register(client, "user@example.com", "Correct-1")
    wrong = await client.post(f"{AUTH}/login", json={"email": "user@example.com", "password": "x"})
    unknown = await client.post(
        f"{AUTH}/login", json={"email": "nobody@example.com", "password": "x"}
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["detail"] == unknown.json()["detail"]


async def test_refresh_token_cannot_be_used_as_access_and_vice_versa(
    client: httpx.AsyncClient,
) -> None:
    await register(client, "types@example.com", "Correct-1")
    tokens = (
        await client.post(
            f"{AUTH}/login", json={"email": "types@example.com", "password": "Correct-1"}
        )
    ).json()

    assert (
        await client.get(f"{AUTH}/me", headers=bearer(tokens["refresh_token"]))
    ).status_code == 401
    assert (
        await client.post(f"{AUTH}/refresh", json={"refresh_token": tokens["access_token"]})
    ).status_code == 401


async def test_change_password(client: httpx.AsyncClient) -> None:
    access = await register(client, "pw@example.com", "Old-pass-1")

    bad = await client.post(
        f"{AUTH}/change-password",
        headers=bearer(access),
        json={"old_password": "wrong", "new_password": "New-pass-1"},
    )
    assert bad.status_code == 400

    ok = await client.post(
        f"{AUTH}/change-password",
        headers=bearer(access),
        json={"old_password": "Old-pass-1", "new_password": "New-pass-1"},
    )
    assert ok.status_code == 200

    old_login = await client.post(
        f"{AUTH}/login", json={"email": "pw@example.com", "password": "Old-pass-1"}
    )
    new_login = await client.post(
        f"{AUTH}/login", json={"email": "pw@example.com", "password": "New-pass-1"}
    )
    assert old_login.status_code == 401
    assert new_login.status_code == 200


async def test_token_of_deleted_user_is_rejected(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    access = await register(client, "gone@example.com")
    await db_session.execute(text("DELETE FROM users WHERE email = 'gone@example.com'"))
    await db_session.commit()

    assert (await client.get(f"{AUTH}/me", headers=bearer(access))).status_code == 401
