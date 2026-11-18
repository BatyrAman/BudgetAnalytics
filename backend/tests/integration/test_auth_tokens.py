"""Refresh rotation, reuse detection, logout, password policy."""

import httpx
import jwt
import pytest

from app.core.config import settings
from tests.integration.helpers import API, bearer, register_full

AUTH = f"{API}/auth"


async def test_refresh_rotates_and_old_token_is_rejected(client: httpx.AsyncClient) -> None:
    first = await register_full(client, "rot@example.com")
    second = (
        await client.post(f"{AUTH}/refresh", json={"refresh_token": first["refresh_token"]})
    ).json()
    assert second["refresh_token"] != first["refresh_token"]
    assert (
        await client.get(f"{AUTH}/me", headers=bearer(second["access_token"]))
    ).status_code == 200

    reused = await client.post(f"{AUTH}/refresh", json={"refresh_token": first["refresh_token"]})
    assert reused.status_code == 401


async def test_reuse_of_rotated_token_revokes_the_whole_family(client: httpx.AsyncClient) -> None:
    first = await register_full(client, "theft@example.com")
    second = (
        await client.post(f"{AUTH}/refresh", json={"refresh_token": first["refresh_token"]})
    ).json()

    # An attacker replays the stolen first token -> the legitimate newer token dies too.
    assert (
        await client.post(f"{AUTH}/refresh", json={"refresh_token": first["refresh_token"]})
    ).status_code == 401
    assert (
        await client.post(f"{AUTH}/refresh", json={"refresh_token": second["refresh_token"]})
    ).status_code == 401


async def test_logout_revokes_refresh_token_and_is_idempotent(client: httpx.AsyncClient) -> None:
    tokens = await register_full(client, "out@example.com")
    assert (
        await client.post(f"{AUTH}/logout", json={"refresh_token": tokens["refresh_token"]})
    ).status_code == 204
    assert (
        await client.post(f"{AUTH}/logout", json={"refresh_token": tokens["refresh_token"]})
    ).status_code == 204
    assert (
        await client.post(f"{AUTH}/refresh", json={"refresh_token": tokens["refresh_token"]})
    ).status_code == 401


async def test_logout_does_not_end_other_sessions(client: httpx.AsyncClient) -> None:
    await register_full(client, "multi@example.com")
    login = {"email": "multi@example.com", "password": "Pa55-word"}
    phone = (await client.post(f"{AUTH}/login", json=login)).json()
    laptop = (await client.post(f"{AUTH}/login", json=login)).json()
    await client.post(f"{AUTH}/logout", json={"refresh_token": phone["refresh_token"]})
    assert (
        await client.post(f"{AUTH}/refresh", json={"refresh_token": laptop["refresh_token"]})
    ).status_code == 200


async def test_logout_all_invalidates_access_and_refresh_tokens(client: httpx.AsyncClient) -> None:
    tokens = await register_full(client, "all@example.com")
    headers = bearer(tokens["access_token"])
    assert (await client.post(f"{AUTH}/logout-all", headers=headers)).status_code == 204
    assert (await client.get(f"{AUTH}/me", headers=headers)).status_code == 401
    assert (
        await client.post(f"{AUTH}/refresh", json={"refresh_token": tokens["refresh_token"]})
    ).status_code == 401


async def test_password_change_signs_out_everywhere(client: httpx.AsyncClient) -> None:
    tokens = await register_full(client, "pwchange@example.com", "Old-pass-1")
    headers = bearer(tokens["access_token"])
    response = await client.post(
        f"{AUTH}/change-password",
        headers=headers,
        json={"old_password": "Old-pass-1", "new_password": "New-pass-1"},
    )
    assert response.status_code == 200
    assert (await client.get(f"{AUTH}/me", headers=headers)).status_code == 401
    assert (
        await client.post(f"{AUTH}/refresh", json={"refresh_token": tokens["refresh_token"]})
    ).status_code == 401


async def test_refresh_token_without_jti_is_rejected(client: httpx.AsyncClient) -> None:
    # Tokens from before rotation existed carry no jti.
    await register_full(client, "legacy@example.com")
    from datetime import UTC, datetime, timedelta

    legacy = jwt.encode(
        {"sub": "1", "type": "refresh", "exp": datetime.now(UTC) + timedelta(days=1)},
        settings.SECRET_KEY.get_secret_value(),
        algorithm=settings.ALGORITHM,
    )
    assert (await client.post(f"{AUTH}/refresh", json={"refresh_token": legacy})).status_code == 401


@pytest.mark.parametrize("password", ["short1!", "x" * 129])
async def test_password_policy(client: httpx.AsyncClient, password: str) -> None:
    response = await client.post(
        f"{AUTH}/register", json={"full_name": "P", "email": "p@example.com", "password": password}
    )
    assert response.status_code == 422
    assert password not in response.text


async def test_email_is_case_insensitive(client: httpx.AsyncClient) -> None:
    await register_full(client, "Mixed.Case@Example.com")
    me_login = await client.post(
        f"{AUTH}/login", json={"email": "mixed.case@example.COM", "password": "Pa55-word"}
    )
    assert me_login.status_code == 200
    me = await client.get(f"{AUTH}/me", headers=bearer(me_login.json()["access_token"]))
    assert me.json()["email"] == "mixed.case@example.com"
    duplicate = await client.post(
        f"{AUTH}/register",
        json={"full_name": "D", "email": "MIXED.case@example.com", "password": "Pa55-word"},
    )
    assert duplicate.status_code == 409


async def test_responses_never_expose_password_hashes(client: httpx.AsyncClient) -> None:
    tokens = await register_full(client, "hash@example.com")
    me = await client.get(f"{AUTH}/me", headers=bearer(tokens["access_token"]))
    assert "hashed_password" not in me.text and "argon2" not in me.text
