"""
Агрегирующие запросы аналитики.

Все суммы считает PostgreSQL (SUM/COUNT + GROUP BY, date_trunc),
Python получает уже агрегированные строки. Каждый метод — ровно
один SQL-запрос, независимо от числа операций и длины периода.
Фильтр всегда включает user_id и полуинтервал [date_from, date_to),
что позволяет использовать индекс (user_id, transaction_date).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import Select, case, desc, distinct, func, literal_column, select

from app.models.bank import Bank
from app.models.card import Card
from app.models.category import Category
from app.models.enums import TransactionType
from app.models.transaction import Transaction
from app.repositories.base import Repository

Granularity = Literal["hour", "day", "week", "month"]
_GRANULARITIES = {"hour", "day", "week", "month"}


def _trunc(granularity: str, column):
    # Единица date_trunc вставляется литералом (из белого списка), а не
    # bind-параметром: иначе SELECT и GROUP BY получают разные $n и
    # PostgreSQL не считает выражения одинаковыми.
    if granularity not in _GRANULARITIES:
        raise ValueError(f"Unsupported granularity: {granularity}")
    return func.date_trunc(literal_column(f"'{granularity}'"), column)

INCOME = Transaction.transaction_type == TransactionType.INCOME
EXPENSE = Transaction.transaction_type == TransactionType.EXPENSE

_income_sum = func.coalesce(func.sum(case((INCOME, Transaction.amount))), 0)
_expense_sum = func.coalesce(func.sum(case((EXPENSE, Transaction.amount))), 0)


@dataclass(frozen=True, slots=True)
class Scope:
    user_id: int
    currency: str
    date_from: datetime | None = None
    date_to: datetime | None = None  # не включительно
    card_id: int | None = None

    def conditions(self) -> list[Any]:
        conditions: list[Any] = [
            Transaction.user_id == self.user_id,
            Transaction.currency == self.currency,
        ]
        if self.date_from is not None:
            conditions.append(Transaction.transaction_date >= self.date_from)
        if self.date_to is not None:
            conditions.append(Transaction.transaction_date < self.date_to)
        if self.card_id is not None:
            conditions.append(Transaction.card_id == self.card_id)
        return conditions


@dataclass(frozen=True, slots=True)
class Totals:
    income: Decimal
    expense: Decimal
    income_count: int
    expense_count: int


class AnalyticsRepository(Repository):
    def _where(self, stmt: Select, scope: Scope) -> Select:
        return stmt.where(*scope.conditions())

    async def totals(self, scope: Scope) -> Totals:
        stmt = self._where(
            select(
                _income_sum.label("income"),
                _expense_sum.label("expense"),
                func.count(case((INCOME, 1))).label("income_count"),
                func.count(case((EXPENSE, 1))).label("expense_count"),
            ),
            scope,
        )
        row = (await self.session.execute(stmt)).one()
        return Totals(
            income=Decimal(row.income),
            expense=Decimal(row.expense),
            income_count=int(row.income_count),
            expense_count=int(row.expense_count),
        )

    async def series(self, scope: Scope, granularity: Granularity) -> list[tuple[datetime, Decimal, Decimal]]:
        bucket = _trunc(granularity, Transaction.transaction_date).label("bucket")
        stmt = self._where(
            select(bucket, _income_sum.label("income"), _expense_sum.label("expense")),
            scope,
        ).group_by(bucket).order_by(bucket)
        return [
            (row.bucket, Decimal(row.income), Decimal(row.expense))
            for row in (await self.session.execute(stmt)).all()
        ]

    async def by_category(
        self,
        scope: Scope,
        transaction_type: TransactionType = TransactionType.EXPENSE,
        limit: int | None = None,
    ) -> list[tuple[int | None, str, str | None, Decimal, int]]:
        total = func.sum(Transaction.amount)
        stmt = (
            self._where(
                select(
                    Transaction.category_id,
                    func.coalesce(Category.name, "Без категории").label("name"),
                    Category.color,
                    total.label("total"),
                    func.count(Transaction.id).label("count"),
                ).outerjoin(Category, Category.id == Transaction.category_id),
                scope,
            )
            .where(Transaction.transaction_type == transaction_type)
            .group_by(Transaction.category_id, Category.name, Category.color)
            .order_by(desc("total"), Transaction.category_id)
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        return [
            (row.category_id, row.name, row.color, Decimal(row.total), int(row.count))
            for row in (await self.session.execute(stmt)).all()
        ]

    async def top_merchants(self, scope: Scope, limit: int = 5) -> list[tuple[str, Decimal, int]]:
        merchant = func.coalesce(
            Transaction.merchant, Transaction.description, literal_column("'—'")
        ).label("merchant")
        total = func.sum(Transaction.amount)
        stmt = (
            self._where(select(merchant, total.label("total"), func.count(Transaction.id).label("count")), scope)
            .where(EXPENSE)
            .group_by(merchant)
            .order_by(desc("total"), merchant)
            .limit(limit)
        )
        return [(row.merchant, Decimal(row.total), int(row.count)) for row in (await self.session.execute(stmt)).all()]

    async def top_expenses(self, scope: Scope, limit: int = 5) -> list[Transaction]:
        stmt = (
            self._where(select(Transaction), scope)
            .where(EXPENSE)
            .order_by(Transaction.amount.desc(), Transaction.transaction_date.desc())
            .limit(limit)
        )
        return list((await self.session.scalars(stmt)).all())

    async def recurring(
        self, scope: Scope, min_months: int = 2, limit: int = 20
    ) -> list[tuple[str, Decimal, int, int, datetime]]:
        """
        Регулярные платежи: один и тот же получатель и сумма в
        min_months+ разных месяцах окна (подписки, связь, коммуналка).
        """

        merchant = func.coalesce(Transaction.merchant, Transaction.description).label("merchant")
        months = func.count(distinct(_trunc("month", Transaction.transaction_date)))
        stmt = (
            self._where(
                select(
                    merchant,
                    Transaction.amount,
                    func.count(Transaction.id).label("occurrences"),
                    months.label("months"),
                    func.max(Transaction.transaction_date).label("last_date"),
                ),
                scope,
            )
            .where(EXPENSE, merchant.is_not(None))
            .group_by(merchant, Transaction.amount)
            .having(months >= min_months)
            .order_by(desc("months"), Transaction.amount.desc())
            .limit(limit)
        )
        return [
            (row.merchant, Decimal(row.amount), int(row.occurrences), int(row.months), row.last_date)
            for row in (await self.session.execute(stmt)).all()
        ]

    async def by_bank(self, scope: Scope) -> list[tuple[int, str, Decimal, Decimal, int]]:
        stmt = (
            self._where(
                select(
                    Bank.id,
                    Bank.name,
                    _income_sum.label("income"),
                    _expense_sum.label("expense"),
                    func.count(Transaction.id).label("count"),
                ).join(Bank, Bank.id == Transaction.bank_id),
                scope,
            )
            .group_by(Bank.id, Bank.name)
            .order_by(Bank.name)
        )
        return [
            (row.id, row.name, Decimal(row.income), Decimal(row.expense), int(row.count))
            for row in (await self.session.execute(stmt)).all()
        ]

    async def by_card(self, scope: Scope) -> list[tuple[int | None, str | None, Decimal, Decimal, int]]:
        stmt = (
            self._where(
                select(
                    Transaction.card_id,
                    Card.last4,
                    _income_sum.label("income"),
                    _expense_sum.label("expense"),
                    func.count(Transaction.id).label("count"),
                ).outerjoin(Card, Card.id == Transaction.card_id),
                scope,
            )
            .group_by(Transaction.card_id, Card.last4)
            .order_by(Transaction.card_id)
        )
        return [
            (row.card_id, row.last4, Decimal(row.income), Decimal(row.expense), int(row.count))
            for row in (await self.session.execute(stmt)).all()
        ]

    async def by_weekday(self, scope: Scope) -> list[tuple[int, Decimal, int]]:
        weekday = func.extract("isodow", Transaction.transaction_date).label("weekday")
        stmt = (
            self._where(select(weekday, func.sum(Transaction.amount).label("total"), func.count(Transaction.id).label("count")), scope)
            .where(EXPENSE)
            .group_by(weekday)
            .order_by(weekday)
        )
        return [(int(row.weekday), Decimal(row.total), int(row.count)) for row in (await self.session.execute(stmt)).all()]

    async def monthly_totals(self, scope: Scope) -> list[tuple[datetime, Decimal, Decimal]]:
        return await self.series(scope, "month")

    async def category_spent(
        self, user_id: int, currency: str, category_ids: list[int], date_from: datetime, date_to: datetime
    ) -> dict[int, Decimal]:
        """Расходы по нескольким категориям за период — одним запросом (для бюджетов)."""

        if not category_ids:
            return {}
        stmt = (
            select(Transaction.category_id, func.sum(Transaction.amount))
            .where(
                Transaction.user_id == user_id,
                Transaction.currency == currency,
                EXPENSE,
                Transaction.category_id.in_(category_ids),
                Transaction.transaction_date >= date_from,
                Transaction.transaction_date < date_to,
            )
            .group_by(Transaction.category_id)
        )
        return {cid: Decimal(total) for cid, total in (await self.session.execute(stmt)).all()}
