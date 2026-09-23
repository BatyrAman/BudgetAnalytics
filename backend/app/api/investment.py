from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DbSession, Pagination
from app.core.errors import ERROR_RESPONSES
from app.schemas.deposit import (
    DepositChartItem,
    DepositCreate,
    DepositDetail,
    DepositForecast,
    DepositListResponse,
    DepositResponse,
    DepositStatistics,
    DepositUpdate,
)
from app.services.deposits import DepositService

router = APIRouter(prefix="/investments", tags=["Investments"], responses=ERROR_RESPONSES)


@router.post("", response_model=DepositResponse, status_code=status.HTTP_201_CREATED)
async def create_deposit(payload: DepositCreate, user: CurrentUser, db: DbSession):
    return await DepositService(db).create(user.id, payload)


@router.get("", response_model=DepositListResponse)
async def list_deposits(user: CurrentUser, db: DbSession, pagination: Pagination):
    items, total = await DepositService(db).list(user.id, pagination.limit, pagination.offset)
    return DepositListResponse(items=items, total=total)


@router.get("/statistics", response_model=DepositStatistics)
async def get_statistics(user: CurrentUser, db: DbSession):
    return await DepositService(db).statistics(user.id)


@router.get("/chart", response_model=list[DepositChartItem])
async def get_chart(user: CurrentUser, db: DbSession):
    """Суммы вкладов по банкам — для круговой/столбчатой диаграммы."""

    return await DepositService(db).chart(user.id)


@router.get("/{deposit_id}", response_model=DepositDetail)
async def get_deposit(deposit_id: int, user: CurrentUser, db: DbSession):
    return await DepositService(db).detail(deposit_id, user.id)


@router.get("/{deposit_id}/forecast", response_model=DepositForecast)
async def get_forecast(deposit_id: int, user: CurrentUser, db: DbSession):
    return await DepositService(db).forecast(deposit_id, user.id)


@router.put("/{deposit_id}", response_model=DepositResponse)
async def update_deposit(deposit_id: int, payload: DepositUpdate, user: CurrentUser, db: DbSession):
    return await DepositService(db).update(deposit_id, user.id, payload)


@router.delete("/{deposit_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_deposit(deposit_id: int, user: CurrentUser, db: DbSession) -> None:
    await DepositService(db).delete(deposit_id, user.id)
