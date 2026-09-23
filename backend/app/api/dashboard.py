from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.core.errors import ERROR_RESPONSES
from app.schemas.dashboard import DashboardResponse
from app.services.dashboard import DashboardService

router = APIRouter(prefix="/dashboard", tags=["Dashboard"], responses=ERROR_RESPONSES)


@router.get("", response_model=DashboardResponse)
async def get_dashboard(user: CurrentUser, db: DbSession):
    """
    Главный экран: баланс, сводка месяца, последние операции,
    топ категорий расходов, бюджеты и вклады.
    """

    return await DashboardService(db).get_dashboard(user.id)
