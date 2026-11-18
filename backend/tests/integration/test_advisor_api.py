"""AI advisor end to end with a MOCKED provider (no network, no paid API)."""

import json
import logging
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.advisor import get_llm_client
from app.core.config import settings
from app.integrations.llm import (
    LLMClient,
    LLMRequest,
    LLMResponse,
    LLMUnavailableError,
    RetryPolicy,
    TokenUsage,
)
from app.main import app
from app.models.ai_usage import AIUsage
from app.models.goal import FinancialGoal
from tests.integration.helpers import API, bearer, category, create, register, tx

ALMATY = ZoneInfo("Asia/Almaty")
SECRET_KEY_MARKER = "sk-test-NEVER-LOG-THIS"


class FakeProvider:
    """Builds answers from the fact sheet it receives, like a well-behaved
    (or, in other modes, misbehaving) model would."""

    name = "fake"
    model = "fake-model-1"

    def __init__(self, mode: str = "grounded", investment: bool = False) -> None:
        self.mode = mode
        self.investment = investment
        self.requests: list[LLMRequest] = []

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        if self.mode == "error":
            raise LLMUnavailableError("upstream 503")
        data = json.loads(request.messages[1].content.split("\n", 1)[1])
        facts = {f["label"]: f for f in data["facts"]}
        income = next(f for f in data["facts"] if f["label"] == "Доход за месяц")
        category = next(f for label, f in facts.items() if label.startswith("Расходы по категории"))
        rate = next(f for f in data["facts"] if f["label"] == "Норма сбережений за месяц")
        number = income["value"] if self.mode == "grounded" else "1 234 567"
        if request.schema_name == "AdvisorReport":
            body: dict[str, Any] = {
                "summary": (
                    f"Доход за {income['period']} — {number} {income['unit']}. {category['label']}."
                ),
                "insights": [
                    {
                        "area": "savings",
                        "title": "Сбережения",
                        "explanation": f"Норма сбережений {rate['value']} %.",
                        "evidence": [rate["id"]],
                    }
                ],
                "recommendations": [
                    {
                        "title": "Резерв",
                        "action": "Откладывайте часть дохода.",
                        "reasoning": "Это снижает риски.",
                        "evidence": [income["id"]],
                        "assumptions": ["Доход останется стабильным."],
                        "priority": "high",
                        "involves_investment": self.investment,
                    }
                ],
                "risks": [],
                "assumptions": [],
                "data_gaps": data["data_gaps"],
            }
        else:
            body = {
                "answer": f"Ваш доход {number} {income['unit']}.",
                "evidence": [income["id"]],
                "assumptions": [],
                "involves_investment": False,
                "needs_more_data": False,
                "follow_up_question": None,
            }
        content = "{}" if self.mode == "garbage" else json.dumps(body, ensure_ascii=False)
        return LLMResponse(content, TokenUsage(800, 200), self.name, self.model)

    async def aclose(self) -> None:
        pass


async def _no_sleep(_: float) -> None:
    return None


@pytest.fixture
def provider() -> FakeProvider:
    return FakeProvider()


@pytest.fixture(autouse=True)
def llm(provider: FakeProvider):  # type: ignore[no-untyped-def]
    client = LLMClient(
        provider, timeout_seconds=5, retry=RetryPolicy(max_retries=1), sleep=_no_sleep
    )
    app.dependency_overrides[get_llm_client] = lambda: client
    yield client
    app.dependency_overrides.pop(get_llm_client, None)


