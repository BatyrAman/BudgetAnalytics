from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category


class CategoryRepository:
    """Categories visible to a user = system categories (``user_id IS NULL``)
    plus the user's own. Another user's private categories are never visible."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def _visible_to(user_id: int):
        return or_(Category.user_id.is_(None), Category.user_id == user_id)

    async def list_visible(self, user_id: int) -> list[Category]:
        result = await self.db.scalars(
            select(Category).where(self._visible_to(user_id)).order_by(Category.name, Category.id)
        )
        return list(result)

    async def get_visible(self, category_id: int, user_id: int) -> Category | None:
        return await self.db.scalar(
            select(Category).where(Category.id == category_id, self._visible_to(user_id))
        )

    async def get_visible_by_name(self, name: str, user_id: int) -> Category | None:
        """Own category with this name, else a system one with this name."""

        return await self.db.scalar(
            select(Category)
            .where(Category.name == name, self._visible_to(user_id))
            .order_by(Category.user_id.is_(None))  # own (False) before system (True)
            .limit(1)
        )

    async def get_or_create_own(self, name: str, user_id: int) -> Category:
        """Visible category by name, or a new private category of the user."""

        existing = await self.get_visible_by_name(name, user_id)
        if existing is not None:
            return existing
        category = Category(name=name, user_id=user_id)
        self.db.add(category)
        await self.db.flush()
        return category

    def add(self, category: Category) -> None:
        self.db.add(category)
