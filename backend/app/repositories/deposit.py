from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deposit import Deposit


class DepositRepository:
    """User-owned deposits. Every method requires the owner's ``user_id``."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_for_user(self, deposit_id: int, user_id: int) -> Deposit | None:
        return await self.db.scalar(
            select(Deposit).where(Deposit.id == deposit_id, Deposit.user_id == user_id)
        )

    async def list_for_user(self, user_id: int) -> list[Deposit]:
        result = await self.db.scalars(
            select(Deposit).where(Deposit.user_id == user_id).order_by(Deposit.start_date.desc())
        )
        return list(result)

    def add(self, deposit: Deposit) -> None:
        self.db.add(deposit)
