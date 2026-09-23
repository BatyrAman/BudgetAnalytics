from __future__ import annotations

from typing import Any, Generic, TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class Repository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def flush(self) -> None:
        await self.session.flush()


class OwnedRepository(Repository, Generic[ModelT]):
    """CRUD для сущностей, у которых есть колонка user_id."""

    model: type[ModelT]

    def _owned(self, user_id: int) -> Select:
        return select(self.model).where(self.model.user_id == user_id)

    async def get_owned(self, entity_id: int, user_id: int, *options: Any) -> ModelT | None:
        stmt = self._owned(user_id).where(self.model.id == entity_id)
        if options:
            stmt = stmt.options(*options)
        return await self.session.scalar(stmt)

    async def count_owned(self, user_id: int, *conditions: Any) -> int:
        stmt = select(func.count(self.model.id)).where(self.model.user_id == user_id, *conditions)
        return int(await self.session.scalar(stmt) or 0)

    async def list_owned(
        self,
        user_id: int,
        *conditions: Any,
        order_by: Any = None,
        limit: int | None = None,
        offset: int | None = None,
        options: tuple = (),
    ) -> list[ModelT]:
        stmt = self._owned(user_id).where(*conditions)
        if options:
            stmt = stmt.options(*options)
        if order_by is not None:
            stmt = stmt.order_by(*order_by) if isinstance(order_by, (list, tuple)) else stmt.order_by(order_by)
        if limit is not None:
            stmt = stmt.limit(limit)
        if offset:
            stmt = stmt.offset(offset)
        result = await self.session.scalars(stmt)
        return list(result.all())

    def add(self, entity: ModelT) -> ModelT:
        self.session.add(entity)
        return entity

    async def delete(self, entity: ModelT) -> None:
        await self.session.delete(entity)
