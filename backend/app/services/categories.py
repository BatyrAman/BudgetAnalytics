from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.models.category import Category
from app.models.enums import CategoryKind
from app.repositories.categories import CategoryRepository
from app.schemas.category import CategoryCreate, CategoryUpdate


class CategoryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = CategoryRepository(session)

    async def list(self, user_id: int, kind: CategoryKind | None = None) -> list[Category]:
        return await self.repo.list_visible(user_id, kind)

    async def create(self, user_id: int, payload: CategoryCreate) -> Category:
        if await self.repo.name_taken(user_id, payload.name, payload.kind):
            raise ConflictError("Category already exists", code="CATEGORY_EXISTS")
        category = self.repo.add(Category(user_id=user_id, **payload.model_dump()))
        await self.session.commit()
        await self.session.refresh(category)
        return category

    async def _get_own(self, category_id: int, user_id: int) -> Category:
        # Системные и чужие категории изменять нельзя — для них 404.
        category = await self.repo.get_owned(category_id, user_id)
        if category is None:
            raise NotFoundError("Category not found", code="CATEGORY_NOT_FOUND")
        return category

    async def update(self, category_id: int, user_id: int, payload: CategoryUpdate) -> Category:
        category = await self._get_own(category_id, user_id)
        updates = payload.model_dump(exclude_unset=True, exclude_none=True)
        if "name" in updates and await self.repo.name_taken(
            user_id, updates["name"], category.kind, exclude_id=category.id
        ):
            raise ConflictError("Category already exists", code="CATEGORY_EXISTS")
        for field, value in updates.items():
            setattr(category, field, value)
        await self.session.commit()
        await self.session.refresh(category)
        return category

    async def delete(self, category_id: int, user_id: int) -> None:
        category = await self._get_own(category_id, user_id)
        # Операции остаются, category_id → NULL (ON DELETE SET NULL).
        await self.repo.delete(category)
        await self.session.commit()
