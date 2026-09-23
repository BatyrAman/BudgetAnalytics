from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class BudgetBase(BaseModel):
    title: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Budget name"
    )

    monthly_limit: Decimal = Field(
        ...,
        gt=0,
        decimal_places=2,
        description="Monthly budget limit"
    )


class BudgetCreate(BudgetBase):
    pass


class BudgetUpdate(BaseModel):
    title: str | None = Field(
        default=None,
        min_length=2,
        max_length=100
    )

    monthly_limit: Decimal | None = Field(
        default=None,
        gt=0,
        decimal_places=2
    )

    spent: Decimal | None = Field(
        default=None,
        ge=0,
        decimal_places=2
    )


class BudgetResponse(BudgetBase):
    id: int

    spent: Decimal

    user_id: int

    created_at: datetime

    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True
    )


class BudgetDetail(BudgetResponse):
    remaining: Decimal

    progress: float

    is_exceeded: bool


class BudgetListResponse(BaseModel):
    items: list[BudgetResponse]

    total: int


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