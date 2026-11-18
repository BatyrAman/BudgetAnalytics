from typing import Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_db
from app.core.errors import ErrorResponse
from app.models.enums import CategoryKind
from app.models.user import User
from app.schemas.category import CategoryCreate, CategoryResponse, CategoryUpdate
from app.services.categories import CategoryService

router = APIRouter(prefix="/categories", tags=["Categories"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
}


@router.get("", response_model=list[CategoryResponse], responses={401: _ERRORS[401]})
async def list_categories(
    kind: CategoryKind | None = Query(
        default=None, description="Only categories usable for this side (includes 'any')"
    ),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> list[CategoryResponse]:
    """System (default) categories plus the user's own categories."""

    categories = await CategoryService(db).list(current_user.id, kind)
    return [CategoryResponse.from_model(c) for c in categories]


@router.post(
    "", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED, responses=_ERRORS
)
async def create_category(
    payload: CategoryCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> CategoryResponse:
    """Creates a private category (409 if a category with this name is already
    visible to the user, including a system one)."""

    category = await CategoryService(db).create(payload, current_user.id)
    await db.commit()
    return CategoryResponse.from_model(category)


@router.get("/{category_id}", response_model=CategoryResponse, responses=_ERRORS)
async def get_category(
    category_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> CategoryResponse:
    return CategoryResponse.from_model(await CategoryService(db).get(category_id, current_user.id))


@router.patch("/{category_id}", response_model=CategoryResponse, responses=_ERRORS)
async def update_category(
    category_id: int,
    payload: CategoryUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> CategoryResponse:
    """Updates an own category. System categories are read-only (403)."""

    category = await CategoryService(db).update(category_id, payload, current_user.id)
    await db.commit()
    return CategoryResponse.from_model(category)


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT, responses=_ERRORS)
async def delete_category(
    category_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Deletes an own, unused category (409 while transactions or budgets use it)."""

    await CategoryService(db).delete(category_id, current_user.id)
    await db.commit()
