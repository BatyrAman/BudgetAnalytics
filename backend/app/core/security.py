from datetime import datetime
from datetime import timedelta
from datetime import timezone

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings


class TokenError(Exception):
    """Токен невалиден, просрочен или имеет неверный тип."""


# bcrypt учитывает только первые 72 байта пароля; длиннее —
# отклоняем на уровне схем (см. schemas/auth.py).
BCRYPT_MAX_BYTES = 72


def hash_password(password: str) -> str:
    # passlib 1.7 несовместим с bcrypt>=4.1 (падает на detect_wrap_bug),
    # поэтому используем bcrypt напрямую. Формат хеша прежний ($2b$).
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(
    plain_password: str,
    hashed_password: str
) -> bool:
    secret = plain_password.encode("utf-8")
    if len(secret) > BCRYPT_MAX_BYTES:
        return False
    try:
        return bcrypt.checkpw(secret, hashed_password.encode("ascii"))
    except ValueError:
        return False


def create_access_token(
    data: dict
) -> str:

    to_encode = data.copy()

    expire = datetime.now(
        timezone.utc
    ) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )

    to_encode.update(
        {
            "exp": expire,
            "type": "access",
        }
    )

    return jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )


def create_refresh_token(
    data: dict,
    expires_days: int = 7,
) -> str:

    to_encode = data.copy()

    expire = datetime.now(timezone.utc) + timedelta(days=expires_days)

    to_encode.update(
        {
            "exp": expire,
            "type": "refresh",
        }
    )

    return jwt.encode(
        to_encode,
        settings.SECRET_KEY,
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
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
    except JWTError as exc:
        raise TokenError("Could not validate token") from exc

    if payload.get("type") != expected_type:
        raise TokenError("Invalid token type")

    return payload