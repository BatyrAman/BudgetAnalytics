"""Rate limiting, security headers and request size limits."""

import os
import time
from collections.abc import AsyncIterator, Iterator
from types import SimpleNamespace

import httpx
import pytest

from app.core import rate_limit
from app.core.config import settings
from app.core.rate_limit import (
    LOGIN_PER_ACCOUNT,
    MemoryBackend,
    RateLimiter,
    RedisBackend,
    Rule,
    get_rate_limiter,
)
from app.main import app, create_app
from tests.integration.helpers import API, bearer, register

REDIS_URL = os.environ.get("REDIS_TEST_URL")


# Wall-clock instant at the start of every rule window (divisible by 60, 900
# and 3600 s), so a test's requests can never straddle a window boundary.
FROZEN_WALL_CLOCK = 1_800_000_000.0


@pytest.fixture
def limiter(monkeypatch: pytest.MonkeyPatch) -> Iterator[RateLimiter]:
    # Fixed windows are keyed by ``time.time() // window``. Real time made the
    # per-IP login test flaky: 21 Argon2 logins take seconds, and crossing a
    # minute boundary reset the counter. Freeze the limiter's clock only (the
    # module's ``time`` binding), not the global ``time`` module.
    monkeypatch.setattr(
        rate_limit,
        "time",
        SimpleNamespace(time=lambda: FROZEN_WALL_CLOCK, monotonic=time.monotonic),
    )
    fresh = RateLimiter(MemoryBackend(), enabled=True)
    app.dependency_overrides[get_rate_limiter] = lambda: fresh
    yield fresh
    app.dependency_overrides.pop(get_rate_limiter, None)


async def _login(
    client: httpx.AsyncClient, email: str, password: str = "wrong-password"
) -> httpx.Response:
    return await client.post(f"{API}/auth/login", json={"email": email, "password": password})


class TestRateLimits:
    async def test_login_is_limited_per_account(
        self, client: httpx.AsyncClient, limiter: RateLimiter
    ) -> None:
        for _ in range(LOGIN_PER_ACCOUNT.limit):
            assert (await _login(client, "victim@example.com")).status_code == 401
        blocked = await _login(client, "VICTIM@example.com")  # case does not bypass the key
        assert blocked.status_code == 429
        assert blocked.json()["code"] == "too_many_requests"
        assert int(blocked.headers["Retry-After"]) >= 1
        # Even the correct password is refused while blocked (no oracle).
        assert (await _login(client, "victim@example.com", "Pa55-word")).status_code == 429
        # Other accounts are unaffected (per-IP limit not reached yet).
        assert (await _login(client, "someone.else@example.com")).status_code == 401

    async def test_login_is_limited_per_ip(
        self, client: httpx.AsyncClient, limiter: RateLimiter
    ) -> None:
        statuses = [(await _login(client, f"user{i}@example.com")).status_code for i in range(21)]
        assert statuses[:20] == [401] * 20 and statuses[20] == 429

    async def test_registration_is_limited_per_ip(
        self, client: httpx.AsyncClient, limiter: RateLimiter
    ) -> None:
        for i in range(10):
            await register(client, f"new{i}@example.com")
        response = await client.post(
            f"{API}/auth/register",
            json={"full_name": "X", "email": "x@example.com", "password": "Pa55-word"},
        )
        assert response.status_code == 429

    async def test_per_user_limit(self, client: httpx.AsyncClient, limiter: RateLimiter) -> None:
        headers = bearer(await register(client, "pw@example.com"))
        body = {"old_password": "wrong", "new_password": "New-pass-1"}
        statuses = [
            (
                await client.post(f"{API}/auth/change-password", headers=headers, json=body)
            ).status_code
            for _ in range(6)
        ]
        assert statuses == [400] * 5 + [429]

    async def test_auth_fails_closed_when_store_is_down(self, client: httpx.AsyncClient) -> None:
        class Broken(MemoryBackend):
            async def hit(self, key: str, window_seconds: int) -> int:
                raise ConnectionError("redis down")

        app.dependency_overrides[get_rate_limiter] = lambda: RateLimiter(Broken(), enabled=True)
        try:
            login = await _login(client, "a@example.com")
            assert login.status_code == 503  # no unlimited guessing during an outage
            health = await client.get("/health")
            assert health.status_code == 200
        finally:
            app.dependency_overrides.pop(get_rate_limiter, None)

    async def test_disabled_limiter_does_nothing(self, client: httpx.AsyncClient) -> None:
        app.dependency_overrides[get_rate_limiter] = lambda: RateLimiter(
            MemoryBackend(), enabled=False
        )
        try:
            statuses = {(await _login(client, "x@example.com")).status_code for _ in range(15)}
            assert statuses == {401}
        finally:
            app.dependency_overrides.pop(get_rate_limiter, None)


