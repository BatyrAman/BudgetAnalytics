"""
Аутентификация: регистрация, вход, ротация refresh-токенов, выход.

Ротация: каждый refresh-токен одноразовый. При обмене старый
помечается revoked + replaced_by, выдаётся новый в той же «семье».
Повторное предъявление уже использованного токена = признак кражи:
отзывается вся семья (все устройства этой сессии входа).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthenticationError, ConflictError, PermissionDeniedError
from app.core.security import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    new_family_id,
    verify_password,
)
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.repositories.refresh_tokens import RefreshTokenRepository
from app.repositories.users import UserRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TokenPair:
    access_token: str
    access_expires_in: int
    refresh_token: str
    refresh_expires_at: datetime


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.tokens = RefreshTokenRepository(session)

    async def _find_by_email(self, email: str) -> User | None:
        return await self.session.scalar(
            select(User).where(func.lower(User.email) == email.strip().lower()).limit(1)
        )

    async def _issue(self, user: User, family_id: str | None = None) -> TokenPair:
        access = create_access_token(user.id, user.token_version)
        refresh = create_refresh_token(user.id, family_id or new_family_id())
        payload = decode_token(refresh.token, "refresh")
        self.tokens.add(
            RefreshToken(
                user_id=user.id,
                jti=refresh.jti,
                family_id=payload["fam"],
                expires_at=refresh.expires_at,
            )
        )
        await self.session.flush()
        lifetime = int((access.expires_at - datetime.now(timezone.utc)).total_seconds())
        return TokenPair(access.token, lifetime, refresh.token, refresh.expires_at)

    async def register(self, full_name: str, email: str, password: str) -> TokenPair:
        if await self._find_by_email(email) is not None:
            raise ConflictError("User with this email already exists", code="EMAIL_TAKEN")
        user = self.users.add(
            User(full_name=full_name.strip(), email=email.strip().lower(), hashed_password=hash_password(password))
        )
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError("User with this email already exists", code="EMAIL_TAKEN") from exc
        pair = await self._issue(user)
        await self.session.commit()
        return pair

    async def login(self, email: str, password: str) -> TokenPair:
        user = await self._find_by_email(email)
        if not verify_password(password, user.hashed_password if user else None) or user is None:
            raise AuthenticationError("Incorrect email or password", code="INVALID_CREDENTIALS")
        if not user.is_active:
            raise PermissionDeniedError("Inactive user", code="INACTIVE_USER")
        pair = await self._issue(user)
        await self.session.commit()
        return pair

    async def refresh(self, token: str | None) -> TokenPair:
        invalid = AuthenticationError("Invalid or expired refresh token", code="INVALID_REFRESH_TOKEN")
        if not token:
            raise invalid
        try:
            payload = decode_token(token, "refresh")
            user_id = int(payload["sub"])
        except (TokenError, KeyError, TypeError, ValueError):
            raise invalid

        now = datetime.now(timezone.utc)
        stored = await self.tokens.get_for_update(payload["jti"])
        if stored is None or stored.user_id != user_id or stored.expires_at <= now:
            raise invalid

        if stored.revoked_at is not None:
            # Повторное использование — отзываем всю цепочку.
            await self.tokens.revoke_family(user_id, stored.family_id, now)
            await self.session.commit()
            logger.warning("Refresh token reuse detected for user %s; family revoked", user_id)
            raise AuthenticationError("Refresh token reuse detected", code="REFRESH_TOKEN_REUSED")

        user = await self.users.get(user_id)
        if user is None or not user.is_active:
            raise invalid

        pair = await self._issue(user, stored.family_id)
        stored.revoked_at = now
        stored.replaced_by = decode_token(pair.refresh_token, "refresh")["jti"]
        await self.session.commit()
        return pair

    async def logout(self, token: str | None) -> None:
        if not token:
            return
        try:
            payload = decode_token(token, "refresh")
        except TokenError:
            return
        stored = await self.tokens.get_for_update(payload["jti"])
        if stored is not None:
            await self.tokens.revoke_family(stored.user_id, stored.family_id, datetime.now(timezone.utc))
            await self.session.commit()

    async def logout_all(self, user: User) -> None:
        await self.tokens.revoke_all(user.id, datetime.now(timezone.utc))
        user.token_version += 1
        await self.session.commit()

    async def change_password(self, user: User, old_password: str, new_password: str) -> None:
        if not verify_password(old_password, user.hashed_password):
            raise AuthenticationError("Old password is incorrect", code="INVALID_CREDENTIALS", status_code=400)
        user.hashed_password = hash_password(new_password)
        # Все сессии, кроме новой после повторного входа, завершаются.
        await self.tokens.revoke_all(user.id, datetime.now(timezone.utc))
        user.token_version += 1
        await self.session.commit()

    async def delete_account(self, user: User, password: str) -> None:
        if not verify_password(password, user.hashed_password):
            raise AuthenticationError("Password is incorrect", code="INVALID_CREDENTIALS", status_code=400)
        # Все пользовательские данные удаляются каскадом (FK ON DELETE CASCADE).
        await self.users.delete(user)
        await self.session.commit()
