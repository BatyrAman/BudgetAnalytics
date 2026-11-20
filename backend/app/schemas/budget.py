from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import CurrencyCodeStr, Page, PatchModel, PositiveMoney

_TITLE = Field(min_length=2, max_length=100, description="Budget name")


class BudgetCreate(BaseModel):
    title: str = _TITLE
    monthly_limit: PositiveMoney = Field(description="Monthly spending limit")
    currency: CurrencyCodeStr | None = Field(
        default=None, description="Defaults to the user's default currency"
    )
    category_id: int | None = Field(
        default=None, description="Visible category; omit for a limit on all expenses"
    )


class BudgetUpdate(PatchModel):
    nullable = frozenset({"category_id"})

    title: str | None = Field(default=None, min_length=2, max_length=100)
    monthly_limit: PositiveMoney | None = None
    spent: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=18,
        decimal_places=2,
        description="DEPRECATED manual value; actual spending comes from /utilization",
    )
    currency: CurrencyCodeStr | None = None
    category_id: int | None = None


class BudgetResponse(BaseModel):
    id: int
    title: str
    monthly_limit: Decimal
    currency_code: str
    category_id: int | None
    spent: Decimal = Field(
        description=(
            "DEPRECATED: manually entered value, NOT computed from transactions. "
            "Clients must use GET /budgets/utilization or GET /budgets/{id}/utilization "
            "for actual spending."
        )
    )
    user_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


_DEPRECATED_MANUAL = (
    "DEPRECATED: derived from the manual `spent` value, NOT from transactions. "
    "Clients must use GET /budgets/utilization or GET /budgets/{id}/utilization."
)


class BudgetDetail(BudgetResponse):
    remaining: Decimal = Field(description=_DEPRECATED_MANUAL)
    progress: float = Field(description=_DEPRECATED_MANUAL)
    is_exceeded: bool = Field(description=_DEPRECATED_MANUAL)


class BudgetListResponse(Page[BudgetResponse]):
    pass


class BudgetUtilizationResponse(BaseModel):
    """Computed from transactions: net expenses (expenses − refunds) of the
    budget's category (or all categories) in its currency for the month."""

    budget_id: int
    month: str = Field(examples=["2025-03"])
    currency_code: str
    limit: Decimal
    spent: Decimal
    remaining: Decimal
    utilization_percent: Decimal
    is_exceeded: bool


# ---------------------------------------------------------------- legacy (deprecated)
class BudgetStatistics(BaseModel):
    total_budget: Decimal
    total_spent: Decimal
    remaining: Decimal
    utilization_percent: float


class BudgetProgress(BaseModel):
    budget_id: int
    title: str
    monthly_limit: Decimal
    spent: Decimal
    remaining: Decimal
    progress: float


class BudgetAlert(BaseModel):
    title: str
    spent: Decimal
    monthly_limit: Decimal
    progress: float
    message: str
