"""Deposit use cases. All numbers come from ``app.services.finance``."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, NotFoundError
from app.models.bank import Bank
from app.models.deposit import Deposit
from app.models.enums import Capitalization
from app.models.user import User
from app.repositories.currency import CurrencyRepository
from app.repositories.deposit import DepositRepository
from app.schemas.deposits import DepositCreate, DepositUpdate, Maturity
from app.services.deposits import validate_deposit_term
from app.services.finance import DepositMaturity, effective_annual_rate

PERIODS_PER_YEAR = {
    Capitalization.MONTHLY: 12,
    Capitalization.QUARTERLY: 4,
    Capitalization.ANNUALLY: 1,
}


def to_maturity(result: DepositMaturity, nominal_rate) -> Maturity:
    periods = PERIODS_PER_YEAR.get(result.capitalization)
    return Maturity(
        term_days=result.term_days,
        capitalization_periods=result.capitalization_periods,
        stub_days=result.stub_days,
        interest=result.interest,
        maturity_amount=result.maturity_amount,
        effective_annual_rate=effective_annual_rate(nominal_rate, periods) if periods else None,
    )


class DepositService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.deposits = DepositRepository(db)

    async def get(self, deposit_id: int, user_id: int) -> Deposit:
        deposit = await self.deposits.get_for_user(deposit_id, user_id)
        if deposit is None:
            raise NotFoundError("Deposit not found", code="deposit_not_found")
        return deposit

    async def list(self, user_id: int, limit: int, offset: int) -> tuple[list[Deposit], int]:
        base = select(Deposit).where(Deposit.user_id == user_id)
        total = await self.db.scalar(select(func.count()).select_from(base.subquery()))
        rows = await self.db.scalars(
            base.order_by(Deposit.start_date.desc(), Deposit.id.desc()).limit(limit).offset(offset)
        )
        return list(rows), int(total or 0)

    async def _check_bank(self, bank_id: int) -> None:
        if await self.db.get(Bank, bank_id) is None:
            raise AppError("Bank not found", code="bank_not_found")

    async def create(self, payload: DepositCreate, user: User) -> Deposit:
        currency = payload.currency or user.default_currency_code
        if await CurrencyRepository(self.db).get(currency) is None:
            raise AppError("Unknown currency", code="unknown_currency")
        await self._check_bank(payload.bank_id)
        deposit = Deposit(
            user_id=user.id,
            bank_id=payload.bank_id,
            amount=payload.principal,
            currency_code=currency,
            interest_rate=payload.interest_rate,
            effective_rate=payload.effective_rate,
            capitalization=payload.capitalization,
            start_date=payload.start_date,
            end_date=payload.end_date,
        )
        self.deposits.add(deposit)
        await self.db.flush()
        await self.db.refresh(deposit)
        return deposit

    async def update(self, deposit_id: int, payload: DepositUpdate, user_id: int) -> Deposit:
        deposit = await self.get(deposit_id, user_id)
        changes = payload.model_dump(exclude_unset=True)
        if "bank_id" in changes:
            await self._check_bank(changes["bank_id"])
        if "principal" in changes:
            changes["amount"] = changes.pop("principal")
        if "start_date" in changes or "end_date" in changes:
            # Validated together with the stored date that is not changing.
            # Edits that leave the dates alone stay possible on a legacy
            # deposit with a data_issue (it is never silently "fixed").
            validate_deposit_term(
                changes.get("start_date", deposit.start_date),
                changes.get("end_date", deposit.end_date),
            )
        for field, value in changes.items():
            setattr(deposit, field, value)
        await self.db.flush()
        await self.db.refresh(deposit)
        return deposit

    async def delete(self, deposit_id: int, user_id: int) -> None:
        await self.db.delete(await self.get(deposit_id, user_id))
