"""AI financial advisor endpoints.

Responses always include the verified ``facts`` the advice is based on,
whether the text came from the LLM or from deterministic rules, and
server-side disclaimers. Numbers in the advice are guaranteed (by a server
check) to be values from ``facts``.
"""

from dataclasses import replace
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_currency,
    get_current_active_user,
    get_db,
    get_timezone,
    limit_per_user,
)
from app.core.config import settings
from app.core.errors import ErrorResponse
from app.core.rate_limit import ADVISOR_PER_USER
from app.integrations.llm import LLMClient, build_llm_client
from app.models.user import User
from app.schemas.advisor import AdvisorAnswerResponse, AdvisorReportResponse, AskRequest, FactOut
from app.services.ai.financial_advisor import AdvisorOutcome, FinancialAdvisor
from app.services.ai.prompts import PROMPT_VERSION
from app.services.finance import CurrencySpec

router = APIRouter(prefix="/advisor", tags=["AI Advisor"])

_client: LLMClient | None = None
_client_built = False


def get_llm_client() -> LLMClient | None:
    """Process-wide client built from settings (``None`` when AI_PROVIDER=none).
    Overridden in tests with mocked providers."""

    global _client, _client_built
    if not _client_built:
        _client = build_llm_client(settings)
        _client_built = True
    return _client


async def close_llm_client() -> None:
    global _client, _client_built
    if _client is not None:
        await _client.aclose()
    _client, _client_built = None, False


def _meta(outcome: AdvisorOutcome, currency: CurrencySpec) -> dict:
    return {
        "generated_by": outcome.generated_by,
        "fallback_reason": outcome.fallback_reason,
        "provider": outcome.provider,
        "model": outcome.model,
        "prompt_version": PROMPT_VERSION,
        "currency_code": currency.code,
        "as_of": outcome.sheet.as_of,
        "facts": [FactOut(**f.__dict__) for f in _restored_facts(outcome)],
        "disclaimers": outcome.disclaimers,
    }


def _restored_facts(outcome: AdvisorOutcome):
    restored = []
    for fact in outcome.sheet.facts:
        label = fact.label
        for token, name in outcome.sheet.pseudonyms.items():
            label = label.replace(token, name)
        restored.append(replace(fact, label=label))
    return restored


_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}


@router.post(
    "/insights",
    response_model=AdvisorReportResponse,
    responses=_ERRORS,
    dependencies=[Depends(limit_per_user(ADVISOR_PER_USER))],
)
async def get_insights(
    tz: ZoneInfo = Depends(get_timezone),
    currency: CurrencySpec = Depends(get_currency),
    current_user: User = Depends(get_current_active_user),
    client: LLMClient | None = Depends(get_llm_client),
    db: AsyncSession = Depends(get_db),
) -> AdvisorReportResponse:
    """Summary, spending and savings insights, budget suggestions and risks."""

    outcome = await FinancialAdvisor(db, settings, client).report(current_user, currency, tz)
    await db.commit()
    return AdvisorReportResponse(**_meta(outcome, currency), report=outcome.payload)


@router.post(
    "/ask",
    response_model=AdvisorAnswerResponse,
    responses=_ERRORS,
    dependencies=[Depends(limit_per_user(ADVISOR_PER_USER))],
)
async def ask(
    payload: AskRequest,
    tz: ZoneInfo = Depends(get_timezone),
    currency: CurrencySpec = Depends(get_currency),
    current_user: User = Depends(get_current_active_user),
    client: LLMClient | None = Depends(get_llm_client),
    db: AsyncSession = Depends(get_db),
) -> AdvisorAnswerResponse:
    """Answer a financial question using only the user's verified data.
    E-mails, phone numbers, card numbers and IINs are removed from the
    question before it is sent to the AI provider."""

    outcome = await FinancialAdvisor(db, settings, client).ask(
        current_user, payload.question, currency, tz
    )
    await db.commit()
    return AdvisorAnswerResponse(**_meta(outcome, currency), answer=outcome.payload)
