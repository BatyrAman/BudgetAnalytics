from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CategoryBase(BaseModel):
    name: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Category name"
    )

    color: str = Field(
        default="#3B82F6",
        max_length=30,
        description="HEX color"
    )

    icon: str = Field(
        default="wallet",
        max_length=50,
        description="Icon name"
    )


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: str | None = Field(
        default=None,
        min_length=2,
        max_length=100
    )

    color: str | None = Field(
        default=None,
        max_length=30
    )

    icon: str | None = Field(
        default=None,
        max_length=50
    )


class CategoryResponse(CategoryBase):
    id: int

    model_config = ConfigDict(
        from_attributes=True
    )


class CategoryDetail(CategoryResponse):
    transaction_count: int = 0

    total_amount: float = 0.0


class CategoryListResponse(BaseModel):
    items: list[CategoryResponse]

    total: int


class CategoryStatistics(BaseModel):
    category_id: int

    category_name: str

    total_income: float

    total_expense: float

    transaction_count: int


class TopCategory(BaseModel):
    name: str

    amount: float

    percentage: float