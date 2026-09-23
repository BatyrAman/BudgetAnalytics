from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.models.bank import Bank
from app.repositories.base import Repository


class BankRepository(Repository):
    """Справочник банков — общий, без user_id."""

    async def get(self, bank_id: int) -> Bank | None:
        return await self.session.get(Bank, bank_id)

    async def list(self) -> list[Bank]:
        return list((await self.session.scalars(select(Bank).order_by(Bank.name))).all())

    async def count(self) -> int:
        return int(await self.session.scalar(select(func.count(Bank.id))) or 0)

    async def get_or_create(self, name: str) -> Bank:
        # INSERT ... ON CONFLICT безопасен при параллельных импортах.
        await self.session.execute(
            insert(Bank).values(name=name).on_conflict_do_nothing(index_elements=[Bank.name])
        )
        return await self.session.scalar(select(Bank).where(Bank.name == name))
