from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash
from pwdlib.exceptions import PwdlibError
from pwdlib.hashers.argon2 import Argon2Hasher
from pwdlib.hashers.bcrypt import BcryptHasher

from app.core.config import settings


class TokenError(Exception):
    """Токен невалиден, просрочен или имеет неверный тип."""


class TokenExpiredError(TokenError):
    """Подпись токена верна, но срок его действия истёк."""


# Новые хеши — Argon2. Bcrypt оставлен только для проверки хешей,
# созданных прежней реализацией (passlib + bcrypt).
password_hash = PasswordHash(
    (
        Argon2Hasher(),
        BcryptHasher(),
    )
)


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Проверяет пароль. Повреждённый/неизвестный формат хеша или ошибка
    хешера трактуются как неверный пароль, а не как 500.
    """

    try:
        return password_hash.verify(plain_password, hashed_password)
    except PwdlibError:
        return False


def create_access_token(data: dict) -> str:

    to_encode = data.copy()

    expire = datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update(
        {
            "exp": expire,
            "type": "access",
        }
    )

    return jwt.encode(
        to_encode, settings.SECRET_KEY.get_secret_value(), algorithm=settings.ALGORITHM
    )


def create_refresh_token(
    data: dict,
    expires_days: int | None = None,
) -> str:

    to_encode = data.copy()

    days = settings.REFRESH_TOKEN_EXPIRE_DAYS if expires_days is None else expires_days
    expire = datetime.now(UTC) + timedelta(days=days)

    to_encode.update(
        {
            "exp": expire,
            "type": "refresh",
        }
    )

    return jwt.encode(
        to_encode,
        settings.SECRET_KEY.get_secret_value(),
        algorithm=settings.ALGORITHM,
    )


def decode_token(
    token: str,
    expected_type: str = "access",
) -> dict:
    """
    Декодирует и проверяет JWT.

    Бросает TokenError, если токен просрочен, повреждён
    либо не соответствует ожидаемому типу (access/refresh).
    """

    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY.get_secret_value(),
            algorithms=[settings.ALGORITHM],
            options={"require": ["exp"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenExpiredError("Token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("Could not validate token") from exc

    if payload.get("type") != expected_type:
        raise TokenError("Invalid token type")

    return payload
