from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.budget import Budget


class BudgetRepository:
    """User-owned budgets. Every method requires the owner's ``user_id``."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_for_user(self, budget_id: int, user_id: int) -> Budget | None:
        return await self.db.scalar(
            select(Budget).where(Budget.id == budget_id, Budget.user_id == user_id)
        )

    async def list_for_user(self, user_id: int) -> list[Budget]:
        result = await self.db.scalars(
            select(Budget).where(Budget.user_id == user_id).order_by(Budget.id)
        )
        return list(result)

    def add(self, budget: Budget) -> None:
        self.db.add(budget)
