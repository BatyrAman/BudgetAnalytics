"""OAuth2 password flow endpoint used by Swagger UI's Authorize button."""

import httpx

from app.core.rate_limit import LOGIN_PER_ACCOUNT, RateLimiter
from app.main import app
from tests.integration.helpers import API, bearer, register
from tests.integration.test_hardening import limiter  # noqa: F401 - shared fixture

PASSWORD = "Pa55-word"


async def _token(client: httpx.AsyncClient, username: str, password: str) -> httpx.Response:
    # Exactly what Swagger UI sends: form-encoded, grant_type=password.
    return await client.post(
        f"{API}/auth/token",
        data={"grant_type": "password", "username": username, "password": password},
    )


def test_openapi_points_swagger_at_the_form_endpoint() -> None:
    schemes = app.openapi()["components"]["securitySchemes"]
    flow = schemes["OAuth2PasswordBearer"]["flows"]["password"]
    assert flow["tokenUrl"] == f"{API}/auth/token"
    body = app.openapi()["paths"][f"{API}/auth/token"]["post"]["requestBody"]["content"]
    assert "application/x-www-form-urlencoded" in body
    # The JSON login used by applications is unchanged.
    login = app.openapi()["paths"][f"{API}/auth/login"]["post"]["requestBody"]["content"]
    assert list(login) == ["application/json"]


async def test_form_token_can_access_protected_endpoint(client: httpx.AsyncClient) -> None:
    await register(client, "swagger@example.com", PASSWORD)
    response = await _token(client, "Swagger@Example.com", PASSWORD)  # e-mail is normalised
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["token_type"] == "bearer"
    assert {"access_token", "refresh_token"} <= body.keys()

    me = await client.get(f"{API}/auth/me", headers=bearer(body["access_token"]))
    assert (me.status_code, me.json()["email"]) == (200, "swagger@example.com")
    assert (await client.get(f"{API}/auth/me")).status_code == 401


async def test_wrong_credentials_and_bad_requests(client: httpx.AsyncClient) -> None:
    await register(client, "swagger@example.com", PASSWORD)
    wrong = await _token(client, "swagger@example.com", "Wrong-pass1")
    unknown = await _token(client, "nobody@example.com", PASSWORD)
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["detail"] == unknown.json()["detail"]  # no account enumeration

    not_email = await _token(client, "not-an-email", "Secret-Value-77")
    assert not_email.status_code == 422
    assert "Secret-Value-77" not in not_email.text  # input is never echoed

    too_long = await _token(client, "swagger@example.com", "x" * 10_000)
    assert too_long.status_code == 422  # same password length cap as /login

    as_json = await client.post(
        f"{API}/auth/token", json={"username": "swagger@example.com", "password": PASSWORD}
    )
    assert as_json.status_code == 422


async def test_shares_the_per_account_limit_with_json_login(
    client: httpx.AsyncClient,
    limiter: RateLimiter,  # noqa: F811 - frozen-clock limiter from test_hardening
) -> None:
    for i in range(LOGIN_PER_ACCOUNT.limit):
        if i % 2:
            r = await _token(client, "victim@example.com", "wrong-password")
        else:
            r = await client.post(
                f"{API}/auth/login",
                json={"email": "victim@example.com", "password": "wrong-password"},
            )
        assert r.status_code == 401
    # Switching endpoints does not reset the counter.
    assert (await _token(client, "victim@example.com", "wrong-password")).status_code == 429
