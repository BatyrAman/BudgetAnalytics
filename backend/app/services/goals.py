"""Financial goal use cases. Ownership: every query is scoped by user id;
another user's goal is indistinguishable from a missing one (404).

Derived values (engine, Decimal, ROUND_HALF_UP to minor units):
    progress_percent        = saved / target × 100     (share_percent, 0.01 %)
    remaining               = max(target − saved, 0)
    months_left             = months_until(today, target_date)
    required_monthly_saving = remaining / months_left  (equal parts, no interest)
``today`` is the local date in the caller's time zone.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, NotFoundError
from app.models.goal import FinancialGoal
from app.models.types import SUPPORTED_MINOR_UNITS
from app.models.user import User
from app.repositories.currency import CurrencyRepository
from app.repositories.goal import FinancialGoalRepository
from app.schemas.goals import GoalCreate, GoalResponse, GoalUpdate
from app.services.finance import CurrencySpec, share_percent
from app.services.finance.indicators import months_until, required_monthly_saving
from app.services.finance.money import calc_context, quantize_money


@dataclass(frozen=True)
class GoalProgress:
    progress_percent: Decimal
    remaining: Decimal
    is_reached: bool
    months_left: int | None
    required_monthly_saving: Decimal | None


def goal_progress(goal: FinancialGoal, today: date) -> GoalProgress:
    currency = CurrencySpec(goal.currency_code, SUPPORTED_MINOR_UNITS)
    with calc_context():
        remaining = quantize_money(
            max(goal.target_amount - goal.saved_amount, Decimal(0)), currency
        )
    progress = share_percent(goal.saved_amount, goal.target_amount) or Decimal("0.00")
    months = months_until(today, goal.target_date) if goal.target_date else None
    required = (
        required_monthly_saving(remaining, months, currency)
        if months is not None and remaining > 0
        else None
    )
    return GoalProgress(progress, remaining, remaining == 0, months, required)


def to_response(goal: FinancialGoal, today: date) -> GoalResponse:
    p = goal_progress(goal, today)
    return GoalResponse(
        id=goal.id,
        name=goal.name,
        currency_code=goal.currency_code,
        target_amount=goal.target_amount,
        saved_amount=goal.saved_amount,
        target_date=goal.target_date,
        progress_percent=p.progress_percent,
        remaining=p.remaining,
        is_reached=p.is_reached,
        months_left=p.months_left,
        required_monthly_saving=p.required_monthly_saving,
        created_at=goal.created_at,
        updated_at=goal.updated_at,
    )


class GoalService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.goals = FinancialGoalRepository(db)

    async def list(self, user_id: int) -> list[FinancialGoal]:
        return await self.goals.list_for_user(user_id)

    async def get(self, goal_id: int, user_id: int) -> FinancialGoal:
        goal = await self.goals.get_for_user(goal_id, user_id)
        if goal is None:
            raise NotFoundError("Goal not found", code="goal_not_found")
        return goal

    async def create(self, payload: GoalCreate, user: User) -> FinancialGoal:
        currency = payload.currency or user.default_currency_code
        if await CurrencyRepository(self.db).get(currency) is None:
            raise AppError("Unknown currency", code="unknown_currency")
        goal = FinancialGoal(
            user_id=user.id,
            name=payload.name,
            target_amount=payload.target_amount,
            saved_amount=payload.saved_amount,
            currency_code=currency,
            target_date=payload.target_date,
        )
        self.goals.add(goal)
        await self.db.flush()
        await self.db.refresh(goal)
        return goal

    async def update(self, goal_id: int, payload: GoalUpdate, user_id: int) -> FinancialGoal:
        goal = await self.get(goal_id, user_id)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(goal, field, value)
        await self.db.flush()
        await self.db.refresh(goal)
        return goal

    async def delete(self, goal_id: int, user_id: int) -> None:
        await self.db.delete(await self.get(goal_id, user_id))
