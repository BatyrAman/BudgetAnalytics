from __future__ import annotations

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, DbSession
from app.core.errors import ERROR_RESPONSES
from app.schemas.debt import (
    DebtCreate,
    DebtPaymentCreate,
    DebtPaymentResponse,
    DebtResponse,
    DebtScheduleResponse,
    DebtSummary,
    DebtUpdate,
    PrepaymentRequest,
    PrepaymentResponse,
    StrategyRequest,
    StrategyResponse,
    UpcomingPayment,
)
from app.services.debts.service import DebtService

router = APIRouter(prefix="/debts", tags=["Debts"], responses=ERROR_RESPONSES)


@router.get("", response_model=list[DebtResponse])
async def list_debts(user: CurrentUser, db: DbSession, include_closed: bool = False):
    """Долги пользователя с прогнозом закрытия и переплатой при текущем платеже."""

    return await DebtService(db).list(user.id, include_closed)


@router.post("", response_model=DebtResponse, status_code=status.HTTP_201_CREATED)
async def create_debt(payload: DebtCreate, user: CurrentUser, db: DbSession):
    return await DebtService(db).create(user.id, payload)


@router.get("/summary", response_model=DebtSummary)
async def get_summary(user: CurrentUser, db: DbSession):
    """Общий долг, платёж в месяц, долговая нагрузка и дата свободы от долгов."""

    return await DebtService(db).summary(user)


@router.get("/calendar", response_model=list[UpcomingPayment])
async def get_calendar(user: CurrentUser, db: DbSession, days: int = Query(default=30, ge=1, le=366)):
    return await DebtService(db).calendar(user.id, days)


@router.post("/strategy", response_model=StrategyResponse)
async def simulate_strategy(payload: StrategyRequest, user: CurrentUser, db: DbSession):
    """
    Помесячная симуляция погашения всех активных долгов по стратегии
    avalanche / snowball / hybrid с дополнительным платежом extra_payment
    и сравнение со всеми стратегиями и с «только минимальными платежами».
    """

    return await DebtService(db).strategy(user.id, payload)


@router.get("/{debt_id}", response_model=DebtResponse)
async def get_debt(debt_id: int, user: CurrentUser, db: DbSession):
    return await DebtService(db).get(debt_id, user.id)


@router.put("/{debt_id}", response_model=DebtResponse)
async def update_debt(debt_id: int, payload: DebtUpdate, user: CurrentUser, db: DbSession):
    return await DebtService(db).update(debt_id, user.id, payload)


@router.delete("/{debt_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_debt(debt_id: int, user: CurrentUser, db: DbSession) -> None:
    await DebtService(db).delete(debt_id, user.id)


@router.get("/{debt_id}/schedule", response_model=DebtScheduleResponse)
async def get_schedule(debt_id: int, user: CurrentUser, db: DbSession):
    return await DebtService(db).schedule(debt_id, user.id)


@router.post("/{debt_id}/prepayment", response_model=PrepaymentResponse)
async def simulate_prepayment(debt_id: int, payload: PrepaymentRequest, user: CurrentUser, db: DbSession):
    """Расчёт досрочного погашения: mode=term (уменьшить срок) или payment (уменьшить платёж)."""

    return await DebtService(db).prepayment(debt_id, user.id, payload)


@router.get("/{debt_id}/payments", response_model=list[DebtPaymentResponse])
async def list_payments(debt_id: int, user: CurrentUser, db: DbSession):
    return await DebtService(db).list_payments(debt_id, user.id)


@router.post("/{debt_id}/payments", response_model=DebtPaymentResponse, status_code=status.HTTP_201_CREATED)
async def record_payment(debt_id: int, payload: DebtPaymentCreate, user: CurrentUser, db: DbSession):
    """Фиксирует внесённый платёж: проценты за месяц, затем основной долг."""

    return await DebtService(db).record_payment(debt_id, user.id, payload)


@router.delete("/{debt_id}/payments/{payment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def reverse_payment(debt_id: int, payment_id: int, user: CurrentUser, db: DbSession) -> None:
    """Сторнирует платёж и возвращает основной долг в остаток."""

    await DebtService(db).reverse_payment(debt_id, payment_id, user.id)
