from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_db
from app.core.security import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    MessageResponse,
    RefreshTokenRequest,
    RefreshTokenResponse,
    RegisterRequest,
    Token,
)
from app.schemas.user import UserResponse

router = APIRouter(prefix="/auth", tags=["Auth"])


def _issue_tokens(user: User) -> RefreshTokenResponse:
    payload = {"sub": str(user.id)}

    return RefreshTokenResponse(
        access_token=create_access_token(payload),
        refresh_token=create_refresh_token(payload),
    )


@router.post(
    "/register",
    response_model=RefreshTokenResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    payload: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> RefreshTokenResponse:
    """
    Регистрация нового пользователя.

    Возвращает пару access/refresh токенов, чтобы фронтенд
    мог сразу авторизовать пользователя без отдельного логина.
    """

    existing = await db.scalar(
        select(User).where(User.email == payload.email)
    )

    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with this email already exists",
        )

    user = User(
        full_name=payload.full_name,
        email=payload.email,
        hashed_password=hash_password(payload.password),
    )

    db.add(user)
    await db.commit()
    await db.refresh(user)

    return _issue_tokens(user)


@router.post(
    "/login",
    response_model=RefreshTokenResponse,
)
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> RefreshTokenResponse:

    user = await db.scalar(
        select(User).where(User.email == payload.email)
    )

    invalid_credentials = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Incorrect email or password",
    )

    if user is None or not verify_password(
        payload.password,
        user.hashed_password,
    ):
        raise invalid_credentials

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )

    return _issue_tokens(user)


@router.post(
    "/refresh",
    response_model=Token,
)
async def refresh_token(
    payload: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
) -> Token:
    """
    Выдаёт новый access-токен по действующему refresh-токену.
    """

    invalid_token = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired refresh token",
    )

    try:
        decoded = decode_token(
            payload.refresh_token,
            expected_type="refresh",
        )
    except TokenError:
        raise invalid_token

    user_id = decoded.get("sub")

    if user_id is None:
        raise invalid_token

    user = await db.scalar(
        select(User).where(User.id == int(user_id))
    )

    if user is None or not user.is_active:
        raise invalid_token

    access_token = create_access_token({"sub": str(user.id)})

    return Token(access_token=access_token)


@router.post(
    "/change-password",
    response_model=MessageResponse,
)
async def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:

    if not verify_password(
        payload.old_password,
        current_user.hashed_password,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Old password is incorrect",
        )

    current_user.hashed_password = hash_password(payload.new_password)

    db.add(current_user)
    await db.commit()

    return MessageResponse(message="Password updated successfully")


@router.get(
    "/me",
    response_model=UserResponse,
)
async def get_me(
    current_user: User = Depends(get_current_active_user),
) -> User:
    return current_user
