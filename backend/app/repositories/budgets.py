from __future__ import annotations

from sqlalchemy import func, select

from app.models.budget import Budget
from app.repositories.base import OwnedRepository


class BudgetRepository(OwnedRepository[Budget]):
    model = Budget

    async def totals(self, user_id: int):
        return (
            await self.session.execute(
                select(
                    func.coalesce(func.sum(Budget.monthly_limit), 0),
                    func.count(Budget.id),
                ).where(Budget.user_id == user_id)
            )
        ).one()
