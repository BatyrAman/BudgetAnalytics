from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update

from app.models.refresh_token import RefreshToken
from app.repositories.base import Repository


class RefreshTokenRepository(Repository):
    def add(self, token: RefreshToken) -> RefreshToken:
        self.session.add(token)
        return token

    async def get_for_update(self, jti: str) -> RefreshToken | None:
        return await self.session.scalar(
            select(RefreshToken).where(RefreshToken.jti == jti).with_for_update()
        )

    async def revoke_family(self, user_id: int, family_id: str, now: datetime) -> None:
        await self.session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.family_id == family_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )

    async def revoke_all(self, user_id: int, now: datetime) -> None:
        await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
