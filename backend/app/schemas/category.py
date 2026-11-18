from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import CategoryKind
from app.schemas.common import HexColor, PatchModel


class CategoryBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100, description="Category name")
    color: HexColor = "#3B82F6"
    icon: str = Field(default="wallet", min_length=1, max_length=50, pattern=r"^[a-z0-9-]+$")
    kind: CategoryKind = Field(
        default=CategoryKind.ANY,
        description="income | expense | any — which transaction types may use it",
    )


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(PatchModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    color: HexColor | None = None
    icon: str | None = Field(default=None, min_length=1, max_length=50, pattern=r"^[a-z0-9-]+$")
    kind: CategoryKind | None = None


class CategoryResponse(BaseModel):
    """``is_system`` categories are shared defaults: visible to everyone,
    read-only. Other categories belong to the current user only."""

    id: int
    name: str
    color: str
    icon: str
    kind: CategoryKind
    is_system: bool = False

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_model(cls, category: object) -> "CategoryResponse":
        response = cls.model_validate(category)
        response.is_system = getattr(category, "user_id", None) is None
        return response
