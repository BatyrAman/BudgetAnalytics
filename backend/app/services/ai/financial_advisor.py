"""AI financial advisor use cases (provider-independent).

Flow for every request:
1. Build the verified fact sheet (deterministic services only, pseudonymized).
2. No LLM configured -> rules.  Limits exceeded -> rules (no provider call).
3. Call the LLM through ``LLMClient`` (timeouts, retries, metadata logging).
4. Validate JSON with Pydantic, then the grounding guard (fact ids + numbers).
   Any failure -> rules. Model output is never trusted.
5. Restore pseudonymized names, add server-side disclaimers, record usage.

Nothing here logs prompts, answers, questions or amounts.
"""

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.logging import request_id_var
from app.integrations.llm import (
    LLMCallFailed,
    LLMClient,
    LLMMessage,
    LLMRequest,
    TokenUsage,
    strict_json_schema,
)
from app.models.user import User
from app.schemas.advisor import AdvisorAnswer, AdvisorReport
from app.services.ai import fallback, guard, prompts
from app.services.ai.facts import FactSheet, FactSheetBuilder
from app.services.ai.usage import AIUsageService, estimate_usage
from app.services.finance import CurrencySpec

logger = logging.getLogger("budget.ai")

DISCLAIMER_GENERAL = (
    "Это информационный обзор на основе ваших данных, а не индивидуальная финансовая, "
    "налоговая или инвестиционная рекомендация. Решения вы принимаете самостоятельно."
)
DISCLAIMER_INVESTMENT = (
    "Инвестиции связаны с риском потери средств: доходность не гарантируется, а прошлые "
    "результаты не гарантируют будущих. Перед инвестированием оцените риски или обратитесь "
    "к лицензированному специалисту."
)
DISCLAIMER_ESTIMATES = (
    "Расчётные значения (например, доход по вкладу) — оценки при указанных допущениях, "
    "а не гарантированный результат; фактические условия банка могут отличаться."
)
_INVESTMENT_WORDS = re.compile(
    r"инвест|акци|облигац|etf|фонд|крипт|брокер|дивиденд|invest|stock|bond|crypto", re.IGNORECASE
)


@dataclass(frozen=True)
class AdvisorOutcome[T]:
    payload: T
    sheet: FactSheet
    generated_by: Literal["llm", "rules"]
    fallback_reason: str | None
    provider: str
    model: str
    disclaimers: list[str]


def _restore[M: BaseModel](model: M, pseudonyms: dict[str, str]) -> M:
    """Replace [CAT-1]-style tokens with the user's real names (server side)."""

    if not pseudonyms:
        return model
    text = model.model_dump_json()
    for token, name in pseudonyms.items():
        text = text.replace(token, json.dumps(name, ensure_ascii=False)[1:-1])
    return type(model).model_validate_json(text)


