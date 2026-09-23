from __future__ import annotations

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, DbSession, Pagination
from app.core.errors import ERROR_RESPONSES
from app.schemas.budget import (
    BudgetAlert,
    BudgetCreate,
    BudgetDetail,
    BudgetListResponse,
    BudgetProgress,
    BudgetResponse,
    BudgetStatistics,
    BudgetUpdate,
)
from app.services.budgets import BudgetService

router = APIRouter(prefix="/budgets", tags=["Budgets"], responses=ERROR_RESPONSES)


@router.post("", response_model=BudgetResponse, status_code=status.HTTP_201_CREATED)
async def create_budget(payload: BudgetCreate, user: CurrentUser, db: DbSession):
    return await BudgetService(db).create(user.id, payload)


@router.get("", response_model=BudgetListResponse)
async def list_budgets(user: CurrentUser, db: DbSession, pagination: Pagination):
    items, total = await BudgetService(db).list(user.id, pagination.limit, pagination.offset)
    return BudgetListResponse(items=items, total=total)


@router.get("/statistics", response_model=BudgetStatistics)
async def get_statistics(user: CurrentUser, db: DbSession):
    return await BudgetService(db).statistics(user.id)


@router.get("/progress", response_model=list[BudgetProgress])
async def get_progress(user: CurrentUser, db: DbSession):
    return await BudgetService(db).progress(user.id)


@router.get("/alerts", response_model=list[BudgetAlert])
async def get_alerts(user: CurrentUser, db: DbSession, threshold: float = Query(default=80.0, ge=0, le=1000)):
    """Бюджеты, использование которых превысило `threshold` % от лимита."""

    return await BudgetService(db).alerts(user.id, threshold)


@router.get("/{budget_id}", response_model=BudgetDetail)
async def get_budget(budget_id: int, user: CurrentUser, db: DbSession):
    return await BudgetService(db).get(budget_id, user.id)


@router.put("/{budget_id}", response_model=BudgetResponse)
async def update_budget(budget_id: int, payload: BudgetUpdate, user: CurrentUser, db: DbSession):
    return await BudgetService(db).update(budget_id, user.id, payload)


@router.delete("/{budget_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_budget(budget_id: int, user: CurrentUser, db: DbSession) -> None:
    await BudgetService(db).delete(budget_id, user.id)
