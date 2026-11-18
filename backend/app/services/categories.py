"""Category use cases. System categories (user_id NULL) are read-only defaults
visible to everyone; private categories are visible and editable only by their
owner. Another user's category is reported exactly like a missing one."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, PermissionDeniedError
from app.models.budget import Budget
from app.models.category import Category
from app.models.enums import CategoryKind, category_allows
from app.models.transaction import Transaction
from app.repositories.category import CategoryRepository
from app.repositories.transaction import TransactionRepository
from app.schemas.category import CategoryCreate, CategoryUpdate


class CategoryService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.categories = CategoryRepository(db)

    async def list(self, user_id: int, kind: CategoryKind | None = None) -> list[Category]:
        """``kind`` filter returns categories USABLE for that side: e.g.
        ``expense`` -> expense and ``any`` categories."""

        categories = await self.categories.list_visible(user_id)
        if kind is None or kind is CategoryKind.ANY:
            return categories
        return [c for c in categories if c.kind in (kind, CategoryKind.ANY)]

    async def get(self, category_id: int, user_id: int) -> Category:
        category = await self.categories.get_visible(category_id, user_id)
        if category is None:
            raise NotFoundError("Category not found")
        return category

    async def _get_own(self, category_id: int, user_id: int) -> Category:
        category = await self.get(category_id, user_id)
        if category.user_id is None:
            raise PermissionDeniedError("System categories are read-only")
        return category

    async def _ensure_name_free(
        self, name: str, user_id: int, exclude_id: int | None = None
    ) -> None:
        existing = await self.categories.get_visible_by_name(name, user_id)
        if existing is not None and existing.id != exclude_id:
            raise ConflictError("Category already exists")

    async def create(self, payload: CategoryCreate, user_id: int) -> Category:
        await self._ensure_name_free(payload.name, user_id)
        category = Category(**payload.model_dump(), user_id=user_id)
        self.categories.add(category)
        await self.db.flush()
        return category

    async def update(self, category_id: int, payload: CategoryUpdate, user_id: int) -> Category:
        category = await self._get_own(category_id, user_id)
        changes = payload.model_dump(exclude_unset=True)
        if "name" in changes:
            await self._ensure_name_free(changes["name"], user_id, exclude_id=category.id)
        new_kind = changes.get("kind")
        if new_kind is not None and new_kind != category.kind:
            await self._ensure_kind_fits_existing(category, CategoryKind(new_kind))
        for field, value in changes.items():
            setattr(category, field, value)
        await self.db.flush()
        return category

    async def _ensure_kind_fits_existing(self, category: Category, kind: CategoryKind) -> None:
        used_types = set(
            await self.db.scalars(
                select(Transaction.transaction_type)
                .where(Transaction.category_id == category.id)
                .distinct()
            )
        )
        if any(not category_allows(kind, t) for t in used_types):
            raise ConflictError(
                "The category already has transactions of another type; "
                "move them before changing its kind"
            )

    async def delete(self, category_id: int, user_id: int) -> None:
        category = await self._get_own(category_id, user_id)
        used_by_transactions = await TransactionRepository(self.db).count_for_category(category.id)
        used_by_budgets = await self.db.scalar(
            select(func.count(Budget.id)).where(Budget.category_id == category.id)
        )
        if used_by_transactions or used_by_budgets:
            raise ConflictError(
                "Category is used by transactions or budgets; reassign them before deleting"
            )
        await self.db.delete(category)
