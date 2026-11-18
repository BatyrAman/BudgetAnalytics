from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_db, get_timezone
from app.core.errors import ErrorResponse
from app.models.user import User
from app.schemas.goals import GoalCreate, GoalResponse, GoalUpdate
from app.services.goals import GoalService, to_response

router = APIRouter(prefix="/goals", tags=["Financial goals"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorResponse},
    401: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}


def _today(tz: ZoneInfo) -> date:
    return datetime.now(tz).date()


@router.get("", response_model=list[GoalResponse], responses={401: _ERRORS[401]})
async def list_goals(
    tz: ZoneInfo = Depends(get_timezone),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> list[GoalResponse]:
    today = _today(tz)
    return [to_response(g, today) for g in await GoalService(db).list(current_user.id)]


@router.post(
    "", response_model=GoalResponse, status_code=status.HTTP_201_CREATED, responses=_ERRORS
)
async def create_goal(
    payload: GoalCreate,
    tz: ZoneInfo = Depends(get_timezone),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> GoalResponse:
    """A savings goal. ``saved_amount`` is entered by the user (it is not
    inferred from cash flow). Names are unique per user (409)."""

    goal = await GoalService(db).create(payload, current_user)
    await db.commit()
    return to_response(goal, _today(tz))


@router.get("/{goal_id}", response_model=GoalResponse, responses=_ERRORS)
async def get_goal(
    goal_id: int,
    tz: ZoneInfo = Depends(get_timezone),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> GoalResponse:
    return to_response(await GoalService(db).get(goal_id, current_user.id), _today(tz))


@router.patch("/{goal_id}", response_model=GoalResponse, responses=_ERRORS)
async def update_goal(
    goal_id: int,
    payload: GoalUpdate,
    tz: ZoneInfo = Depends(get_timezone),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> GoalResponse:
    goal = await GoalService(db).update(goal_id, payload, current_user.id)
    await db.commit()
    return to_response(goal, _today(tz))


@router.delete("/{goal_id}", status_code=status.HTTP_204_NO_CONTENT, responses=_ERRORS)
async def delete_goal(
    goal_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await GoalService(db).delete(goal_id, current_user.id)
    await db.commit()