@pytest.mark.skipif(not REDIS_URL, reason="REDIS_TEST_URL is not set")
class TestRedisBackend:
    @pytest.fixture
    async def backends(self) -> AsyncIterator[tuple[RedisBackend, RedisBackend]]:
        first, second = RedisBackend(REDIS_URL or ""), RedisBackend(REDIS_URL or "")
        yield first, second
        await first.aclose()
        await second.aclose()

    async def test_counters_are_shared_between_workers(
        self, backends: tuple[RedisBackend, RedisBackend]
    ) -> None:
        import uuid

        rule = Rule(f"test-{uuid.uuid4().hex}", limit=3, window_seconds=60)
        worker_a, worker_b = RateLimiter(backends[0]), RateLimiter(backends[1])
        await worker_a.check(rule, "ip")
        await worker_b.check(rule, "ip")
        await worker_a.check(rule, "ip")
        with pytest.raises(Exception) as info:
            await worker_b.check(rule, "ip")  # 4th hit across both "processes"
        assert getattr(info.value, "status_code", None) == 429

    async def test_keys_expire_with_the_window(
        self, backends: tuple[RedisBackend, RedisBackend]
    ) -> None:
        import uuid

        key = f"rl:test:{uuid.uuid4().hex}"
        assert await backends[0].hit(key, 2) == 1
        assert await backends[1].hit(key, 2) == 2
        ttl = await backends[0]._client.ttl(key)
        assert 0 < ttl <= 2

    async def test_readiness_reports_redis(
        self, client: httpx.AsyncClient, backends: tuple[RedisBackend, RedisBackend]
    ) -> None:
        app.dependency_overrides[get_rate_limiter] = lambda: RateLimiter(backends[0])
        from app.api import health

        original = health.get_rate_limiter
        health.get_rate_limiter = lambda: RateLimiter(backends[0])  # type: ignore[assignment]
        try:
            body = (await client.get("/health/ready")).json()
            assert body["rate_limit_store"] == "ok"
        finally:
            health.get_rate_limiter = original  # type: ignore[assignment]
            app.dependency_overrides.pop(get_rate_limiter, None)


class TestHeadersAndLimits:
    async def test_security_headers(self, client: httpx.AsyncClient) -> None:
        response = await client.get(f"{API}/auth/me")
        h = response.headers
        assert h["x-content-type-options"] == "nosniff"
        assert h["x-frame-options"] == "DENY"
        assert h["referrer-policy"] == "no-referrer"
        assert h["cache-control"] == "no-store"
        assert "default-src 'none'" in h["content-security-policy"]
        assert "strict-transport-security" not in h  # only in production
        docs = await client.get("/docs")
        assert "content-security-policy" not in docs.headers  # docs need scripts (off in prod)

    async def test_hsts_in_production(self) -> None:
        prod = create_app(settings.model_copy(update={"ENVIRONMENT": "production"}))
        transport = httpx.ASGITransport(app=prod)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            response = await c.get("/health")
        assert response.headers["strict-transport-security"].startswith("max-age=31536000")
        # Docs are disabled in production.
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            assert (await c.get("/docs")).status_code == 404

    async def test_json_body_size_limit(self, client: httpx.AsyncClient) -> None:
        big = "x" * (settings.MAX_REQUEST_BYTES + 10)
        response = await client.post(
            f"{API}/auth/login", json={"email": "a@example.com", "password": big}
        )
        assert response.status_code == 413
        assert response.json()["code"] == "payload_too_large"

    async def test_chunked_body_without_content_length(self, client: httpx.AsyncClient) -> None:
        async def chunks():  # type: ignore[no-untyped-def]
            for _ in range(settings.MAX_REQUEST_BYTES // 65536 + 2):
                yield b"x" * 65536

        response = await client.post(
            f"{API}/auth/login", content=chunks(), headers={"content-type": "application/json"}
        )
        assert response.status_code == 413

    async def test_upload_paths_allow_statement_sized_bodies(
        self, client: httpx.AsyncClient
    ) -> None:
        headers = bearer(await register(client, "up@example.com"))
        size = settings.MAX_REQUEST_BYTES + 1024  # above the JSON limit, below the upload limit
        content = b"date;amount\n" + b"01.03.2025;-1,00\n" * (size // 17)
        response = await client.post(
            f"{API}/imports/kaspi/preview",
            headers=headers,
            files={"file": ("s.csv", content, "text/csv")},
        )
        assert response.status_code != 413
