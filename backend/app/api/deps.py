from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Query
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.errors import AuthenticationError, PermissionDeniedError
from app.core.security import TokenError, decode_token
from app.models.user import User
from app.repositories.users import UserRepository

__all__ = [
    "get_db",
    "get_current_user",
    "get_current_active_user",
    "PaginationParams",
    "DbSession",
    "CurrentUser",
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

    401, если токен отсутствует, просрочен, повреждён
    либо пользователь по нему не найден.
    """

    if token is None:
        raise AuthenticationError()

    try:
        payload = decode_token(token, expected_type="access")
    except TokenError:
        raise AuthenticationError() from None

    try:
        user_id = int(payload.get("sub"))
    except (TypeError, ValueError):
        raise AuthenticationError() from None

    user = await UserRepository(db).get(user_id)
    # token_version отзывает все access-токены после смены пароля
    # или выхода со всех устройств.
    if user is None or payload.get("ver", 0) != user.token_version:
        raise AuthenticationError()

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:

    if not current_user.is_active:
        raise PermissionDeniedError("Inactive user", code="INACTIVE_USER")

    return current_user


DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_active_user)]


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


Pagination = Annotated[PaginationParams, Depends()]
