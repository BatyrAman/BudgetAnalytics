"""Rate limiting (fixed window) with pluggable storage.

* ``memory`` — per-process counters. Only for development/tests: with several
  workers or replicas every process counts separately, so limits are
  multiplied (a bypass). Production settings refuse it.
* ``redis``  — shared counters; atomic INCR+EXPIRE in one Lua script.

Keys never contain raw personal data: identifiers (e-mails) are SHA-256 hashed.
Client IP is ``request.client.host`` — run uvicorn with ``--proxy-headers`` and
``--forwarded-allow-ips`` set to the reverse proxy ONLY, so clients cannot
spoof it with ``X-Forwarded-For``; the app never parses that header itself.

Failure policy when the backend is unreachable: auth endpoints fail CLOSED
(503 — no unlimited password guessing during an outage), others fail OPEN
(the request proceeds; an error is logged).

Fixed windows allow up to 2× the limit across a window boundary; limits are
chosen with that in mind.
"""

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass
from typing import Protocol

from app.core.errors import AppError

logger = logging.getLogger("budget.ratelimit")


class RateLimitedError(AppError):
    status_code = 429
    code = "too_many_requests"

    def __init__(self, retry_after: int) -> None:
        super().__init__("Too many requests, please try again later")
        self.headers = {"Retry-After": str(max(1, retry_after))}


class RateLimitUnavailableError(AppError):
    status_code = 503
    code = "service_unavailable"


@dataclass(frozen=True)
class Rule:
    name: str
    limit: int
    window_seconds: int
    fail_closed: bool = False


# Conservative defaults for a personal-finance API.
LOGIN_PER_IP = Rule("login_ip", 20, 60, fail_closed=True)
LOGIN_PER_ACCOUNT = Rule("login_account", 10, 15 * 60, fail_closed=True)
REGISTER_PER_IP = Rule("register_ip", 10, 60 * 60, fail_closed=True)
REFRESH_PER_IP = Rule("refresh_ip", 60, 60, fail_closed=True)
PASSWORD_CHANGE_PER_USER = Rule("password_change_user", 5, 60 * 60, fail_closed=True)
IMPORT_PER_USER = Rule("import_user", 30, 60 * 60)
ADVISOR_PER_USER = Rule("advisor_user", 30, 60 * 60)
API_PER_IP = Rule("api_ip", 600, 60)


class Backend(Protocol):
    async def hit(self, key: str, window_seconds: int) -> int:
        """Increment and return the counter of ``key`` for the current window."""
        ...

    async def ping(self) -> None: ...

    async def aclose(self) -> None: ...


class MemoryBackend:
    def __init__(self) -> None:
        self._counts: dict[str, tuple[int, float]] = {}
        self._lock = asyncio.Lock()

    async def hit(self, key: str, window_seconds: int) -> int:
        now = time.monotonic()
        async with self._lock:
            count, expires = self._counts.get(key, (0, now + window_seconds))
            if expires <= now:
                count, expires = 0, now + window_seconds
            count += 1
            self._counts[key] = (count, expires)
            if len(self._counts) > 100_000:  # bound memory: drop expired entries
                self._counts = {k: v for k, v in self._counts.items() if v[1] > now}
            return count

    async def ping(self) -> None:
        return None

    async def aclose(self) -> None:
        return None


_INCR_EXPIRE = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return count
"""


class RedisBackend:
    def __init__(self, url: str) -> None:
        import redis.asyncio as redis  # lazy: only needed when configured

        self._client = redis.from_url(url, socket_timeout=2, socket_connect_timeout=2)
        self._script = self._client.register_script(_INCR_EXPIRE)

    async def hit(self, key: str, window_seconds: int) -> int:
        return int(await self._script(keys=[key], args=[window_seconds]))

    async def ping(self) -> None:
        await self._client.ping()

    async def aclose(self) -> None:
        await self._client.aclose()


def hashed(identifier: str) -> str:
    return hashlib.sha256(identifier.strip().lower().encode()).hexdigest()[:32]


class RateLimiter:
    def __init__(self, backend: Backend, enabled: bool = True, prefix: str = "rl") -> None:
        self.backend = backend
        self.enabled = enabled
        self.prefix = prefix

    async def check(self, rule: Rule, identifier: str) -> None:
        if not self.enabled:
            return
        window = rule.window_seconds
        bucket = int(time.time() // window)
        key = f"{self.prefix}:{rule.name}:{identifier}:{bucket}"
        try:
            count = await self.backend.hit(key, window)
        except Exception as exc:
            logger.error(
                "rate limit backend unavailable",
                extra={"fields": {"rule": rule.name, "error_type": type(exc).__name__}},
            )
            if rule.fail_closed:
                raise RateLimitUnavailableError("Service temporarily unavailable") from None
            return
        if count > rule.limit:
            retry_after = window - int(time.time()) % window
            logger.warning("rate limit exceeded", extra={"fields": {"rule": rule.name}})
            raise RateLimitedError(retry_after)

    async def aclose(self) -> None:
        await self.backend.aclose()


_limiter: RateLimiter | None = None


def build_rate_limiter(backend_name: str, redis_url: str | None, enabled: bool) -> RateLimiter:
    backend: Backend = (
        RedisBackend(redis_url) if backend_name == "redis" and redis_url else MemoryBackend()
    )
    return RateLimiter(backend, enabled=enabled)


def get_rate_limiter() -> RateLimiter:
    """FastAPI dependency (overridden in tests)."""

    global _limiter
    if _limiter is None:
        from app.core.config import settings

        _limiter = build_rate_limiter(
            settings.RATE_LIMIT_BACKEND,
            settings.REDIS_URL.get_secret_value() if settings.REDIS_URL else None,
            settings.RATE_LIMIT_ENABLED,
        )
    return _limiter


async def close_rate_limiter() -> None:
    global _limiter
    if _limiter is not None:
        await _limiter.aclose()
    _limiter = None
