from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, NotFoundError
from app.models.deposit import Deposit
from app.repositories.banks import BankRepository
from app.repositories.deposits import DepositRepository
from app.schemas.deposit import (
    DepositChartItem,
    DepositCreate,
    DepositDetail,
    DepositForecast,
    DepositResponse,
    DepositStatistics,
    DepositUpdate,
)
from app.services.finance.deposits import simple_interest
from app.services.finance.money import ZERO


def expected_profit(deposit: Deposit) -> Decimal:
    """Доход без капитализации, ACT/365 — как в v0.1 API."""

    return simple_interest(deposit.amount, deposit.interest_rate, deposit.start_date, deposit.end_date)


class DepositService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = DepositRepository(session)
        self.banks = BankRepository(session)

    async def _get_owned(self, deposit_id: int, user_id: int) -> Deposit:
        deposit = await self.repo.get_with_bank(deposit_id, user_id)
        if deposit is None:
            raise NotFoundError("Deposit not found", code="DEPOSIT_NOT_FOUND")
        return deposit

    async def create(self, user_id: int, payload: DepositCreate) -> Deposit:
        if await self.banks.get(payload.bank_id) is None:
            raise AppError("Bank not found", code="BANK_NOT_FOUND")
        if payload.end_date <= payload.start_date:
            raise AppError("end_date must be after start_date", code="INVALID_DATE_RANGE")
        deposit = self.repo.add(Deposit(user_id=user_id, **payload.model_dump()))
        await self.session.commit()
        await self.session.refresh(deposit)
        return deposit

    async def list(self, user_id: int, limit: int, offset: int) -> tuple[list[Deposit], int]:
        total = await self.repo.count_owned(user_id)
        items = await self.repo.list_owned(
            user_id, order_by=(Deposit.start_date.desc(), Deposit.id.desc()), limit=limit, offset=offset
        )
        return items, total

    async def detail(self, deposit_id: int, user_id: int, today: date | None = None) -> DepositDetail:
        deposit = await self._get_owned(deposit_id, user_id)
        profit = expected_profit(deposit)
        return DepositDetail(
            **DepositResponse.model_validate(deposit).model_dump(),
            bank_name=deposit.bank.name if deposit.bank else "—",
            duration_days=max((deposit.end_date - deposit.start_date).days, 0),
            expected_profit=profit,
            expected_amount=deposit.amount + profit,
            is_active=deposit.end_date >= (today or date.today()),
        )

    async def forecast(self, deposit_id: int, user_id: int) -> DepositForecast:
        deposit = await self._get_owned(deposit_id, user_id)
        profit = expected_profit(deposit)
        return DepositForecast(
            deposit_id=deposit.id,
            maturity_date=deposit.end_date,
            expected_profit=profit,
            expected_amount=deposit.amount + profit,
        )

    async def statistics(self, user_id: int) -> DepositStatistics:
        deposits = await self.repo.list_owned(user_id)
        total_amount = sum((d.amount for d in deposits), ZERO)
        total_profit = sum((expected_profit(d) for d in deposits), ZERO)
        return DepositStatistics(
            total_deposits=len(deposits),
            total_amount=total_amount,
            total_expected_profit=total_profit,
            total_expected_value=total_amount + total_profit,
        )

    async def chart(self, user_id: int) -> list[DepositChartItem]:
        return [
            DepositChartItem(label=name, amount=Decimal(total))
            for name, total in await self.repo.sum_by_bank(user_id)
        ]

    async def update(self, deposit_id: int, user_id: int, payload: DepositUpdate) -> Deposit:
        deposit = await self._get_owned(deposit_id, user_id)
        updates = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
        if "bank_id" in updates and await self.banks.get(updates["bank_id"]) is None:
            raise AppError("Bank not found", code="BANK_NOT_FOUND")
        start = updates.get("start_date", deposit.start_date)
        end = updates.get("end_date", deposit.end_date)
        if end <= start:
            raise AppError("end_date must be after start_date", code="INVALID_DATE_RANGE")
        for field, value in updates.items():
            setattr(deposit, field, value)
        await self.session.commit()
        await self.session.refresh(deposit)
        return deposit

    async def delete(self, deposit_id: int, user_id: int) -> None:
        deposit = await self._get_owned(deposit_id, user_id)
        await self.repo.delete(deposit)
        await self.session.commit()
