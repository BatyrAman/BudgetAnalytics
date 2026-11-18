from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.exceptions import RequestValidationError
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_db, limit_per_ip, limit_per_user
from app.core.errors import ErrorResponse
from app.core.rate_limit import (
    LOGIN_PER_ACCOUNT,
    LOGIN_PER_IP,
    PASSWORD_CHANGE_PER_USER,
    REFRESH_PER_IP,
    REGISTER_PER_IP,
    RateLimiter,
    get_rate_limiter,
    hashed,
)
from app.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    MessageResponse,
    RefreshTokenRequest,
    RefreshTokenResponse,
    RegisterRequest,
)
from app.schemas.user import UserResponse
from app.services.auth import AuthService, TokenPair

router = APIRouter(prefix="/auth", tags=["Auth"])

_UNAUTHORIZED: dict[int | str, dict[str, Any]] = {401: {"model": ErrorResponse}}


def _pair(tokens: TokenPair) -> RefreshTokenResponse:
    return RefreshTokenResponse(
        access_token=tokens.access_token, refresh_token=tokens.refresh_token
    )


@router.post(
    "/register",
    response_model=RefreshTokenResponse,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"model": ErrorResponse}, 429: {"model": ErrorResponse}},
    dependencies=[Depends(limit_per_ip(REGISTER_PER_IP))],
)
async def register(
    payload: RegisterRequest, db: AsyncSession = Depends(get_db)
) -> RefreshTokenResponse:
    """Creates a user (password 8–128 characters, e-mail stored lower-case)
    and signs them in."""

    service = AuthService(db)
    user = await service.register(payload.full_name, payload.email, payload.password)
    tokens = await service.issue_tokens(user)
    await db.commit()
    return _pair(tokens)


@router.post(
    "/login",
    response_model=RefreshTokenResponse,
    responses={**_UNAUTHORIZED, 429: {"model": ErrorResponse}},
    dependencies=[Depends(limit_per_ip(LOGIN_PER_IP))],
)
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
    limiter: RateLimiter = Depends(get_rate_limiter),
) -> RefreshTokenResponse:
    """Limited per IP and per account (e-mail), so neither one fast attacker
    nor a botnet spraying one account can guess passwords quickly."""

    return await _login(payload, db, limiter)


@router.post(
    "/token",
    response_model=RefreshTokenResponse,
    responses={**_UNAUTHORIZED, 429: {"model": ErrorResponse}},
    dependencies=[Depends(limit_per_ip(LOGIN_PER_IP))],
)
async def login_oauth2_form(
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
    limiter: RateLimiter = Depends(get_rate_limiter),
) -> RefreshTokenResponse:
    """OAuth2 password flow (``application/x-www-form-urlencoded``) for
    Swagger UI's **Authorize** and standard OAuth2 clients: ``username`` is the
    e-mail. Same checks and limits as ``/login``; applications should use the
    JSON ``/login``."""

    try:
        payload = LoginRequest(email=form.username, password=form.password)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors(include_input=False)) from None
    return await _login(payload, db, limiter)


async def _login(
    payload: LoginRequest, db: AsyncSession, limiter: RateLimiter
) -> RefreshTokenResponse:
    await limiter.check(LOGIN_PER_ACCOUNT, hashed(payload.email))
    service = AuthService(db)
    user = await service.authenticate(payload.email, payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password"
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user")
    tokens = await service.issue_tokens(user)
    await db.commit()
    return _pair(tokens)


@router.post(
    "/refresh",
    response_model=RefreshTokenResponse,
    responses=_UNAUTHORIZED,
    dependencies=[Depends(limit_per_ip(REFRESH_PER_IP))],
)
async def refresh_token(
    payload: RefreshTokenRequest, db: AsyncSession = Depends(get_db)
) -> RefreshTokenResponse:
    """Rotates the refresh token: returns a new access token AND a new refresh
    token; the presented refresh token can no longer be used."""

    tokens = await AuthService(db).rotate(payload.refresh_token)
    await db.commit()
    return _pair(tokens)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_UNAUTHORIZED,
    dependencies=[Depends(limit_per_ip(REFRESH_PER_IP))],
)
async def logout(payload: RefreshTokenRequest, db: AsyncSession = Depends(get_db)) -> None:
    """Ends the session of this refresh token (idempotent). Access tokens
    already issued remain valid until they expire; use /auth/logout-all to
    invalidate them immediately."""

    await AuthService(db).logout(payload.refresh_token)
    await db.commit()


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT, responses=_UNAUTHORIZED)
async def logout_all(
    current_user: User = Depends(get_current_active_user), db: AsyncSession = Depends(get_db)
) -> None:
    """Ends every session of the user and invalidates all their access tokens."""

    await AuthService(db).logout_all(current_user)
    await db.commit()


@router.post(
    "/change-password",
    response_model=MessageResponse,
    responses={**_UNAUTHORIZED, 400: {"model": ErrorResponse}},
    dependencies=[Depends(limit_per_user(PASSWORD_CHANGE_PER_USER))],
)
async def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Changes the password and signs out every session (sign in again)."""

    await AuthService(db).change_password(current_user, payload.old_password, payload.new_password)
    await db.commit()
    return MessageResponse(message="Password updated successfully")


@router.get("/me", response_model=UserResponse, responses=_UNAUTHORIZED)
async def get_me(current_user: User = Depends(get_current_active_user)) -> User:
    return current_user
