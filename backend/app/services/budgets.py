"""Budget use cases and the legacy progress adapter.

The math lives in ``app.services.finance.budget``. ``budget_progress_percent``
keeps the legacy float contract (``progress: float``; 0 for a non-positive
limit) used by the deprecated manual-``spent`` endpoints.
"""

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, NotFoundError
from app.models.budget import Budget
from app.models.enums import CategoryKind
from app.models.user import User
from app.repositories.budget import BudgetRepository
from app.repositories.category import CategoryRepository
from app.repositories.currency import CurrencyRepository
from app.schemas.budget import BudgetCreate, BudgetUpdate
from app.services.finance import KZT, budget_utilization


def budget_progress_percent(spent: Decimal, monthly_limit: Decimal) -> float:
    """Share of the limit already spent, in percent, rounded to 0.01 (HALF_UP)."""

    if monthly_limit <= 0:
        return 0.0
    return float(budget_utilization(monthly_limit, spent, KZT).utilization_percent)


class BudgetService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.budgets = BudgetRepository(db)

    async def get(self, budget_id: int, user_id: int) -> Budget:
        budget = await self.budgets.get_for_user(budget_id, user_id)
        if budget is None:
            raise NotFoundError("Budget not found")
        return budget

    async def _check_category(self, category_id: int | None, user_id: int) -> None:
        if category_id is None:
            return
        category = await CategoryRepository(self.db).get_visible(category_id, user_id)
        if category is None:
            raise AppError("Category not found")
        if category.kind is CategoryKind.INCOME:
            raise AppError("A budget limits spending; an income category cannot be used")

    async def _check_currency(self, code: str) -> None:
        if await CurrencyRepository(self.db).get(code) is None:
            raise AppError("Unknown currency")

    async def create(self, payload: BudgetCreate, user: User) -> Budget:
        currency = payload.currency or user.default_currency_code
        await self._check_currency(currency)
        await self._check_category(payload.category_id, user.id)
        budget = Budget(
            title=payload.title,
            monthly_limit=payload.monthly_limit,
            spent=Decimal("0"),
            currency_code=currency,
            category_id=payload.category_id,
            user_id=user.id,
        )
        self.budgets.add(budget)
        await self.db.flush()
        await self.db.refresh(budget)
        return budget

    async def update(self, budget_id: int, payload: BudgetUpdate, user_id: int) -> Budget:
        budget = await self.get(budget_id, user_id)
        changes = payload.model_dump(exclude_unset=True)
        if "category_id" in changes:
            await self._check_category(changes["category_id"], user_id)
        if "currency" in changes:
            await self._check_currency(changes["currency"])
            changes["currency_code"] = changes.pop("currency")
        for field, value in changes.items():
            setattr(budget, field, value)
        await self.db.flush()
        await self.db.refresh(budget)
        return budget

    async def delete(self, budget_id: int, user_id: int) -> None:
        await self.db.delete(await self.get(budget_id, user_id))