class FinancialAdvisor:
    def __init__(self, db: AsyncSession, settings: Settings, client: LLMClient | None) -> None:
        self.db = db
        self.settings = settings
        self.client = client
        self.usage = AIUsageService(db, settings)

    async def report(
        self, user: User, currency: CurrencySpec, tz: ZoneInfo
    ) -> AdvisorOutcome[AdvisorReport]:
        sheet = await FactSheetBuilder(self.db).build(user, currency, tz, datetime.now(tz).date())
        messages = (
            LLMMessage("system", prompts.SYSTEM_PROMPT),
            LLMMessage("user", prompts.data_message(sheet)),
            LLMMessage("user", prompts.REPORT_TASK),
        )
        result, reason = await self._run(
            user, sheet, messages, AdvisorReport, "report", guard.check_report
        )
        payload = result or fallback.build_report(sheet)
        investment = any(r.involves_investment for r in payload.recommendations)
        return self._outcome(payload, sheet, reason, investment)

    async def ask(
        self, user: User, question: str, currency: CurrencySpec, tz: ZoneInfo
    ) -> AdvisorOutcome[AdvisorAnswer]:
        sheet = await FactSheetBuilder(self.db).build(user, currency, tz, datetime.now(tz).date())
        clean_question = prompts.redact_question(question)
        messages = (
            LLMMessage("system", prompts.SYSTEM_PROMPT),
            LLMMessage("user", prompts.data_message(sheet)),
            LLMMessage(
                "user", prompts.QUESTION_TASK + "\nВОПРОС ПОЛЬЗОВАТЕЛЯ (данные):\n" + clean_question
            ),
        )
        result, reason = await self._run(
            user, sheet, messages, AdvisorAnswer, "question", guard.check_answer
        )
        payload = result or fallback.build_answer(sheet)
        investment = payload.involves_investment or bool(_INVESTMENT_WORDS.search(question))
        return self._outcome(payload, sheet, reason, investment)

    # ------------------------------------------------------------ internals
    def _outcome(self, payload, sheet, reason, investment):
        disclaimers = [DISCLAIMER_GENERAL]
        if investment:
            disclaimers.append(DISCLAIMER_INVESTMENT)
        if any(f.topic == "deposit" for f in sheet.facts):
            disclaimers.append(DISCLAIMER_ESTIMATES)
        return AdvisorOutcome(
            payload=_restore(payload, sheet.pseudonyms),
            sheet=sheet,
            generated_by="rules" if reason else "llm",
            fallback_reason=reason,
            provider=self.client.provider_name if self.client else "none",
            model=self.client.model if self.client else "rules",
            disclaimers=disclaimers,
        )

    async def _record(
        self, user: User, feature: str, outcome: str, usage: TokenUsage, latency_ms: int
    ) -> None:
        await self.usage.record(
            user_id=user.id,
            feature=feature,
            provider=self.client.provider_name if self.client else "none",
            model=self.client.model if self.client else "rules",
            prompt_version=prompts.PROMPT_VERSION,
            outcome=outcome,
            usage=usage,
            latency_ms=latency_ms,
            request_id=request_id_var.get(),
        )

    async def _run(self, user, sheet, messages, schema: type[BaseModel], feature: str, check):  # noqa: E501
        """Returns (validated model or None, fallback reason or None)."""

        if self.client is None:
            await self._record(user, feature, "disabled", TokenUsage(), 0)
            return None, "disabled"

        estimate = estimate_usage(
            sum(len(m.content) for m in messages), self.settings.AI_MAX_OUTPUT_TOKENS
        )
        decision = await self.usage.check_limits(user.id, estimate)
        if not decision.allowed:
            logger.info(
                "ai limit reached", extra={"fields": {"feature": feature, "limit": decision.reason}}
            )
            await self._record(user, feature, "limited", TokenUsage(), 0)
            return None, "limit_reached"

        request = LLMRequest(
            messages=messages,
            response_schema=strict_json_schema(schema),
            schema_name=schema.__name__,
            max_output_tokens=self.settings.AI_MAX_OUTPUT_TOKENS,
            temperature=self.settings.AI_TEMPERATURE,
        )
        try:
            result = await self.client.generate(request, feature)
        except LLMCallFailed as failed:
            await self._record(user, feature, "fallback_error", failed.usage, failed.latency_ms)
            return None, "provider_error"

        try:
            parsed = schema.model_validate_json(result.response.content)
            check(parsed, sheet)
        except (ValidationError, guard.GuardViolation) as exc:
            logger.warning(
                "ai output rejected",
                extra={"fields": {"feature": feature, "error_type": type(exc).__name__}},
            )
            await self._record(user, feature, "fallback_invalid", result.usage, result.latency_ms)
            return None, "invalid_output"

        await self._record(user, feature, "success", result.usage, result.latency_ms)
        return parsed, None


__all__ = ["DISCLAIMER_GENERAL", "DISCLAIMER_INVESTMENT", "FinancialAdvisor"]
