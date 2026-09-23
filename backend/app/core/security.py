from datetime import datetime
from datetime import timedelta
from datetime import timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings


class TokenError(Exception):
    """Токен невалиден, просрочен или имеет неверный тип."""


pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(
    plain_password: str,
    hashed_password: str
) -> bool:
    return pwd_context.verify(
        plain_password,
        hashed_password
    )


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