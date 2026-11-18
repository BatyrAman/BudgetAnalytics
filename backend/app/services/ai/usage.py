"""AI token/cost accounting and limits.

* Cost (USD) = input_tokens × input_price / 1e6 + output_tokens × output_price / 1e6,
  with prices from configuration, rounded to 0.000001 USD (half up). Unknown
  when prices are not configured.
* Limits are checked BEFORE a call against usage already recorded plus a
  conservative estimate of the new call (prompt characters / 2 as input
  tokens — Cyrillic text uses more tokens per character than English — plus
  the maximum output tokens):
    - daily tokens per user (UTC day),
    - daily cost per user (UTC day),
    - monthly cost for all users (UTC calendar month).
  Concurrent requests can overshoot a limit by at most one call each.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.integrations.llm.base import TokenUsage
from app.models.ai_usage import AIUsage

_MILLION = Decimal(1_000_000)
_MICRO_USD = Decimal("0.000001")


def cost_usd(usage: TokenUsage, settings: Settings) -> Decimal | None:
    price_in = settings.AI_INPUT_PRICE_PER_1M_TOKENS_USD
    price_out = settings.AI_OUTPUT_PRICE_PER_1M_TOKENS_USD
    if price_in is None or price_out is None:
        return None
    cost = (
        Decimal(usage.input_tokens) * price_in / _MILLION
        + Decimal(usage.output_tokens) * price_out / _MILLION
    )
    return cost.quantize(_MICRO_USD, rounding=ROUND_HALF_UP)


def estimate_usage(prompt_chars: int, max_output_tokens: int) -> TokenUsage:
    return TokenUsage(input_tokens=prompt_chars // 2 + 1, output_tokens=max_output_tokens)


@dataclass(frozen=True)
class LimitDecision:
    allowed: bool
    reason: str | None = None


class AIUsageService:
    def __init__(self, db: AsyncSession, settings: Settings) -> None:
        self.db = db
        self.settings = settings

    async def record(
        self,
        *,
        user_id: int,
        feature: str,
        provider: str,
        model: str,
        prompt_version: str,
        outcome: str,
        usage: TokenUsage,
        latency_ms: int,
        request_id: str | None,
    ) -> AIUsage:
        row = AIUsage(
            user_id=user_id,
            feature=feature,
            provider=provider,
            model=model,
            prompt_version=prompt_version,
            outcome=outcome,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cost_usd=cost_usd(usage, self.settings),
            latency_ms=latency_ms,
            request_id=request_id,
        )
        self.db.add(row)
        await self.db.flush()
        return row

    async def check_limits(
        self, user_id: int, estimate: TokenUsage, now: datetime | None = None
    ) -> LimitDecision:
        now = now or datetime.now(UTC)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = day_start.replace(day=1)

        tokens_today, cost_today = (
            await self.db.execute(
                select(
                    func.coalesce(func.sum(AIUsage.input_tokens + AIUsage.output_tokens), 0),
                    func.coalesce(func.sum(AIUsage.cost_usd), 0),
                ).where(AIUsage.user_id == user_id, AIUsage.created_at >= day_start)
            )
        ).one()

        limit_tokens = self.settings.AI_DAILY_TOKEN_LIMIT_PER_USER
        if int(tokens_today) + estimate.total_tokens > limit_tokens:
            return LimitDecision(False, "daily_token_limit")

        estimated_cost = cost_usd(estimate, self.settings) or Decimal(0)
        user_cost_limit = self.settings.AI_DAILY_COST_LIMIT_PER_USER_USD
        if (
            user_cost_limit is not None
            and Decimal(cost_today or 0) + estimated_cost > user_cost_limit
        ):
            return LimitDecision(False, "daily_cost_limit")

        total_limit = self.settings.AI_MONTHLY_COST_LIMIT_TOTAL_USD
        if total_limit is not None:
            month_cost = await self.db.scalar(
                select(func.coalesce(func.sum(AIUsage.cost_usd), 0)).where(
                    AIUsage.created_at >= month_start
                )
            )
            if Decimal(month_cost or 0) + estimated_cost > total_limit:
                return LimitDecision(False, "monthly_cost_limit")

        return LimitDecision(True)