def _month_start(months_ago: int) -> str:
    today = datetime.now(ALMATY).date()
    index = today.year * 12 + today.month - 1 - months_ago
    day = date(index // 12, index % 12 + 1, 1)
    return datetime.combine(day, time(12), tzinfo=ALMATY).isoformat()


@pytest.fixture
async def alice(client: httpx.AsyncClient, db_session: AsyncSession) -> dict[str, Any]:
    headers = bearer(await register(client, "alice.private@example.com"))
    me = (await client.get(f"{API}/auth/me", headers=headers)).json()
    secret_cat = await category(client, headers, "Долг Ивану")
    salary = await category(client, headers, "Работа")
    await tx(client, headers, salary, "600000", "income", _month_start(1))
    await tx(client, headers, secret_cat, "200000", "expense", _month_start(1))
    await tx(client, headers, salary, "50000", "income", _month_start(0))
    await create(
        client,
        "/budgets",
        headers,
        {"title": "Еда секретно", "monthly_limit": "1000.00", "category_id": secret_cat},
    )
    db_session.add(
        FinancialGoal(
            user_id=me["id"],
            name="Свадьба Айгерим",
            target_amount=Decimal("1000000"),
            currency_code="KZT",
        )
    )
    await db_session.commit()
    return {"headers": headers, "id": me["id"]}


async def _usage(db: AsyncSession, user_id: int) -> list[AIUsage]:
    return list(
        await db.scalars(select(AIUsage).where(AIUsage.user_id == user_id).order_by(AIUsage.id))
    )


async def test_grounded_llm_report(
    client: httpx.AsyncClient,
    alice: dict,
    provider: FakeProvider,
    db_session: AsyncSession,  # type: ignore[type-arg]
) -> None:
    response = await client.post(f"{API}/advisor/insights", headers=alice["headers"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["generated_by"], body["fallback_reason"], body["provider"], body["model"]) == (
        "llm",
        None,
        "fake",
        "fake-model-1",
    )
    assert body["prompt_version"] == "advisor-v1"
    # Pseudonymized names are restored for the user...
    assert "Долг Ивану" in body["report"]["summary"]
    labels = " ".join(f["label"] for f in body["facts"])
    assert "Долг Ивану" in labels and "Еда секретно" in labels and "Свадьба Айгерим" in labels
    assert any(f["value"] == "600000.00" for f in body["facts"])
    assert body["disclaimers"] and "не индивидуальная" in body["disclaimers"][0]

    # ...but never sent to the provider, nor the user's identity.
    sent = json.dumps([m.content for m in provider.requests[0].messages], ensure_ascii=False)
    for private in (
        "Долг Ивану",
        "Еда секретно",
        "Свадьба Айгерим",
        "alice.private@example.com",
        "Test User",
    ):
        assert private not in sent
    assert "[CAT-1]" in sent and "[BUDGET-1]" in sent and "[GOAL-1]" in sent
    assert provider.requests[0].response_schema["additionalProperties"] is False

    rows = await _usage(db_session, alice["id"])
    assert [(r.outcome, r.input_tokens, r.output_tokens, r.provider) for r in rows] == [
        ("success", 800, 200, "fake")
    ]


@pytest.mark.parametrize(
    ("mode", "reason", "outcome"),
    [
        ("invented", "invalid_output", "fallback_invalid"),  # number not in facts -> rejected
        ("garbage", "invalid_output", "fallback_invalid"),  # schema violation -> rejected
        ("error", "provider_error", "fallback_error"),
    ],
)
async def test_untrusted_or_failed_llm_falls_back_to_rules(
    client: httpx.AsyncClient,
    alice: dict,  # type: ignore[type-arg]
    provider: FakeProvider,
    db_session: AsyncSession,
    mode: str,
    reason: str,
    outcome: str,
) -> None:
    provider.mode = mode
    body = (await client.post(f"{API}/advisor/insights", headers=alice["headers"])).json()
    assert (body["generated_by"], body["fallback_reason"]) == ("rules", reason)
    assert "1 234 567" not in json.dumps(body, ensure_ascii=False)
    assert "600000.00" in body["report"]["summary"]  # rules quote facts verbatim
    assert [r.outcome for r in await _usage(db_session, alice["id"])] == [outcome]
    if mode == "error":
        assert len(provider.requests) == 2  # retried once (retryable), then gave up


async def test_limit_reached_skips_the_provider(
    client: httpx.AsyncClient,
    alice: dict,
    provider: FakeProvider,  # type: ignore[type-arg]
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "AI_DAILY_TOKEN_LIMIT_PER_USER", 100)
    body = (await client.post(f"{API}/advisor/insights", headers=alice["headers"])).json()
    assert (body["generated_by"], body["fallback_reason"]) == ("rules", "limit_reached")
    assert provider.requests == []
    assert [r.outcome for r in await _usage(db_session, alice["id"])] == ["limited"]


async def test_cost_limit_uses_recorded_spend(
    client: httpx.AsyncClient,
    alice: dict,
    provider: FakeProvider,  # type: ignore[type-arg]
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "AI_INPUT_PRICE_PER_1M_TOKENS_USD", Decimal("1"))
    monkeypatch.setattr(settings, "AI_OUTPUT_PRICE_PER_1M_TOKENS_USD", Decimal("4"))
    monkeypatch.setattr(settings, "AI_DAILY_COST_LIMIT_PER_USER_USD", Decimal("0.02"))
    first = (await client.post(f"{API}/advisor/insights", headers=alice["headers"])).json()
    assert first["generated_by"] == "llm"
    rows = await _usage(db_session, alice["id"])
    assert rows[0].cost_usd == Decimal("0.001600")  # 800 × 1/1e6 + 200 × 4/1e6
    # Recorded 0.0016 + estimate (≥ 1 500 output tokens × 4/1e6 = 0.006) stays under 0.02 ...
    monkeypatch.setattr(settings, "AI_DAILY_COST_LIMIT_PER_USER_USD", Decimal("0.005"))
    second = (await client.post(f"{API}/advisor/insights", headers=alice["headers"])).json()
    assert second["fallback_reason"] == "limit_reached"  # ... but not under 0.005
    assert len(provider.requests) == 1


async def test_disabled_ai_uses_rules(client: httpx.AsyncClient, alice: dict) -> None:  # type: ignore[type-arg]
    app.dependency_overrides[get_llm_client] = lambda: None
    body = (await client.post(f"{API}/advisor/insights", headers=alice["headers"])).json()
    assert (body["generated_by"], body["fallback_reason"], body["provider"]) == (
        "rules",
        "disabled",
        "none",
    )


async def test_ask_redacts_identifiers_and_adds_investment_disclaimer(
    client: httpx.AsyncClient,
    alice: dict,
    provider: FakeProvider,  # type: ignore[type-arg]
) -> None:
    question = "Стоит ли купить акции? Пишите на ivan@mail.kz, карта 4400 4300 1234 5678"
    response = await client.post(
        f"{API}/advisor/ask", headers=alice["headers"], json={"question": question}
    )
    body = response.json()
    assert response.status_code == 200 and body["generated_by"] == "llm"
    assert body["answer"]["answer"].startswith("Ваш доход")
    sent = provider.requests[0].messages[2].content
    assert "ivan@mail.kz" not in sent and "4400 4300 1234 5678" not in sent
    assert "акции" in sent
    assert any("Инвестиции связаны с риском" in d for d in body["disclaimers"])


async def test_investment_recommendation_gets_disclaimer(
    client: httpx.AsyncClient,
    alice: dict,
    provider: FakeProvider,  # type: ignore[type-arg]
) -> None:
    provider.investment = True
    body = (await client.post(f"{API}/advisor/insights", headers=alice["headers"])).json()
    assert any("Инвестиции связаны с риском" in d for d in body["disclaimers"])


@pytest.mark.parametrize("question", ["", "ab", "x" * 501])
async def test_question_validation(client: httpx.AsyncClient, alice: dict, question: str) -> None:  # type: ignore[type-arg]
    response = await client.post(
        f"{API}/advisor/ask", headers=alice["headers"], json={"question": question}
    )
    assert response.status_code == 422


@pytest.mark.parametrize("path", ["insights", "ask"])
async def test_authentication_required(client: httpx.AsyncClient, path: str) -> None:
    assert (
        await client.post(f"{API}/advisor/{path}", json={"question": "Как дела?"})
    ).status_code == 401


async def test_facts_belong_to_the_current_user_only(
    client: httpx.AsyncClient,
    alice: dict,
    provider: FakeProvider,  # type: ignore[type-arg]
) -> None:
    bob = bearer(await register(client, "bob@example.com"))
    app.dependency_overrides[get_llm_client] = lambda: None
    body = (await client.post(f"{API}/advisor/insights", headers=bob)).json()
    text = json.dumps(body, ensure_ascii=False)
    assert "600000.00" not in text and "Долг Ивану" not in text and "Свадьба" not in text


async def test_logs_contain_no_financial_data_question_or_keys(
    client: httpx.AsyncClient,
    alice: dict,
    provider: FakeProvider,  # type: ignore[type-arg]
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "OPENAI_API_KEY", SECRET_KEY_MARKER)
    caplog.set_level(logging.DEBUG)
    await client.post(f"{API}/advisor/insights", headers=alice["headers"])
    provider.mode = "invented"
    await client.post(
        f"{API}/advisor/ask",
        headers=alice["headers"],
        json={"question": "Секретный вопрос про долг Ивану"},
    )
    rendered = "\n".join(
        f"{r.getMessage()} {getattr(r, 'fields', '')} {r.exc_text or ''}" for r in caplog.records
    )
    assert "llm call" in rendered  # metadata IS logged
    for forbidden in (
        "600000",
        "200000",
        "Долг Ивану",
        "Секретный вопрос",
        "Свадьба",
        "alice.private",
        SECRET_KEY_MARKER,
        "1 234 567",
    ):
        assert forbidden not in rendered, forbidden
