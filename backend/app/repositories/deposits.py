from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app.models.bank import Bank
from app.models.deposit import Deposit
from app.repositories.base import OwnedRepository


class DepositRepository(OwnedRepository[Deposit]):
    model = Deposit

    async def list_with_bank(self, user_id: int) -> list[Deposit]:
        return await self.list_owned(
            user_id, order_by=Deposit.start_date.desc(), options=(joinedload(Deposit.bank),)
        )

    async def get_with_bank(self, deposit_id: int, user_id: int) -> Deposit | None:
        return await self.get_owned(deposit_id, user_id, joinedload(Deposit.bank))

    async def sum_by_bank(self, user_id: int) -> list[tuple[str, object]]:
        total = func.sum(Deposit.amount)
        stmt = (
            select(Bank.name, total)
            .join(Bank, Bank.id == Deposit.bank_id)
            .where(Deposit.user_id == user_id)
            .group_by(Bank.name)
            .order_by(total.desc())
        )
        return [tuple(row) for row in (await self.session.execute(stmt)).all()]
