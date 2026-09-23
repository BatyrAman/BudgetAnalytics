"""
Простой in-memory rate limiter (скользящее окно) для /auth/login и /upload.

Работает в пределах одного процесса. При горизонтальном
масштабировании заменить хранилище на Redis — интерфейс
зависимости останется тем же.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque

from fastapi import Request

from app.core.config import settings
from app.core.errors import RateLimitError


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def hit(self, key: str, limit: int, window_seconds: float = 60.0) -> bool:
        now = time.monotonic()
        async with self._lock:
            bucket = self._hits[key]
            while bucket and now - bucket[0] >= window_seconds:
                bucket.popleft()
            if len(bucket) >= limit:
                return False
            bucket.append(now)
            return True

    def reset(self) -> None:
        self._hits.clear()


limiter = SlidingWindowLimiter()


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def rate_limit(scope: str, per_minute_setting: str):
    async def dependency(request: Request) -> None:
        if not settings.RATE_LIMIT_ENABLED:
            return
        limit = getattr(settings, per_minute_setting)
        allowed = await limiter.hit(f"{scope}:{_client_key(request)}", limit)
        if not allowed:
            raise RateLimitError(
                "Too many requests, try again later",
                details={"scope": scope, "limit_per_minute": limit},
            )

    return dependency
