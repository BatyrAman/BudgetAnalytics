"""Authentication use cases: registration, login, token rotation, logout.

TOKENS
* Access token (JWT, ``ACCESS_TOKEN_EXPIRE_MINUTES``): ``sub`` = user id,
  ``ver`` = the user's ``token_version``. Stateless; becomes invalid as soon
  as ``token_version`` changes (logout-all, password change).
* Refresh token (JWT, ``REFRESH_TOKEN_EXPIRE_DAYS``): ``sub``, ``jti``,
  ``fam``. Its ``jti`` is stored server-side. Every refresh ROTATES it
  (old one revoked, new one issued in the same family). Presenting a revoked
  refresh token revokes the whole family (reuse detection).
* Logout revokes the refresh-token family of the presented token; access
  tokens already issued stay valid until they expire (short-lived). Use
  logout-all to invalidate everything immediately.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError, AuthenticationError, ConflictError
from app.core.security import (
    TokenError,
    TokenExpiredError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.repositories.refresh_token import RefreshTokenRepository
from app.repositories.user import UserRepository

_INVALID_REFRESH = "Invalid or expired refresh token"


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str


def _now() -> datetime:
    return datetime.now(UTC)


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.users = UserRepository(db)
        self.tokens = RefreshTokenRepository(db)

    # ------------------------------------------------------------ users
    async def register(self, full_name: str, email: str, password: str) -> User:
        if await self.users.get_by_email(email) is not None:
            raise ConflictError("User with this email already exists", code="email_taken")
        user = User(
            full_name=full_name, email=email.lower(), hashed_password=hash_password(password)
        )
        self.users.add(user)
        await self.db.flush()
        return user

    async def authenticate(self, email: str, password: str) -> User | None:
        user = await self.users.get_by_email(email)
        if user is None:
            # Spend comparable time so unknown e-mails are not detectable by timing.
            verify_password(password, _DUMMY_HASH)
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user

    async def change_password(self, user: User, old_password: str, new_password: str) -> None:
        if not verify_password(old_password, user.hashed_password):
            raise AppError("Old password is incorrect", code="wrong_password")  # 400, as before
        user.hashed_password = hash_password(new_password)
        await self._invalidate_all_sessions(user)

    # ------------------------------------------------------------ tokens
    async def issue_tokens(self, user: User, family_id: str | None = None) -> TokenPair:
        jti = str(uuid.uuid4())
        family = family_id or str(uuid.uuid4())
        self.tokens.add(
            RefreshToken(
                jti=jti,
                family_id=family,
                user_id=user.id,
                expires_at=_now() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
            )
        )
        await self.db.flush()
        return TokenPair(
            access_token=create_access_token({"sub": str(user.id), "ver": user.token_version}),
            refresh_token=create_refresh_token({"sub": str(user.id), "jti": jti, "fam": family}),
        )

    async def _load_refresh(self, refresh_token: str) -> tuple[RefreshToken, dict[str, object]]:
        try:
            payload = decode_token(refresh_token, expected_type="refresh")
        except TokenExpiredError:
            raise AuthenticationError(_INVALID_REFRESH, code="token_expired") from None
        except TokenError:
            raise AuthenticationError(_INVALID_REFRESH, code="invalid_token") from None
        jti = payload.get("jti")
        if not isinstance(jti, str):
            # issued before rotation existed
            raise AuthenticationError(_INVALID_REFRESH, code="invalid_token")
        record = await self.tokens.get_for_update(jti)
        if record is None or str(record.user_id) != payload.get("sub"):
            raise AuthenticationError(_INVALID_REFRESH, code="invalid_token")
        return record, payload

    async def rotate(self, refresh_token: str) -> TokenPair:
        record, _ = await self._load_refresh(refresh_token)
        now = _now()
        if record.revoked_at is not None:
            # Reuse of a rotated/revoked token: assume theft, end the session family.
            await self.tokens.revoke_family(record.family_id, now)
            await self.db.commit()
            raise AuthenticationError(_INVALID_REFRESH, code="invalid_token")
        if record.expires_at <= now:
            raise AuthenticationError(_INVALID_REFRESH, code="token_expired")

        user = await self.users.get_by_id(record.user_id)
        if user is None or not user.is_active:
            raise AuthenticationError(_INVALID_REFRESH, code="invalid_token")

        record.revoked_at = now
        return await self.issue_tokens(user, family_id=record.family_id)

    async def logout(self, refresh_token: str) -> None:
        """Idempotent: logging out an already revoked session succeeds."""

        record, _ = await self._load_refresh(refresh_token)
        await self.tokens.revoke_family(record.family_id, _now())

    async def logout_all(self, user: User) -> None:
        await self._invalidate_all_sessions(user)

    async def _invalidate_all_sessions(self, user: User) -> None:
        await self.tokens.revoke_all_for_user(user.id, _now())
        user.token_version = user.token_version + 1


_DUMMY_HASH = hash_password("timing-equalizer-not-a-real-password")
