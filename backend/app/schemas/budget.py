from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import MoneyDecimal, NonNegativeMoney, PositiveMoney


class BudgetBase(BaseModel):
    title: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Budget name"
    )

    monthly_limit: PositiveMoney = Field(description="Monthly budget limit")


class BudgetCreate(BudgetBase):
    # Если указана категория, spent считается по расходам категории
    # за текущий месяц автоматически.
    category_id: int | None = None


class BudgetUpdate(BaseModel):
    title: str | None = Field(
        default=None,
        min_length=2,
        max_length=100
    )

    monthly_limit: PositiveMoney | None = None

    # Ручной учёт — только для бюджетов без категории.
    spent: NonNegativeMoney | None = None

    category_id: int | None = None


class BudgetResponse(BaseModel):
    id: int

    title: str

    monthly_limit: MoneyDecimal

    spent: MoneyDecimal

    category_id: int | None = None

    # "transactions" — посчитано по операциям месяца, "manual" — введено вручную.
    spent_source: str = "manual"

    user_id: int

    created_at: datetime

    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True
    )


class BudgetDetail(BudgetResponse):
    remaining: MoneyDecimal

    progress: float

    is_exceeded: bool


class BudgetListResponse(BaseModel):
    items: list[BudgetResponse]

    total: int


class BudgetStatistics(BaseModel):
    total_budget: MoneyDecimal

    total_spent: MoneyDecimal

    remaining: MoneyDecimal

    utilization_percent: float


class BudgetProgress(BaseModel):
    budget_id: int

    title: str

    monthly_limit: MoneyDecimal

    spent: MoneyDecimal

    remaining: MoneyDecimal

    progress: float


class BudgetAlert(BaseModel):
    title: str

    spent: MoneyDecimal

    monthly_limit: MoneyDecimal

    progress: float

    message: str
