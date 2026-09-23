from __future__ import annotations

from sqlalchemy import func, or_, select

from app.models.category import Category
from app.models.enums import CategoryKind
from app.repositories.base import Repository


def visible_to(user_id: int):
    """Системные категории + собственные категории пользователя."""

    return or_(Category.user_id.is_(None), Category.user_id == user_id)


class CategoryRepository(Repository):
    async def get_visible(self, category_id: int, user_id: int) -> Category | None:
        return await self.session.scalar(
            select(Category).where(Category.id == category_id, visible_to(user_id))
        )

    async def get_owned(self, category_id: int, user_id: int) -> Category | None:
        return await self.session.scalar(
            select(Category).where(Category.id == category_id, Category.user_id == user_id)
        )

    async def list_visible(self, user_id: int, kind: CategoryKind | None = None) -> list[Category]:
        stmt = select(Category).where(visible_to(user_id))
        if kind is not None:
            stmt = stmt.where(Category.kind == kind)
        stmt = stmt.order_by(Category.user_id.is_not(None), Category.name)
        return list((await self.session.scalars(stmt)).all())

    async def find_by_name(
        self, user_id: int, name: str, kind: CategoryKind
    ) -> Category | None:
        """Своя категория приоритетнее системной с тем же именем."""

        stmt = (
            select(Category)
            .where(
                visible_to(user_id),
                func.lower(Category.name) == name.strip().lower(),
                Category.kind == kind,
            )
            .order_by(Category.user_id.is_(None))
            .limit(1)
        )
        return await self.session.scalar(stmt)

    async def name_taken(self, user_id: int, name: str, kind: CategoryKind, exclude_id: int | None = None) -> bool:
        stmt = select(Category.id).where(
            Category.user_id == user_id,
            func.lower(Category.name) == name.strip().lower(),
            Category.kind == kind,
        )
        if exclude_id is not None:
            stmt = stmt.where(Category.id != exclude_id)
        return (await self.session.scalar(stmt.limit(1))) is not None

    def add(self, category: Category) -> Category:
        self.session.add(category)
        return category

    async def delete(self, category: Category) -> None:
        await self.session.delete(category)
