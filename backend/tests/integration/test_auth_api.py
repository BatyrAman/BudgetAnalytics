import jwt
import pytest

from app.core.config import settings
from tests.integration.conftest import API, register

pytestmark = pytest.mark.integration

COOKIE = settings.REFRESH_COOKIE_NAME


async def _login(client, email, password):
    return await client.post(f"{API}/auth/login", json={"email": email, "password": password})


async def test_register_sets_httponly_refresh_cookie(client):
    response = await client.post(
        f"{API}/auth/register",
        json={"full_name": "Test", "email": "Cookie@Example.com", "password": "Str0ng-password!"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["refresh_token"] is None  # не в теле
    assert abs(body["expires_in"] - settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60) <= 2
    set_cookie = response.headers["set-cookie"]
    assert f"{COOKIE}=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=strict" in set_cookie
    assert f"Path={API}/auth" in set_cookie


async def test_access_token_claims(alice):
    claims = jwt.decode(alice.token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    assert claims["type"] == "access"
    assert {"sub", "exp", "iat", "jti", "ver"} <= claims.keys()
    assert claims["exp"] - claims["iat"] == settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60


async def test_login_is_case_insensitive_and_errors_are_uniform(client, alice):
    ok = await _login(client, alice.email.upper(), alice.password)
    assert ok.status_code == 200
    wrong_password = await _login(client, alice.email, "wrong-password")
    unknown = await _login(client, "nobody@example.com", "wrong-password")
    assert wrong_password.status_code == unknown.status_code == 401
    assert wrong_password.json() == unknown.json()


async def test_duplicate_email(client, alice):
    response = await client.post(
        f"{API}/auth/register", json={"full_name": "X", "email": alice.email.upper(), "password": "Another-pass1"}
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EMAIL_TAKEN"


@pytest.mark.parametrize("password", ["short", "x" * 73])
async def test_password_policy(client, password):
    response = await client.post(
        f"{API}/auth/register", json={"full_name": "X", "email": "p@example.com", "password": password}
    )
    assert response.status_code == 422
    assert password not in response.text  # значение не отражается в ошибке


async def test_refresh_rotation_and_reuse_detection(client, alice):
    login = await _login(client, alice.email, alice.password)
    first_refresh = login.cookies[COOKIE]

    rotated = await client.post(f"{API}/auth/refresh")
    assert rotated.status_code == 200, rotated.text
    second_refresh = rotated.cookies[COOKIE]
    assert second_refresh != first_refresh
    assert rotated.json()["access_token"]

    # повторное использование старого токена → вся семья отозвана
    client.cookies.set(COOKIE, first_refresh, path=f"{API}/auth")
    reused = await client.post(f"{API}/auth/refresh")
    assert reused.status_code == 401
    assert reused.json()["error"]["code"] == "REFRESH_TOKEN_REUSED"

    client.cookies.set(COOKIE, second_refresh, path=f"{API}/auth")
    after = await client.post(f"{API}/auth/refresh")
    assert after.status_code == 401


async def test_refresh_requires_cookie_and_rejects_access_token(client, alice):
    client.cookies.clear()
    assert (await client.post(f"{API}/auth/refresh")).status_code == 401
    client.cookies.set(COOKIE, alice.token, path=f"{API}/auth")
    assert (await client.post(f"{API}/auth/refresh")).status_code == 401
    # refresh в теле игнорируется вне legacy-режима
    client.cookies.clear()
    login = await _login(client, alice.email, alice.password)
    token = login.cookies[COOKIE]
    client.cookies.clear()
    assert (await client.post(f"{API}/auth/refresh", json={"refresh_token": token})).status_code == 401


async def test_legacy_body_mode(client, alice, monkeypatch):
    monkeypatch.setattr(settings, "REFRESH_TOKEN_IN_BODY", True)
    login = (await _login(client, alice.email, alice.password)).json()
    assert login["refresh_token"]
    client.cookies.clear()
    refreshed = await client.post(f"{API}/auth/refresh", json={"refresh_token": login["refresh_token"]})
    assert refreshed.status_code == 200


async def test_foreign_origin_is_rejected_for_cookie_endpoints(client, alice):
    await _login(client, alice.email, alice.password)
    evil = await client.post(f"{API}/auth/refresh", headers={"Origin": "https://evil.example"})
    assert evil.status_code == 403
    assert evil.json()["error"]["code"] == "ORIGIN_NOT_ALLOWED"
    good = await client.post(f"{API}/auth/refresh", headers={"Origin": settings.cors_origins[0]})
    assert good.status_code == 200


async def test_logout_revokes_refresh(client, alice):
    await _login(client, alice.email, alice.password)
    token = client.cookies[COOKIE]
    assert (await client.post(f"{API}/auth/logout")).status_code == 204
    client.cookies.set(COOKIE, token, path=f"{API}/auth")
    assert (await client.post(f"{API}/auth/refresh")).status_code == 401


async def test_logout_all_revokes_access_tokens(client, alice):
    assert (await alice.get("/auth/me")).status_code == 200
    assert (await alice.post("/auth/logout-all")).status_code == 204
    assert (await alice.get("/auth/me")).status_code == 401


async def test_change_password(client, alice):
    response = await alice.post(
        "/auth/change-password", json={"old_password": alice.password, "new_password": "New-password-123"}
    )
    assert response.status_code == 200
    assert (await alice.get("/auth/me")).status_code == 401  # старый access отозван
    assert (await _login(client, alice.email, alice.password)).status_code == 401
    assert (await _login(client, alice.email, "New-password-123")).status_code == 200

    wrong = await (await register(client)).post(
        "/auth/change-password", json={"old_password": "nope-nope", "new_password": "New-password-123"}
    )
    assert wrong.status_code == 400


async def test_tampered_and_expired_tokens(client, alice):
    header, payload, signature = alice.token.split(".")
    tampered = f"{header}.{payload}.{signature[::-1]}"
    assert (await client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {tampered}"})).status_code == 401

    import datetime as dt

    expired = jwt.encode(
        {"sub": str(alice.id), "type": "access", "ver": 0, "jti": "x",
         "iat": dt.datetime(2020, 1, 1), "exp": dt.datetime(2020, 1, 2)},
        settings.SECRET_KEY, algorithm=settings.ALGORITHM,
    )
    assert (await client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {expired}"})).status_code == 401

    none_alg = jwt.encode({"sub": str(alice.id), "type": "access"}, key=None, algorithm="none")
    assert (await client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {none_alg}"})).status_code == 401


async def test_delete_account_removes_all_data(client, alice, kaspi_id, session):
    from sqlalchemy import text

    await alice.post("/cards", json={"bank_id": kaspi_id, "last4": "1234"})
    await alice.post("/upload/kaspi", files={"file": ("s.csv", b"date,description,amount\n2025-01-01,x,-1\n", "text/csv")})
    wrong = await alice.client.request("DELETE", f"{API}/auth/me", headers=alice.headers, json={"password": "bad-password"})
    assert wrong.status_code == 400
    response = await alice.client.request("DELETE", f"{API}/auth/me", headers=alice.headers, json={"password": alice.password})
    assert response.status_code == 204
    for table in ("transactions", "cards", "statement_imports", "refresh_tokens"):
        count = await session.scalar(text(f"SELECT count(*) FROM {table} WHERE user_id = :u"), {"u": alice.id})
        assert count == 0, table


async def test_login_rate_limit(client, alice, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "LOGIN_RATE_LIMIT_PER_MINUTE", 3)
    codes = [(await _login(client, alice.email, "bad-password")).status_code for _ in range(4)]
    assert codes == [401, 401, 401, 429]
