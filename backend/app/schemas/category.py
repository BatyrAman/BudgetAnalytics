from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import CategoryKind


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
    kind: CategoryKind = CategoryKind.EXPENSE


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
    kind: CategoryKind
    is_system: bool

    model_config = ConfigDict(
        from_attributes=True
    )
