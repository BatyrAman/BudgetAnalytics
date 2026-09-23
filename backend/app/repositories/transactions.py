from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import joinedload

from app.models.enums import CategorySource, TransactionType
from app.models.transaction import Transaction
from app.repositories.base import OwnedRepository

_INSERT_CHUNK = 1000


@dataclass(frozen=True, slots=True)
class TransactionFilters:
    start_date: datetime | None = None
    end_date: datetime | None = None
    category_id: int | None = None
    bank_id: int | None = None
    card_id: int | None = None
    transaction_type: TransactionType | None = None
    min_amount: Decimal | None = None
    max_amount: Decimal | None = None

    def conditions(self) -> list[Any]:
        conditions: list[Any] = []
        if self.start_date is not None:
            conditions.append(Transaction.transaction_date >= self.start_date)
        if self.end_date is not None:
            conditions.append(Transaction.transaction_date <= self.end_date)
        if self.category_id is not None:
            conditions.append(Transaction.category_id == self.category_id)
        if self.bank_id is not None:
            conditions.append(Transaction.bank_id == self.bank_id)
        if self.card_id is not None:
            conditions.append(Transaction.card_id == self.card_id)
        if self.transaction_type is not None:
            conditions.append(Transaction.transaction_type == self.transaction_type)
        if self.min_amount is not None:
            conditions.append(Transaction.amount >= self.min_amount)
        if self.max_amount is not None:
            conditions.append(Transaction.amount <= self.max_amount)
        return conditions


class TransactionRepository(OwnedRepository[Transaction]):
    model = Transaction

    async def get_detailed(self, transaction_id: int, user_id: int) -> Transaction | None:
        return await self.get_owned(
            transaction_id,
            user_id,
            joinedload(Transaction.category),
            joinedload(Transaction.bank),
        )

    async def search(
        self, user_id: int, filters: TransactionFilters, limit: int, offset: int
    ) -> tuple[list[Transaction], int]:
        conditions = filters.conditions()
        total = await self.count_owned(user_id, *conditions)
        items = await self.list_owned(
            user_id,
            *conditions,
            order_by=(Transaction.transaction_date.desc(), Transaction.id.desc()),
            limit=limit,
            offset=offset,
        )
        return items, total

    async def recent_detailed(self, user_id: int, limit: int) -> list[Transaction]:
        # Одним запросом с JOIN вместо db.get() на каждую операцию (N+1).
        return await self.list_owned(
            user_id,
            order_by=(Transaction.transaction_date.desc(), Transaction.id.desc()),
            limit=limit,
            options=(joinedload(Transaction.category), joinedload(Transaction.bank)),
        )

    async def statistics(self, user_id: int, currency: str):
        income = Transaction.transaction_type == TransactionType.INCOME
        expense = Transaction.transaction_type == TransactionType.EXPENSE
        stmt = select(
            func.count(Transaction.id).label("count"),
            func.coalesce(func.sum(case((income, Transaction.amount))), 0).label("income"),
            func.coalesce(func.sum(case((expense, Transaction.amount))), 0).label("expense"),
            func.coalesce(func.avg(case((income, Transaction.amount))), 0).label("avg_income"),
            func.coalesce(func.avg(case((expense, Transaction.amount))), 0).label("avg_expense"),
        ).where(Transaction.user_id == user_id, Transaction.currency == currency)
        return (await self.session.execute(stmt)).one()

    async def insert_ignoring_duplicates(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        INSERT ... ON CONFLICT (user_id, external_hash) DO NOTHING.

        Возвращает только реально вставленные строки. Конкурентные
        импорты одной выписки не создадут дублей — это гарантирует БД.
        """

        inserted: list[dict[str, Any]] = []
        for start in range(0, len(rows), _INSERT_CHUNK):
            chunk = rows[start : start + _INSERT_CHUNK]
            stmt = (
                insert(Transaction)
                .values(chunk)
                .on_conflict_do_nothing(constraint="uq_transactions_user_external_hash")
                .returning(
                    Transaction.id,
                    Transaction.external_hash,
                    Transaction.amount,
                    Transaction.transaction_type,
                )
            )
            result = await self.session.execute(stmt)
            inserted.extend(dict(row._mapping) for row in result.all())
        return inserted

    async def existing_hashes(self, user_id: int, hashes: list[str]) -> set[str]:
        if not hashes:
            return set()
        stmt = select(Transaction.external_hash).where(
            Transaction.user_id == user_id,
            Transaction.external_hash.in_(hashes),
        )
        return set((await self.session.scalars(stmt)).all())

    async def category_memory(self, user_id: int, merchants: list[str]) -> dict[str, int]:
        """
        Последняя категория, которую пользователь вручную выбрал
        для каждого merchant. Один запрос на весь импорт.
        """

        if not merchants:
            return {}
        stmt = (
            select(Transaction.merchant, Transaction.category_id)
            .where(
                Transaction.user_id == user_id,
                Transaction.merchant.in_(merchants),
                Transaction.category_id.is_not(None),
                Transaction.category_source == CategorySource.USER,
            )
            .distinct(Transaction.merchant)
            .order_by(Transaction.merchant, Transaction.updated_at.desc(), Transaction.id.desc())
        )
        return {merchant: category_id for merchant, category_id in (await self.session.execute(stmt)).all()}
