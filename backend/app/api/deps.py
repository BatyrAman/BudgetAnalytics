from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Depends, Query, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.errors import AuthenticationError, DomainValidationError, PermissionDeniedError
from app.core.rate_limit import API_PER_IP, RateLimiter, Rule, get_rate_limiter
from app.core.security import TokenError, TokenExpiredError, decode_token
from app.models.user import User
from app.repositories.currency import CurrencyRepository
from app.repositories.user import UserRepository
from app.services.finance import CurrencySpec

__all__ = [
    "get_db",
    "get_current_user",
    "get_current_active_user",
    "PaginationParams",
]

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_PREFIX}/auth/token",  # form-based OAuth2 flow (Swagger)
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

    credentials_message = "Could not validate credentials"

    if token is None:
        # No token at all: the generic ``unauthorized`` code (nothing was rejected).
        raise AuthenticationError(credentials_message)

    try:
        payload = decode_token(token, expected_type="access")
    except TokenExpiredError:
        raise AuthenticationError(credentials_message, code="token_expired") from None
    except TokenError:
        raise AuthenticationError(credentials_message, code="invalid_token") from None

    user_id = payload.get("sub")

    if user_id is None:
        raise AuthenticationError(credentials_message, code="invalid_token")

    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        raise AuthenticationError(credentials_message, code="invalid_token") from None

    user = await UserRepository(db).get_by_id(user_id)

    # ``ver`` must match: logout-all / password change bump token_version and
    # thereby invalidate every access token issued before.
    if user is None or payload.get("ver") != user.token_version:
        raise AuthenticationError(credentials_message, code="invalid_token")

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:

    if not current_user.is_active:
        raise PermissionDeniedError("Inactive user", code="inactive_user")

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


# ---------------------------------------------------------------- analytics params
DEFAULT_TIMEZONE = "Asia/Almaty"
MAX_PERIOD_DAYS = 5 * 366


def get_timezone(
    tz: str = Query(
        default=DEFAULT_TIMEZONE,
        max_length=64,
        description="IANA time zone used for day/month boundaries, e.g. Asia/Almaty",
    ),
) -> ZoneInfo:
    try:
        return ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        raise DomainValidationError("Unknown time zone", code="unknown_timezone") from None


async def get_currency(
    currency: str | None = Query(
        default=None,
        pattern=r"^[A-Z]{3}$",
        description="ISO 4217 code; defaults to the user's default currency",
    ),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> CurrencySpec:
    code = currency or current_user.default_currency_code
    spec = await CurrencyRepository(db).get_spec(code)
    if spec is None:
        raise DomainValidationError("Unknown currency", code="unknown_currency")
    return spec


@dataclass(frozen=True)
class DateRange:
    """Inclusive local dates ``date_from``..``date_to`` = the half-open instant
    interval [date_from 00:00, date_to + 1 day 00:00) in ``tz``."""

    date_from: date
    date_to: date
    tz: ZoneInfo

    @property
    def start(self) -> datetime:
        return datetime.combine(self.date_from, time.min, tzinfo=self.tz)

    @property
    def end(self) -> datetime:
        return datetime.combine(self.date_to + timedelta(days=1), time.min, tzinfo=self.tz)


def get_date_range(
    date_from: date | None = Query(default=None, description="First day (inclusive)"),
    date_to: date | None = Query(default=None, description="Last day (inclusive)"),
    tz: ZoneInfo = Depends(get_timezone),
) -> DateRange:
    """Defaults to the current calendar month in ``tz``."""

    today = datetime.now(tz).date()
    start = date_from or today.replace(day=1)
    if date_to is None:
        next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
        end = next_month - timedelta(days=1)
    else:
        end = date_to
    if end < start:
        raise DomainValidationError(
            "date_to must not be before date_from", code="invalid_date_range"
        )
    if (end - start).days >= MAX_PERIOD_DAYS:
        raise DomainValidationError("The period must not exceed 5 years", code="period_too_long")
    return DateRange(start, end, tz)


def parse_month(month: str | None, tz: ZoneInfo) -> date:
    """``YYYY-MM`` -> first day of that month; default: current month in ``tz``."""

    if month is None:
        return datetime.now(tz).date().replace(day=1)
    try:
        return datetime.strptime(month, "%Y-%m").date()
    except ValueError:
        raise DomainValidationError("month must be YYYY-MM", code="invalid_month") from None


# ---------------------------------------------------------------- rate limiting
def client_ip(request: Request) -> str:
    """Set by uvicorn from trusted proxies only (--forwarded-allow-ips)."""

    return request.client.host if request.client else "unknown"


async def limit_api_per_ip(
    request: Request, limiter: RateLimiter = Depends(get_rate_limiter)
) -> None:
    await limiter.check(API_PER_IP, client_ip(request))


def limit_per_ip(rule: Rule) -> Callable[..., Awaitable[None]]:
    async def dependency(
        request: Request, limiter: RateLimiter = Depends(get_rate_limiter)
    ) -> None:
        await limiter.check(rule, client_ip(request))

    return dependency


def limit_per_user(rule: Rule) -> Callable[..., Awaitable[None]]:
    async def dependency(
        current_user: User = Depends(get_current_active_user),
        limiter: RateLimiter = Depends(get_rate_limiter),
    ) -> None:
        await limiter.check(rule, str(current_user.id))

    return dependency
