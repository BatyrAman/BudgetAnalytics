from __future__ import annotations

from datetime import date

from sqlalchemy import func, select

from app.models.debt import Debt, DebtPayment
from app.models.enums import DebtPaymentStatus
from app.repositories.base import OwnedRepository


class DebtRepository(OwnedRepository[Debt]):
    model = Debt

    async def list_active(self, user_id: int) -> list[Debt]:
        return await self.list_owned(
            user_id, Debt.is_active.is_(True), Debt.balance > 0, order_by=Debt.id
        )

    async def interest_paid(self, user_id: int, debt_ids: list[int]) -> dict[int, object]:
        if not debt_ids:
            return {}
        stmt = (
            select(DebtPayment.debt_id, func.sum(DebtPayment.interest_part))
            .where(
                DebtPayment.user_id == user_id,
                DebtPayment.debt_id.in_(debt_ids),
                DebtPayment.status == DebtPaymentStatus.PAID,
            )
            .group_by(DebtPayment.debt_id)
        )
        return dict((await self.session.execute(stmt)).all())


class DebtPaymentRepository(OwnedRepository[DebtPayment]):
    model = DebtPayment

    async def for_debt(self, user_id: int, debt_id: int) -> list[DebtPayment]:
        return await self.list_owned(
            user_id, DebtPayment.debt_id == debt_id, order_by=(DebtPayment.paid_at.desc(), DebtPayment.id.desc())
        )

    async def paid_due_dates(self, user_id: int, date_from: date, date_to: date) -> set[tuple[int, date]]:
        stmt = select(DebtPayment.debt_id, DebtPayment.due_date).where(
            DebtPayment.user_id == user_id,
            DebtPayment.status == DebtPaymentStatus.PAID,
            DebtPayment.due_date >= date_from,
            DebtPayment.due_date <= date_to,
        )
        return {(row[0], row[1]) for row in (await self.session.execute(stmt)).all()}
