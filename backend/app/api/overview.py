from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_currency, get_current_active_user, get_db, get_timezone
from app.core.errors import ErrorResponse
from app.models.user import User
from app.schemas.reports import OverviewResponse
from app.services.finance import CurrencySpec
from app.services.overview import OverviewService

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get(
    "/overview",
    response_model=OverviewResponse,
    responses={401: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
async def get_overview(
    tz: ZoneInfo = Depends(get_timezone),
    currency: CurrencySpec = Depends(get_currency),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> OverviewResponse:
    """Financial overview for the current local month in one currency:
    account balances, monthly income/expenses, savings rate, budgets,
    deposits and indicators. Every number comes from the finance engine."""

    return await OverviewService(db).build(current_user.id, currency, tz)
