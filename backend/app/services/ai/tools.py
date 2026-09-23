"""
Безопасный tool API для будущего AI Coach.

* LLM никогда не работает с БД напрямую: каждый tool — тонкая
  обёртка над детерминированным application-сервисом.
* Контекст (user, сессия, дата) задаёт сервер — модель не может
  передать user_id и получить чужие данные.
* Вход валидируется Pydantic-моделью (JSON Schema уходит в LLM),
  выход сериализуется в JSON (деньги — строки) и проходит PII-редакцию.
* Ошибки возвращаются структурированно, без внутренних деталей.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.enums import ProductType
from app.models.user import User
from app.schemas.analytics_overview import OverviewSummary
from app.schemas.common import MoneyDecimal, NonNegativeMoney, PercentDecimal
from app.schemas.debt import StrategyRequest, StrategyResponse
from app.schemas.finance import (
    AffordabilityRequest,
    AffordabilityResponse,
    DepositCalcRequest,
    DepositCalcResponse,
    EmergencyFundRequest,
    EmergencyFundResponse,
    FinancialProfileSummary,
    LoanCalcRequest,
    LoanCalcResponse,
    MortgageCalcRequest,
    MortgageCalcResponse,
)
from app.schemas.products import BankProductResponse
from app.services.ai.contracts import ToolCall, ToolResult, ToolSpec
from app.services.ai.privacy import PIIRedactor
from app.services.analytics.overview import AnalyticsOverviewService
from app.services.analytics.periods import Period
from app.services.calculators import CalculatorService
from app.services.debts.service import DebtService
from app.services.finance.debt_strategy import Strategy
from app.services.products.service import BankProductService

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ToolContext:
    """Серверный контекст вызова. Его нельзя изменить из аргументов модели."""

    session: AsyncSession
    user: User
    today: date = field(default_factory=date.today)


Handler = Callable[[ToolContext, BaseModel], Awaitable[BaseModel | list[BaseModel]]]


@dataclass(frozen=True, slots=True)
class Tool:
    name: str
    description: str
    input_model: type[BaseModel]
    handler: Handler

    def spec(self) -> ToolSpec:
        return ToolSpec(self.name, self.description, self.input_model.model_json_schema())


# ---------------------------------------------------------------- inputs


class NoInput(BaseModel):
    pass


class SpendingInput(BaseModel):
    period: Period = Field(default=Period.MONTH, description="day|week|month|half_year|year")


class UpcomingInput(BaseModel):
    days: int = Field(default=30, ge=1, le=90)


class StrategyInput(BaseModel):
    extra_payment: NonNegativeMoney = Decimal("0")
    strategy: Strategy = Strategy.AVALANCHE


class ProductSearchInput(BaseModel):
    type: ProductType
    amount: Decimal | None = Field(default=None, gt=0)
    term_months: int | None = Field(default=None, ge=1, le=600)


# --------------------------------------------------------------- outputs


class CategoryAmount(BaseModel):
    name: str
    amount: MoneyDecimal
    share_percent: PercentDecimal


class SpendingBreakdown(BaseModel):
    period: Period
    currency: str
    summary: OverviewSummary
    categories: list[CategoryAmount]
    recurring: list[dict[str, Any]]


class ToolList(BaseModel):
    items: list[Any]


# -------------------------------------------------------------- handlers


async def _profile(ctx: ToolContext, _: NoInput) -> FinancialProfileSummary:
    return await CalculatorService(ctx.session).profile_summary(ctx.user)


async def _spending(ctx: ToolContext, data: SpendingInput) -> SpendingBreakdown:
    overview = await AnalyticsOverviewService(ctx.session, ctx.today).overview(ctx.user.id, data.period)
    return SpendingBreakdown(
        period=data.period,
        currency=overview.period.currency,
        summary=overview.summary,
        categories=[
            CategoryAmount(name=c.name, amount=c.amount, share_percent=c.share_percent)
            for c in overview.categories
        ],
        recurring=[{"merchant": r.merchant, "amount": r.amount, "months": r.months} for r in overview.recurring],
    )


async def _debts(ctx: ToolContext, _: NoInput) -> ToolList:
    return ToolList(items=await DebtService(ctx.session, ctx.today).list(ctx.user.id))


async def _upcoming(ctx: ToolContext, data: UpcomingInput) -> ToolList:
    return ToolList(items=await DebtService(ctx.session, ctx.today).calendar(ctx.user.id, data.days))


async def _strategy(ctx: ToolContext, data: StrategyInput) -> StrategyResponse:
    return await DebtService(ctx.session, ctx.today).strategy(
        ctx.user.id,
        StrategyRequest(extra_payment=data.extra_payment, strategy=data.strategy, include_timeline=False),
    )


async def _loan(ctx: ToolContext, data: LoanCalcRequest) -> LoanCalcResponse:
    return CalculatorService().loan(data.model_copy(update={"include_schedule": False}))


async def _mortgage(ctx: ToolContext, data: MortgageCalcRequest) -> MortgageCalcResponse:
    return await CalculatorService(ctx.session).mortgage(ctx.user, data.model_copy(update={"include_schedule": False}))


async def _deposit(ctx: ToolContext, data: DepositCalcRequest) -> DepositCalcResponse:
    return CalculatorService().deposit(data)


async def _affordability(ctx: ToolContext, data: AffordabilityRequest) -> AffordabilityResponse:
    return await CalculatorService(ctx.session).affordability(ctx.user, data)


async def _emergency(ctx: ToolContext, data: EmergencyFundRequest) -> EmergencyFundResponse:
    return await CalculatorService(ctx.session).emergency_fund(ctx.user, data)


async def _products(ctx: ToolContext, data: ProductSearchInput) -> ToolList:
    service = BankProductService(ctx.session)
    products = await service.search(data.type, data.amount, data.term_months, limit=10)
    return ToolList(
        items=[
            BankProductResponse(
                id=p.id,
                bank_id=p.bank_id,
                bank_name=p.bank.name,
                product_type=p.product_type,
                name=p.name,
                rate_min=p.rate_min,
                rate_max=p.rate_max,
                gesv=p.gesv,
                term_min=p.term_min,
                term_max=p.term_max,
                amount_min=p.amount_min,
                amount_max=p.amount_max,
                currency=p.currency,
                conditions=p.conditions,
                source=p.source,
                source_url=p.source_url,
                fetched_at=p.fetched_at,
                updated_at=p.updated_at,
                is_stale=service.is_stale(p),
            )
            for p in products
        ]
    )


TOOLS: tuple[Tool, ...] = (
    Tool("get_financial_profile", "Агрегаты пользователя: доход, обязательные расходы, платежи по долгам.", NoInput, _profile),
    Tool("get_spending_breakdown", "Доходы, расходы и категории за период.", SpendingInput, _spending),
    Tool("get_debts", "Активные долги с прогнозом закрытия и переплатой.", NoInput, _debts),
    Tool("get_upcoming_payments", "Платежи по долгам на ближайшие N дней.", UpcomingInput, _upcoming),
    Tool("simulate_debt_strategy", "Помесячная симуляция погашения долгов по стратегии.", StrategyInput, _strategy),
    Tool("calculate_loan", "Платёж, переплата и эффективная ставка кредита.", LoanCalcRequest, _loan),
    Tool("calculate_mortgage", "Ипотека: платёж, переплата, требуемый доход.", MortgageCalcRequest, _mortgage),
    Tool("calculate_deposit", "Доходность вклада с капитализацией или без.", DepositCalcRequest, _deposit),
    Tool("calculate_affordability", "Потянет ли пользователь новый платёж; уровень риска.", AffordabilityRequest, _affordability),
    Tool("calculate_emergency_fund", "Размер подушки безопасности и срок накопления.", EmergencyFundRequest, _emergency),
    Tool("search_bank_products", "Предложения банков из базы ставок с источником и датой.", ProductSearchInput, _products),
)


class ToolRegistry:
    def __init__(self, tools: tuple[Tool, ...] = TOOLS) -> None:
        self._tools = {tool.name: tool for tool in tools}

    def specs(self) -> list[ToolSpec]:
        return [tool.spec() for tool in self._tools.values()]

    def names(self) -> list[str]:
        return list(self._tools)

    async def execute(self, call: ToolCall, ctx: ToolContext) -> ToolResult:
        tool = self._tools.get(call.name)
        if tool is None:
            return ToolResult(call.id, call.name, {"error": {"code": "UNKNOWN_TOOL"}}, is_error=True)
        try:
            data = tool.input_model.model_validate(call.arguments)
            output = await tool.handler(ctx, data)
        except ValidationError as exc:
            errors = [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]
            return ToolResult(call.id, call.name, {"error": {"code": "INVALID_ARGUMENTS", "details": errors}}, True)
        except AppError as exc:
            return ToolResult(call.id, call.name, {"error": {"code": exc.code, "message": exc.message}}, True)
        except Exception:
            logger.exception("Tool %s failed", call.name)
            return ToolResult(call.id, call.name, {"error": {"code": "TOOL_FAILED"}}, True)

        redactor = PIIRedactor(known_names=[ctx.user.full_name])
        payload = output.model_dump(mode="json")
        return ToolResult(call.id, call.name, redactor.sanitize(payload))
