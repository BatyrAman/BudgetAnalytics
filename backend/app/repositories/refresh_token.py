from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.refresh_token import RefreshToken


class RefreshTokenRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def add(self, token: RefreshToken) -> None:
        self.db.add(token)

    async def get_for_update(self, jti: str) -> RefreshToken | None:
        """Row-locked read so two concurrent refreshes of the same token are
        serialized (the second one sees it revoked)."""

        return await self.db.scalar(
            select(RefreshToken).where(RefreshToken.jti == jti).with_for_update()
        )

    async def revoke_family(self, family_id: str, now: datetime) -> None:
        await self.db.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )

    async def revoke_all_for_user(self, user_id: int, now: datetime) -> None:
        await self.db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
