from __future__ import annotations

from sqlalchemy import select

from app.models.user import User
from app.repositories.base import Repository


class UserRepository(Repository):
    async def get(self, user_id: int) -> User | None:
        return await self.session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        return await self.session.scalar(select(User).where(User.email == email.lower()))

    def add(self, user: User) -> User:
        self.session.add(user)
        return user

    async def delete(self, user: User) -> None:
        await self.session.delete(user)
