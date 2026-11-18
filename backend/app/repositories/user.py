from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, user_id: int) -> User | None:
        return await self.db.scalar(select(User).where(User.id == user_id))

    async def get_by_email(self, email: str) -> User | None:
        """Case-insensitive lookup (emails are stored lower-case since this
        release; older rows may be mixed-case)."""

        return await self.db.scalar(select(User).where(func.lower(User.email) == email.lower()))

    def add(self, user: User) -> None:
        self.db.add(user)
