"""
Бюджеты.

spent для бюджета с категорией = сумма расходов категории за текущий
календарный месяц; считается одним агрегирующим запросом на все
бюджеты пользователя. Для бюджетов без категории используется
сохранённое вручную значение (как в v0.1).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError, NotFoundError
from app.models.budget import Budget
from app.models.enums import CategoryKind
from app.repositories.analytics import AnalyticsRepository
from app.repositories.budgets import BudgetRepository
from app.repositories.categories import CategoryRepository
from app.schemas.budget import (
    BudgetAlert,
    BudgetCreate,
    BudgetDetail,
    BudgetProgress,
    BudgetResponse,
    BudgetStatistics,
    BudgetUpdate,
)
from app.services.finance.calendar import add_months
from app.services.finance.money import ZERO


@dataclass(frozen=True, slots=True)
class BudgetView:
    budget: Budget
    spent: Decimal
    spent_source: str

    @property
    def remaining(self) -> Decimal:
        return self.budget.monthly_limit - self.spent

    @property
    def progress(self) -> float:
        if self.budget.monthly_limit <= 0:
            return 0.0
        return float(round(self.spent / self.budget.monthly_limit * 100, 2))

    def response(self) -> BudgetResponse:
        b = self.budget
        return BudgetResponse(
            id=b.id,
            title=b.title,
            monthly_limit=b.monthly_limit,
            spent=self.spent,
            category_id=b.category_id,
            spent_source=self.spent_source,
            user_id=b.user_id,
            created_at=b.created_at,
            updated_at=b.updated_at,
        )

    def detail(self) -> BudgetDetail:
        return BudgetDetail(
            **self.response().model_dump(),
            remaining=self.remaining,
            progress=self.progress,
            is_exceeded=self.spent > self.budget.monthly_limit,
        )


def current_month_range(today: date) -> tuple[datetime, datetime]:
    start = today.replace(day=1)
    return datetime.combine(start, datetime.min.time()), datetime.combine(
        add_months(start, 1), datetime.min.time()
    )


class BudgetService:
    def __init__(self, session: AsyncSession, today: date | None = None) -> None:
        self.session = session
        self.repo = BudgetRepository(session)
        self.categories = CategoryRepository(session)
        self.analytics = AnalyticsRepository(session)
        self.today = today

    async def _views(self, user_id: int, budgets: list[Budget]) -> list[BudgetView]:
        category_ids = sorted({b.category_id for b in budgets if b.category_id is not None})
        start, end = current_month_range(self.today or date.today())
        spent = await self.analytics.category_spent(
            user_id, settings.DEFAULT_CURRENCY, category_ids, start, end
        )
        return [
            BudgetView(b, spent.get(b.category_id, ZERO), "transactions")
            if b.category_id is not None
            else BudgetView(b, b.spent, "manual")
            for b in budgets
        ]

    async def _get_owned(self, budget_id: int, user_id: int) -> Budget:
        budget = await self.repo.get_owned(budget_id, user_id)
        if budget is None:
            raise NotFoundError("Budget not found", code="BUDGET_NOT_FOUND")
        return budget

    async def _check_category(self, user_id: int, category_id: int | None) -> None:
        if category_id is None:
            return
        category = await self.categories.get_visible(category_id, user_id)
        if category is None:
            raise AppError("Category not found", code="CATEGORY_NOT_FOUND")
        if category.kind != CategoryKind.EXPENSE:
            raise AppError("Budget category must be an expense category", code="CATEGORY_KIND_MISMATCH")

    async def create(self, user_id: int, payload: BudgetCreate) -> BudgetResponse:
        await self._check_category(user_id, payload.category_id)
        budget = self.repo.add(
            Budget(
                title=payload.title,
                monthly_limit=payload.monthly_limit,
                category_id=payload.category_id,
                spent=ZERO,
                user_id=user_id,
            )
        )
        await self.session.commit()
        await self.session.refresh(budget)
        return (await self._views(user_id, [budget]))[0].response()

    async def list(self, user_id: int, limit: int, offset: int) -> tuple[list[BudgetResponse], int]:
        total = await self.repo.count_owned(user_id)
        budgets = await self.repo.list_owned(
            user_id, order_by=(Budget.created_at.desc(), Budget.id.desc()), limit=limit, offset=offset
        )
        return [v.response() for v in await self._views(user_id, budgets)], total

    async def all_views(self, user_id: int) -> list[BudgetView]:
        budgets = await self.repo.list_owned(user_id, order_by=Budget.id)
        return await self._views(user_id, budgets)

    async def get(self, budget_id: int, user_id: int) -> BudgetDetail:
        budget = await self._get_owned(budget_id, user_id)
        return (await self._views(user_id, [budget]))[0].detail()

    async def update(self, budget_id: int, user_id: int, payload: BudgetUpdate) -> BudgetResponse:
        budget = await self._get_owned(budget_id, user_id)
        updates = payload.model_dump(exclude_unset=True)
        if "category_id" in updates:
            await self._check_category(user_id, updates["category_id"])
        for required in ("title", "monthly_limit", "spent"):
            if required in updates and updates[required] is None:
                updates.pop(required)
        for field, value in updates.items():
            setattr(budget, field, value)
        await self.session.commit()
        await self.session.refresh(budget)
        return (await self._views(user_id, [budget]))[0].response()

    async def delete(self, budget_id: int, user_id: int) -> None:
        budget = await self._get_owned(budget_id, user_id)
        await self.repo.delete(budget)
        await self.session.commit()

    async def statistics(self, user_id: int) -> BudgetStatistics:
        views = await self.all_views(user_id)
        total_budget = sum((v.budget.monthly_limit for v in views), ZERO)
        total_spent = sum((v.spent for v in views), ZERO)
        utilization = float(round(total_spent / total_budget * 100, 2)) if total_budget > 0 else 0.0
        return BudgetStatistics(
            total_budget=total_budget,
            total_spent=total_spent,
            remaining=total_budget - total_spent,
            utilization_percent=utilization,
        )

    async def progress(self, user_id: int) -> list[BudgetProgress]:
        return [
            BudgetProgress(
                budget_id=v.budget.id,
                title=v.budget.title,
                monthly_limit=v.budget.monthly_limit,
                spent=v.spent,
                remaining=v.remaining,
                progress=v.progress,
            )
            for v in await self.all_views(user_id)
        ]

    async def alerts(self, user_id: int, threshold: float) -> list[BudgetAlert]:
        alerts: list[BudgetAlert] = []
        for v in await self.all_views(user_id):
            if v.progress < threshold:
                continue
            if v.spent > v.budget.monthly_limit:
                message = f"Бюджет «{v.budget.title}» превышен."
            else:
                message = f"Бюджет «{v.budget.title}» почти израсходован ({v.progress:.0f}%)."
            alerts.append(
                BudgetAlert(
                    title=v.budget.title,
                    spent=v.spent,
                    monthly_limit=v.budget.monthly_limit,
                    progress=v.progress,
                    message=message,
                )
            )
        return alerts
