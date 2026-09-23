from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import PaginationParams, get_current_active_user, get_db
from app.models.bank import Bank
from app.models.deposit import Deposit
from app.models.user import User
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

router = APIRouter(prefix="/investments", tags=["Investments"])


def _expected_profit(deposit: Deposit) -> Decimal:
    duration_days = (deposit.end_date - deposit.start_date).days
    duration_days = max(duration_days, 0)

    rate = deposit.interest_rate / Decimal("100")

    profit = deposit.amount * rate * Decimal(duration_days) / Decimal("365")

    return profit.quantize(Decimal("0.01"))


async def _to_detail(db: AsyncSession, deposit: Deposit) -> DepositDetail:

    bank = await db.get(Bank, deposit.bank_id)

    duration_days = max((deposit.end_date - deposit.start_date).days, 0)
    profit = _expected_profit(deposit)

    return DepositDetail(
        **DepositResponse.model_validate(deposit).model_dump(),
        bank_name=bank.name if bank else "—",
        duration_days=duration_days,
        expected_profit=profit,
        expected_amount=deposit.amount + profit,
        is_active=deposit.end_date >= date.today(),
    )


async def _get_owned_deposit(
    db: AsyncSession,
    deposit_id: int,
    user_id: int,
) -> Deposit:

    deposit = await db.scalar(
        select(Deposit).where(
            Deposit.id == deposit_id,
            Deposit.user_id == user_id,
        )
    )

    if deposit is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deposit not found",
        )

    return deposit


@router.post(
    "",
    response_model=DepositResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_deposit(
    payload: DepositCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Deposit:

    bank = await db.get(Bank, payload.bank_id)
    if bank is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bank not found",
        )

    if payload.end_date <= payload.start_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_date must be after start_date",
        )

    deposit = Deposit(
        amount=payload.amount,
        interest_rate=payload.interest_rate,
        start_date=payload.start_date,
        end_date=payload.end_date,
        bank_id=payload.bank_id,
        user_id=current_user.id,
    )

    db.add(deposit)
    await db.commit()
    await db.refresh(deposit)

    return deposit


@router.get(
    "",
    response_model=DepositListResponse,
)
async def list_deposits(
    pagination: PaginationParams = Depends(),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> DepositListResponse:

    total = await db.scalar(
        select(func.count(Deposit.id)).where(Deposit.user_id == current_user.id)
    )

    result = await db.execute(
        select(Deposit)
        .where(Deposit.user_id == current_user.id)
        .order_by(Deposit.start_date.desc())
        .limit(pagination.limit)
        .offset(pagination.offset)
    )

    return DepositListResponse(items=result.scalars().all(), total=total or 0)


@router.get(
    "/statistics",
    response_model=DepositStatistics,
)
async def get_statistics(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> DepositStatistics:

    result = await db.execute(
        select(Deposit).where(Deposit.user_id == current_user.id)
    )
    deposits = result.scalars().all()

    total_amount = sum((d.amount for d in deposits), Decimal("0"))
    total_profit = sum((_expected_profit(d) for d in deposits), Decimal("0"))

    return DepositStatistics(
        total_deposits=len(deposits),
        total_amount=total_amount,
        total_expected_profit=total_profit,
        total_expected_value=total_amount + total_profit,
    )


@router.get(
    "/chart",
    response_model=list[DepositChartItem],
)
async def get_chart(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> list[DepositChartItem]:
    """
    Суммы вкладов по банкам — для круговой/столбчатой диаграммы.
    """

    stmt = (
        select(Bank.name, func.sum(Deposit.amount))
        .join(Bank, Bank.id == Deposit.bank_id)
        .where(Deposit.user_id == current_user.id)
        .group_by(Bank.name)
        .order_by(func.sum(Deposit.amount).desc())
    )

    result = await db.execute(stmt)

    return [
        DepositChartItem(label=name, amount=Decimal(total))
        for name, total in result.all()
    ]


@router.get(
    "/{deposit_id}",
    response_model=DepositDetail,
)
async def get_deposit(
    deposit_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> DepositDetail:

    deposit = await _get_owned_deposit(db, deposit_id, current_user.id)
    return await _to_detail(db, deposit)


@router.get(
    "/{deposit_id}/forecast",
    response_model=DepositForecast,
)
async def get_forecast(
    deposit_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> DepositForecast:

    deposit = await _get_owned_deposit(db, deposit_id, current_user.id)
    profit = _expected_profit(deposit)

    return DepositForecast(
        deposit_id=deposit.id,
        maturity_date=deposit.end_date,
        expected_profit=profit,
        expected_amount=deposit.amount + profit,
    )


@router.put(
    "/{deposit_id}",
    response_model=DepositResponse,
)
async def update_deposit(
    deposit_id: int,
    payload: DepositUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Deposit:

    deposit = await _get_owned_deposit(db, deposit_id, current_user.id)

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(deposit, field, value)

    db.add(deposit)
    await db.commit()
    await db.refresh(deposit)

    return deposit


@router.delete(
    "/{deposit_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_deposit(
    deposit_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> None:

    deposit = await _get_owned_deposit(db, deposit_id, current_user.id)

    await db.delete(deposit)
    await db.commit()
