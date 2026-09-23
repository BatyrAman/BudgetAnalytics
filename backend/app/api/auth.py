from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Request, Response, status

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.core.errors import ERROR_RESPONSES, PermissionDeniedError
from app.core.rate_limit import rate_limit
from app.schemas.auth import (
    ChangePasswordRequest,
    DeleteAccountRequest,
    LoginRequest,
    MessageResponse,
    RefreshTokenRequest,
    RegisterRequest,
    Token,
)
from app.schemas.user import FinancialProfileResponse, FinancialProfileUpdate, UserResponse
from app.services.auth import AuthService, TokenPair
from app.services.profile import FinancialProfileService

router = APIRouter(prefix="/auth", tags=["Auth"], responses=ERROR_RESPONSES)

COOKIE_PATH = f"{settings.API_PREFIX}/auth"


def _set_refresh_cookie(response: Response, pair: TokenPair) -> None:
    response.set_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        value=pair.refresh_token,
        expires=pair.refresh_expires_at,
        path=COOKIE_PATH,
        domain=settings.REFRESH_COOKIE_DOMAIN,
        secure=settings.REFRESH_COOKIE_SECURE,
        httponly=True,
        samesite=settings.REFRESH_COOKIE_SAMESITE,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        path=COOKIE_PATH,
        domain=settings.REFRESH_COOKIE_DOMAIN,
        secure=settings.REFRESH_COOKIE_SECURE,
        httponly=True,
        samesite=settings.REFRESH_COOKIE_SAMESITE,
    )


def _token_response(response: Response, pair: TokenPair) -> Token:
    _set_refresh_cookie(response, pair)
    return Token(
        access_token=pair.access_token,
        expires_in=pair.access_expires_in,
        refresh_token=pair.refresh_token if settings.REFRESH_TOKEN_IN_BODY else None,
    )


async def verify_origin(request: Request) -> None:
    """
    CSRF-защита эндпоинтов, работающих по cookie (refresh/logout).

    Помимо SameSite=strict: если браузер прислал Origin, он обязан
    быть в списке CORS_ORIGINS. Запросы без Origin (мобильные и
    серверные клиенты) cookie не используют по умолчанию.
    """

    origin = request.headers.get("origin")
    if origin is not None and origin not in settings.cors_origins:
        raise PermissionDeniedError("Origin is not allowed", code="ORIGIN_NOT_ALLOWED")


def _refresh_from_request(request: Request, body: RefreshTokenRequest | None) -> str | None:
    token = request.cookies.get(settings.REFRESH_COOKIE_NAME)
    if token is None and settings.REFRESH_TOKEN_IN_BODY and body is not None:
        token = body.refresh_token
    return token


@router.post(
    "/register",
    response_model=Token,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("login", "LOGIN_RATE_LIMIT_PER_MINUTE"))],
)
async def register(payload: RegisterRequest, response: Response, db: DbSession) -> Token:
    """
    Регистрация. Возвращает access-токен; refresh-токен ставится
    в httpOnly-cookie (Path=/api/v1/auth, SameSite=strict).
    """

    pair = await AuthService(db).register(payload.full_name, payload.email, payload.password)
    return _token_response(response, pair)


@router.post(
    "/login",
    response_model=Token,
    dependencies=[Depends(rate_limit("login", "LOGIN_RATE_LIMIT_PER_MINUTE"))],
)
async def login(payload: LoginRequest, response: Response, db: DbSession) -> Token:
    pair = await AuthService(db).login(payload.email, payload.password)
    return _token_response(response, pair)


@router.post("/refresh", response_model=Token, dependencies=[Depends(verify_origin)])
async def refresh_token(
    request: Request,
    response: Response,
    db: DbSession,
    payload: RefreshTokenRequest | None = Body(default=None),
) -> Token:
    """
    Обменивает refresh-токен из cookie на новую пару (ротация).
    Повторное использование старого токена отзывает всю сессию.
    """

    pair = await AuthService(db).refresh(_refresh_from_request(request, payload))
    return _token_response(response, pair)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(verify_origin)])
async def logout(
    request: Request,
    response: Response,
    db: DbSession,
    payload: RefreshTokenRequest | None = Body(default=None),
) -> None:
    """Завершает текущую сессию: отзывает refresh-токен и удаляет cookie."""

    await AuthService(db).logout(_refresh_from_request(request, payload))
    _clear_refresh_cookie(response)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(response: Response, user: CurrentUser, db: DbSession) -> None:
    """Выход со всех устройств: отзывает все refresh- и access-токены."""

    await AuthService(db).logout_all(user)
    _clear_refresh_cookie(response)


@router.post("/change-password", response_model=MessageResponse)
async def change_password(
    payload: ChangePasswordRequest, response: Response, user: CurrentUser, db: DbSession
) -> MessageResponse:
    """Меняет пароль и завершает все сессии (нужно войти заново)."""

    await AuthService(db).change_password(user, payload.old_password, payload.new_password)
    _clear_refresh_cookie(response)
    return MessageResponse(message="Password updated successfully")


@router.get("/me", response_model=UserResponse)
async def get_me(user: CurrentUser):
    return user


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(payload: DeleteAccountRequest, response: Response, user: CurrentUser, db: DbSession) -> None:
    """Удаляет аккаунт и все данные пользователя без возможности восстановления."""

    await AuthService(db).delete_account(user, payload.password)
    _clear_refresh_cookie(response)


@router.get("/me/profile", response_model=FinancialProfileResponse)
async def get_profile(user: CurrentUser):
    return user


@router.put("/me/profile", response_model=FinancialProfileResponse)
async def update_profile(payload: FinancialProfileUpdate, user: CurrentUser, db: DbSession):
    """Финансовый профиль: заявленный доход, иждивенцы, город, согласие на обработку ПДн."""

    return await FinancialProfileService(db).update(user, payload)
