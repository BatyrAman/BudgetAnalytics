"""
Пароли и JWT.

* Пароли — bcrypt (напрямую, без passlib), максимум 72 байта.
* JWT — PyJWT (python-jose не поддерживается и имеет CVE-2024-33663/33664).
  Обязательные claims: sub, type, exp, iat, jti. Алгоритм фиксирован
  настройкой; "none" и чужие алгоритмы отвергаются.
* access: короткоживущий (по умолчанию 15 минут), в заголовке
  Authorization, содержит ver — версию токенов пользователя.
* refresh: в httpOnly-cookie, одноразовый (ротация), учитывается в
  таблице refresh_tokens.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import settings


class TokenError(Exception):
    """Токен невалиден, просрочен или имеет неверный тип."""


BCRYPT_MAX_BYTES = 72

# Хеш для выравнивания времени ответа, когда пользователь не найден
# (не даём по времени отличить «нет такого email» от «неверный пароль»).
_DUMMY_HASH = bcrypt.hashpw(b"timing-equalizer", bcrypt.gensalt(settings.BCRYPT_ROUNDS)).decode("ascii")


def hash_password(password: str) -> str:
    # passlib 1.7 несовместим с bcrypt>=4.1 (падает на detect_wrap_bug),
    # поэтому используем bcrypt напрямую. Формат хеша прежний ($2b$).
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(settings.BCRYPT_ROUNDS)).decode("ascii")


def verify_password(plain_password: str, hashed_password: str | None) -> bool:
    secret = plain_password.encode("utf-8")
    if hashed_password is None:
        bcrypt.checkpw(b"timing-equalizer", _DUMMY_HASH.encode("ascii"))
        return False
    if len(secret) > BCRYPT_MAX_BYTES:
        return False
    try:
        return bcrypt.checkpw(secret, hashed_password.encode("ascii"))
    except ValueError:
        return False


@dataclass(frozen=True, slots=True)
class IssuedToken:
    token: str
    jti: str
    expires_at: datetime


def _encode(claims: dict, lifetime: timedelta) -> IssuedToken:
    now = datetime.now(timezone.utc)
    jti = secrets.token_urlsafe(24)
    expires_at = now + lifetime
    payload = {**claims, "iat": now, "exp": expires_at, "jti": jti}
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return IssuedToken(token=token, jti=jti, expires_at=expires_at)


def create_access_token(user_id: int, token_version: int = 0) -> IssuedToken:
    return _encode(
        {"sub": str(user_id), "type": "access", "ver": token_version},
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(user_id: int, family_id: str) -> IssuedToken:
    return _encode(
        {"sub": str(user_id), "type": "refresh", "fam": family_id},
        timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def new_family_id() -> str:
    return secrets.token_urlsafe(24)


def decode_token(token: str, expected_type: str = "access") -> dict:
    """
    Декодирует и проверяет JWT.

    Бросает TokenError, если токен просрочен, повреждён
    либо не соответствует ожидаемому типу (access/refresh).
    """

    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"require": ["exp", "iat", "sub", "jti", "type"]},
        )
    except jwt.PyJWTError as exc:
        raise TokenError("Could not validate token") from exc

    if payload.get("type") != expected_type:
        raise TokenError("Invalid token type")

    return payload
