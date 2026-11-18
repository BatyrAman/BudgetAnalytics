"""Resilience and observability around any ``LLMProvider``.

* Overall timeout per attempt (``asyncio.timeout``), in addition to the
  provider's own HTTP timeout.
* Bounded retries with exponential backoff and full jitter, only for errors
  marked ``retryable`` (timeouts, rate limits, 5xx/network).
* One structured log line per attempt with METADATA ONLY: provider, model,
  feature, attempt, latency, token counts, outcome, error type. Never prompts,
  answers, questions, amounts or keys.
"""

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.integrations.llm.base import (
    LLMError,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    LLMTimeoutError,
    TokenUsage,
)

logger = logging.getLogger("budget.ai")


@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int = 2
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 8.0

    def delay(self, attempt: int) -> float:
        """Full-jitter exponential backoff for retry number ``attempt`` (1-based)."""

        cap = min(self.max_delay_seconds, self.base_delay_seconds * 2 ** (attempt - 1))
        return random.uniform(0, cap)  # noqa: S311 - jitter, not cryptography


@dataclass(frozen=True)
class LLMResult:
    response: LLMResponse
    attempts: int
    latency_ms: int
    usage: TokenUsage  # summed over all attempts that reported usage


class LLMCallFailed(Exception):
    def __init__(self, error: LLMError, attempts: int, latency_ms: int, usage: TokenUsage) -> None:
        super().__init__(str(error))
        self.error = error
        self.attempts = attempts
        self.latency_ms = latency_ms
        self.usage = usage


class LLMClient:
    def __init__(
        self,
        provider: LLMProvider,
        timeout_seconds: float,
        retry: RetryPolicy,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.provider = provider
        self.timeout_seconds = timeout_seconds
        self.retry = retry
        self._sleep = sleep

    @property
    def provider_name(self) -> str:
        return self.provider.name

    @property
    def model(self) -> str:
        return self.provider.model

    async def generate(self, request: LLMRequest, feature: str) -> LLMResult:
        started = time.perf_counter()
        input_tokens = output_tokens = 0
        attempt = 0
        while True:
            attempt += 1
            attempt_started = time.perf_counter()
            try:
                async with asyncio.timeout(self.timeout_seconds):
                    response = await self.provider.generate(request)
            except TimeoutError:
                error: LLMError = LLMTimeoutError("LLM call exceeded the configured timeout")
            except LLMError as exc:
                error = exc
            else:
                input_tokens += response.usage.input_tokens
                output_tokens += response.usage.output_tokens
                self._log(feature, attempt, attempt_started, "success", response.usage)
                return LLMResult(
                    response=response,
                    attempts=attempt,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    usage=TokenUsage(input_tokens, output_tokens),
                )

            input_tokens += error.usage.input_tokens
            output_tokens += error.usage.output_tokens
            will_retry = error.retryable and attempt <= self.retry.max_retries
            self._log(
                feature,
                attempt,
                attempt_started,
                "retry" if will_retry else "error",
                error.usage,
                error,
            )
            if not will_retry:
                raise LLMCallFailed(
                    error,
                    attempts=attempt,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    usage=TokenUsage(input_tokens, output_tokens),
                )
            await self._sleep(self.retry.delay(attempt))

    def _log(
        self,
        feature: str,
        attempt: int,
        started: float,
        outcome: str,
        usage: TokenUsage,
        error: LLMError | None = None,
    ) -> None:
        fields = {
            "provider": self.provider.name,
            "model": self.provider.model,
            "feature": feature,
            "attempt": attempt,
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "outcome": outcome,
        }
        if error is not None:
            fields["error_type"] = type(error).__name__
        level = logging.INFO if outcome == "success" else logging.WARNING
        logger.log(level, "llm call", extra={"fields": fields})

    async def aclose(self) -> None:
        await self.provider.aclose()
