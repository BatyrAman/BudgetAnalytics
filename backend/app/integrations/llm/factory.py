"""Builds the configured LLM client. The rest of the app depends on this
function (via FastAPI DI), never on a concrete provider.

Implemented providers: ``openai``. ``AI_PROVIDER=none`` disables the LLM
(advisor answers with deterministic rules only). To add Anthropic, Gemini or
a local Ollama model: implement ``LLMProvider`` in this package and add a
branch below — no business logic changes are needed.
"""

from app.core.config import Settings
from app.integrations.llm.base import LLMConfigurationError
from app.integrations.llm.client import LLMClient, RetryPolicy
from app.integrations.llm.openai_provider import OpenAIProvider

NOT_YET_IMPLEMENTED = {"anthropic", "gemini", "ollama"}


def build_llm_client(settings: Settings) -> LLMClient | None:
    provider_name = settings.AI_PROVIDER
    if provider_name == "none":
        return None
    if provider_name == "openai":
        key = settings.OPENAI_API_KEY.get_secret_value() if settings.OPENAI_API_KEY else ""
        provider = OpenAIProvider(
            api_key=key,
            model=settings.AI_MODEL,
            base_url=settings.OPENAI_BASE_URL,
            timeout_seconds=settings.AI_TIMEOUT_SECONDS,
        )
    elif provider_name in NOT_YET_IMPLEMENTED:
        raise LLMConfigurationError(f"AI provider '{provider_name}' is not implemented yet")
    else:
        raise LLMConfigurationError(f"Unknown AI provider '{provider_name}'")
    return LLMClient(
        provider,
        timeout_seconds=settings.AI_TIMEOUT_SECONDS,
        retry=RetryPolicy(
            max_retries=settings.AI_MAX_RETRIES,
            base_delay_seconds=settings.AI_RETRY_BASE_DELAY_SECONDS,
        ),
    )
