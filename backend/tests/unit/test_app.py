"""App-level tests that need no database."""

import httpx
import pytest

from app.core import database
from app.main import app, create_app

EXPECTED_ROUTER_PREFIXES = [
    "/api/v1/auth",
    "/api/v1/banks",
    "/api/v1/goals",
    "/api/v1/transactions",
    "/api/v1/budgets",
    "/api/v1/investments",
    "/api/v1/dashboard",
    "/api/v1/analytics",
    "/api/v1/upload",
]


def test_all_routers_are_registered_under_api_v1() -> None:
    paths = set(app.openapi()["paths"])
    for prefix in EXPECTED_ROUTER_PREFIXES:
        assert any(p.startswith(prefix) for p in paths), prefix
    assert "/health" in paths
    assert "/health/ready" in paths


async def test_liveness(client: httpx.AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert response.headers["X-Request-ID"]


async def test_readiness_reports_unavailable_database(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def unavailable() -> None:
        raise ConnectionRefusedError("db down")

    monkeypatch.setattr(database, "check_database_connection", unavailable)
    response = await client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "database": "unavailable",
        "rate_limit_store": "not_used",
    }


async def test_client_request_id_is_propagated(client: httpx.AsyncClient) -> None:
    response = await client.get("/health", headers={"X-Request-ID": "abc-123"})
    assert response.headers["X-Request-ID"] == "abc-123"


async def test_unsafe_client_request_id_is_replaced(client: httpx.AsyncClient) -> None:
    response = await client.get("/health", headers={"X-Request-ID": "bad id\n<script>"})
    assert response.headers["X-Request-ID"] != "bad id\n<script>"


async def test_unauthenticated_request_uses_error_schema(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401
    body = response.json()
    assert body["code"] == "unauthorized"
    assert body["detail"] == "Could not validate credentials"
    assert body["request_id"] == response.headers["X-Request-ID"]
    assert response.headers.get_list("X-Request-ID") == [body["request_id"]]
    assert response.headers["WWW-Authenticate"] == "Bearer"


async def test_not_found_uses_error_schema(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


async def test_validation_error_does_not_echo_input(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/login", json={"email": "not-an-email", "password": "TopSecret-Pa55"}
    )
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"
    assert body["detail"][0]["loc"] == ["body", "email"]
    assert "TopSecret-Pa55" not in response.text
    assert "not-an-email" not in response.text


async def test_unhandled_exception_returns_generic_500() -> None:
    test_app = create_app()

    @test_app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("internal detail that must not leak")

    transport = httpx.ASGITransport(app=test_app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        response = await c.get("/boom")

    assert response.status_code == 500
    body = response.json()
    assert body == {
        "detail": "Internal server error",
        "code": "internal_error",
        "request_id": body["request_id"],
    }
    assert body["request_id"]
    assert "internal detail" not in response.text


def test_openapi_schema_builds() -> None:
    schema = app.openapi()
    assert schema["info"]["title"]
    assert "/api/v1/auth/login" in schema["paths"]


async def test_cors_for_configured_frontend_origin() -> None:
    from tests.unit.test_config import make

    cors_app = create_app(make(CORS_ORIGINS=["http://localhost:3000"]))
    transport = httpx.ASGITransport(app=cors_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        preflight = await c.options(
            "/api/v1/transactions",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
        assert preflight.status_code == 200
        assert preflight.headers["access-control-allow-origin"] == "http://localhost:3000"
        assert "access-control-allow-credentials" not in preflight.headers  # bearer, no cookies

        simple = await c.get("/health", headers={"Origin": "http://localhost:3000"})
        exposed = simple.headers["access-control-expose-headers"].lower()
        assert "x-request-id" in exposed and "retry-after" in exposed

        foreign = await c.options(
            "/api/v1/transactions",
            headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"},
        )
        assert "access-control-allow-origin" not in foreign.headers
