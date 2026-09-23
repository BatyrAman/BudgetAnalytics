import pytest
from sqlalchemy import select

from app.models.user import User
from app.services.ai.contracts import LLMResponse, Message, Role, ToolCall
from app.services.ai.llm import LLMClient
from app.services.ai.provider import AIUnavailableError, DisabledProvider, register_provider
from app.services.ai.tools import ToolContext, ToolRegistry

pytestmark = pytest.mark.integration

EXPECTED_TOOLS = {
    "get_financial_profile",
    "get_spending_breakdown",
    "get_debts",
    "get_upcoming_payments",
    "simulate_debt_strategy",
    "calculate_loan",
    "calculate_mortgage",
    "calculate_deposit",
    "calculate_affordability",
    "calculate_emergency_fund",
    "search_bank_products",
}


async def _ctx(session, user_ctx) -> ToolContext:
    user = await session.scalar(select(User).where(User.id == user_ctx.id))
    return ToolContext(session=session, user=user)


def test_tool_specs_are_json_schema():
    specs = {s.name: s for s in ToolRegistry().specs()}
    assert set(specs) == EXPECTED_TOOLS
    assert specs["calculate_loan"].input_schema["type"] == "object"
    assert "amount" in specs["calculate_loan"].input_schema["properties"]
    # user_id нельзя передать ни в один инструмент
    assert all("user_id" not in str(s.input_schema) for s in specs.values())


async def test_tool_results_are_deterministic_json(session, alice):
    registry = ToolRegistry()
    ctx = await _ctx(session, alice)
    call = ToolCall("1", "calculate_loan", {"amount": "1000000", "annual_rate": "12", "term_months": 12})
    first = await registry.execute(call, ctx)
    second = await registry.execute(call, ctx)
    assert not first.is_error
    assert first.content == second.content
    assert first.content["monthly_payment"] == "88848.79"


async def test_tools_are_bound_to_context_user(session, alice, bob):
    await alice.post("/debts", json={
        "name": "Кредит", "debt_type": "consumer_loan", "principal": "100000", "annual_rate": "20",
        "monthly_payment": "10000", "payment_day": 5, "start_date": "2025-01-01"})
    registry = ToolRegistry()
    alice_debts = await registry.execute(ToolCall("1", "get_debts", {}), await _ctx(session, alice))
    bob_debts = await registry.execute(ToolCall("2", "get_debts", {"user_id": alice.id}), await _ctx(session, bob))
    assert len(alice_debts.content["items"]) == 1
    assert bob_debts.content["items"] == []  # лишний аргумент user_id игнорируется


async def test_tool_output_is_sanitized(session, alice):
    await alice.post("/debts", json={
        "name": "Долг Alice", "debt_type": "personal", "principal": "50000", "annual_rate": "0",
        "monthly_payment": "5000", "payment_day": 5, "start_date": "2025-01-01"})
    result = await ToolRegistry().execute(ToolCall("1", "get_debts", {}), await _ctx(session, alice))
    item = result.content["items"][0]
    assert "user_id" not in item
    assert item["name"] == "Долг [NAME]"  # имя владельца (full_name="Alice") скрыто
    assert item["balance"] == "50000.00"


async def test_tool_errors_are_structured(session, alice):
    registry = ToolRegistry()
    ctx = await _ctx(session, alice)
    invalid = await registry.execute(ToolCall("1", "calculate_loan", {"amount": "-1"}), ctx)
    assert invalid.is_error and invalid.content["error"]["code"] == "INVALID_ARGUMENTS"
    domain = await registry.execute(ToolCall("2", "simulate_debt_strategy", {}), ctx)
    assert domain.is_error and domain.content["error"]["code"] == "NO_ACTIVE_DEBTS"
    unknown = await registry.execute(ToolCall("3", "drop_database", {}), ctx)
    assert unknown.content["error"]["code"] == "UNKNOWN_TOOL"


async def test_all_read_tools_run(session, alice):
    registry = ToolRegistry()
    ctx = await _ctx(session, alice)
    for name, args in [
        ("get_financial_profile", {}),
        ("get_spending_breakdown", {"period": "year"}),
        ("get_upcoming_payments", {"days": 30}),
        ("calculate_deposit", {"amount": "100000", "annual_rate": "14", "term_months": 6}),
        ("calculate_mortgage", {"price": "20000000", "down_payment": "4000000", "annual_rate": "16", "term_years": 15}),
        ("calculate_affordability", {"new_payment": "50000", "monthly_income": "400000"}),
        ("calculate_emergency_fund", {"monthly_mandatory_expenses": "150000"}),
        ("search_bank_products", {"type": "deposit", "amount": "500000", "term_months": 6}),
    ]:
        result = await registry.execute(ToolCall(name, name, args), ctx)
        assert not result.is_error, (name, result.content)


class FakeProvider:
    """Провайдер подменяется без изменения бизнес-логики и tools."""

    name = "fake"

    async def generate(self, messages, *, system, options=None):
        return LLMResponse(text="ok")

    async def stream(self, messages, *, system, tools=(), options=None):
        yield

    async def tool_call(self, messages, *, system, tools, options=None):
        return LLMResponse(text="", tool_calls=(ToolCall("c1", "calculate_loan", {"amount": "1000", "annual_rate": "0", "term_months": 2}),))


async def test_provider_is_swappable_and_disabled_by_default(session, alice):
    with pytest.raises(AIUnavailableError):
        await LLMClient(DisabledProvider()).generate([Message(Role.USER, "hi")], system="s")

    register_provider("fake", FakeProvider)
    client = LLMClient(FakeProvider())
    registry = ToolRegistry()
    response = await client.tool_call([Message(Role.USER, "кредит 1000 на 2 месяца")], "s", registry.specs())
    result = await registry.execute(response.tool_calls[0], await _ctx(session, alice))
    assert result.content["monthly_payment"] == "500.00"
