from __future__ import annotations

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import TokenError, decode_token
from app.models.user import User

__all__ = [
    "get_db",
    "get_current_user",
    "get_current_active_user",
    "PaginationParams",
]

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_PREFIX}/auth/login",
    auto_error=False,
)


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Достаёт пользователя из access-токена.

    Бросает 401, если токен отсутствует, просрочен, повреждён
    либо пользователь по нему не найден.
    """

    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if token is None:
        raise credentials_error

    try:
        payload = decode_token(token, expected_type="access")
    except TokenError:
        raise credentials_error

    user_id = payload.get("sub")

    if user_id is None:
        raise credentials_error

    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        raise credentials_error

    user = await db.scalar(
        select(User).where(User.id == user_id)
    )

    if user is None:
        raise credentials_error

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:

    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )

    return current_user


class PaginationParams:
    """
    Общая пагинация для списковых эндпоинтов.

    limit/offset вместо page/size, чтобы было удобно
    комбинировать с SQLAlchemy .limit().offset().
    """

    def __init__(
        self,
        limit: int = Query(default=20, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ):
        self.limit = limit
        self.offset = offset
