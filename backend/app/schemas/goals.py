from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.common import CurrencyCodeStr, Name100, PatchModel, PositiveMoney


class GoalCreate(BaseModel):
    name: Name100
    target_amount: PositiveMoney
    saved_amount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=2)
    currency: CurrencyCodeStr | None = Field(
        default=None, description="Defaults to the user's default currency"
    )
    target_date: date | None = None


class GoalUpdate(PatchModel):
    nullable = frozenset({"target_date"})

    name: Name100 | None = None
    target_amount: PositiveMoney | None = None
    saved_amount: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    target_date: date | None = None


class GoalResponse(BaseModel):
    """Derived fields come from the finance engine (see app.services.goals)."""

    id: int
    name: str
    currency_code: str
    target_amount: Decimal
    saved_amount: Decimal
    target_date: date | None
    progress_percent: Decimal = Field(description="saved / target × 100 (may exceed 100)")
    remaining: Decimal = Field(description="max(target − saved, 0)")
    is_reached: bool
    months_left: int | None = Field(
        description="Calendar months until target_date; null without a date or when it has passed"
    )
    required_monthly_saving: Decimal | None = Field(
        description=(
            "remaining / months_left, equal monthly parts, no interest; null if not applicable"
        )
    )
    created_at: datetime
    updated_at: datetime
