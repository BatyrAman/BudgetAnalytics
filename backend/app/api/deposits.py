from typing import Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import PaginationParams, get_current_active_user, get_db
from app.core.errors import AppError, ErrorResponse
from app.models.deposit import Deposit
from app.models.user import User
from app.repositories.currency import CurrencyRepository
from app.schemas.deposits import (
    DepositCalculationRequest,
    DepositCalculationResponse,
    DepositCreate,
    DepositListResponse,
    DepositResponse,
    DepositUpdate,
)
from app.services.deposit_service import DepositService, to_maturity
from app.services.deposits import maturity_of
from app.services.finance import add_months, deposit_maturity

router = APIRouter(prefix="/deposits", tags=["Deposits"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorResponse},
    401: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}


def _response(deposit: Deposit) -> DepositResponse:
    return DepositResponse(
        id=deposit.id,
        bank_id=deposit.bank_id,
        principal=deposit.amount,
        currency_code=deposit.currency_code,
        interest_rate=deposit.interest_rate,
        effective_rate=deposit.effective_rate,
        capitalization=deposit.capitalization,
        start_date=deposit.start_date,
        end_date=deposit.end_date,
        maturity=to_maturity(maturity_of(deposit), deposit.interest_rate),
        created_at=deposit.created_at,
        updated_at=deposit.updated_at,
    )


@router.post(
    "/calculate",
    response_model=DepositCalculationResponse,
    responses={401: _ERRORS[401], 422: _ERRORS[422]},
)
async def calculate_deposit(
    payload: DepositCalculationRequest,
    _current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> DepositCalculationResponse:
    """Deterministic deposit calculator (nothing is stored)."""

    currency = await CurrencyRepository(db).get_spec(payload.currency)
    if currency is None:
        raise AppError("Unknown currency")
    end = payload.end_date or add_months(payload.start_date, payload.term_months or 0)
    result = deposit_maturity(
        payload.principal,
        payload.interest_rate,
        payload.start_date,
        end,
        payload.capitalization,
        currency,
    )
    return DepositCalculationResponse(
        principal=result.principal,
        currency_code=currency.code,
        interest_rate=payload.interest_rate,
        capitalization=payload.capitalization,
        start_date=payload.start_date,
        maturity_date=end,
        maturity=to_maturity(result, payload.interest_rate),
    )


@router.post(
    "", response_model=DepositResponse, status_code=status.HTTP_201_CREATED, responses=_ERRORS
)
async def create_deposit(
    payload: DepositCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> DepositResponse:
    deposit = await DepositService(db).create(payload, current_user)
    await db.commit()
    return _response(deposit)


@router.get("", response_model=DepositListResponse, responses={401: _ERRORS[401]})
async def list_deposits(
    pagination: PaginationParams = Depends(),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> DepositListResponse:
    items, total = await DepositService(db).list(
        current_user.id, pagination.limit, pagination.offset
    )
    return DepositListResponse(
        items=[_response(d) for d in items],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.get("/{deposit_id}", response_model=DepositResponse, responses=_ERRORS)
async def get_deposit(
    deposit_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> DepositResponse:
    return _response(await DepositService(db).get(deposit_id, current_user.id))


@router.patch("/{deposit_id}", response_model=DepositResponse, responses=_ERRORS)
async def update_deposit(
    deposit_id: int,
    payload: DepositUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> DepositResponse:
    deposit = await DepositService(db).update(deposit_id, payload, current_user.id)
    await db.commit()
    return _response(deposit)


@router.delete("/{deposit_id}", status_code=status.HTTP_204_NO_CONTENT, responses=_ERRORS)
async def delete_deposit(
    deposit_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await DepositService(db).delete(deposit_id, current_user.id)
    await db.commit()
