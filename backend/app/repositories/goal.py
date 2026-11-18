from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.goal import FinancialGoal


class FinancialGoalRepository:
    """User-owned goals. Every method requires the owner's ``user_id``."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_for_user(self, goal_id: int, user_id: int) -> FinancialGoal | None:
        return await self.db.scalar(
            select(FinancialGoal).where(
                FinancialGoal.id == goal_id, FinancialGoal.user_id == user_id
            )
        )

    async def list_for_user(self, user_id: int) -> list[FinancialGoal]:
        result = await self.db.scalars(
            select(FinancialGoal).where(FinancialGoal.user_id == user_id).order_by(FinancialGoal.id)
        )
        return list(result)

    def add(self, goal: FinancialGoal) -> None:
        self.db.add(goal)
