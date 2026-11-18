from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account


class AccountRepository:
    """User-owned accounts. Every method requires the owner's ``user_id``."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_for_user(self, account_id: int, user_id: int) -> Account | None:
        return await self.db.scalar(
            select(Account).where(Account.id == account_id, Account.user_id == user_id)
        )

    async def list_for_user(self, user_id: int, *, include_archived: bool = False) -> list[Account]:
        stmt = select(Account).where(Account.user_id == user_id)
        if not include_archived:
            stmt = stmt.where(Account.is_archived.is_(False))
        result = await self.db.scalars(stmt.order_by(Account.name))
        return list(result)

    def add(self, account: Account) -> None:
        self.db.add(account)
