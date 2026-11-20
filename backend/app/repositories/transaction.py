"""User-owned transactions: CRUD queries, filtered listing and SQL aggregates.

Every method requires the owner's ``user_id``. Aggregates are computed in SQL
(SUM/COUNT ... GROUP BY) and returned as per-type sums for the finance engine,
which applies all financial definitions (refunds, transfers, rounding).
"""

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Select, func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.category import Category
from app.models.enums import TransactionType
from app.models.transaction import Transaction
from app.services.finance.cashflow import CashflowItem

# IANA zone names only (validated again against zoneinfo by the API layer);
# the name is inlined into SQL so GROUP BY sees one identical expression.
_TZ_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_+\-]*(/[A-Za-z0-9_+\-]+)*$")


@dataclass(frozen=True)
class TransactionFilters:
    start: datetime | None = None  # inclusive, timezone-aware
    end: datetime | None = None  # exclusive, timezone-aware
    category_id: int | None = None
    account_id: int | None = None
    bank_id: int | None = None
    transaction_type: TransactionType | None = None
    currency_code: str | None = None
    min_amount: Decimal | None = None
    max_amount: Decimal | None = None
    search: str | None = None


@dataclass
class TypeSums:
    sums: dict[TransactionType, Decimal] = field(default_factory=dict)
    count: int = 0


@dataclass
class CategorySums:
    category_id: int
    name: str
    is_system: bool = False
    sums: dict[TransactionType, Decimal] = field(default_factory=dict)
    count: int = 0


def _require_aware(*values: datetime | None) -> None:
    for value in values:
        if value is not None and value.tzinfo is None:
            raise ValueError("datetimes must be timezone-aware")


class TransactionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------ rows
    async def get_for_user(self, transaction_id: int, user_id: int) -> Transaction | None:
        return await self.db.scalar(
            select(Transaction).where(
                Transaction.id == transaction_id, Transaction.user_id == user_id
            )
        )

    def add(self, transaction: Transaction) -> None:
        self.db.add(transaction)

    async def delete(self, transaction: Transaction) -> None:
        await self.db.delete(transaction)

    def _filtered(self, user_id: int, f: TransactionFilters) -> Select:
        _require_aware(f.start, f.end)
        stmt = select(Transaction).where(Transaction.user_id == user_id)
        if f.start is not None:
            stmt = stmt.where(Transaction.transaction_date >= f.start)
        if f.end is not None:
            stmt = stmt.where(Transaction.transaction_date < f.end)
        if f.category_id is not None:
            stmt = stmt.where(Transaction.category_id == f.category_id)
        if f.account_id is not None:
            stmt = stmt.where(Transaction.account_id == f.account_id)
        if f.bank_id is not None:
            stmt = stmt.where(Transaction.bank_id == f.bank_id)
        if f.transaction_type is not None:
            stmt = stmt.where(Transaction.transaction_type == f.transaction_type)
        if f.currency_code is not None:
            stmt = stmt.where(Transaction.currency_code == f.currency_code)
        if f.min_amount is not None:
            stmt = stmt.where(Transaction.amount >= f.min_amount)
        if f.max_amount is not None:
            stmt = stmt.where(Transaction.amount <= f.max_amount)
        if f.search:
            escaped = f.search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            stmt = stmt.where(Transaction.description.ilike(f"%{escaped}%", escape="\\"))
        return stmt

    async def list_filtered(
        self, user_id: int, filters: TransactionFilters, limit: int, offset: int
    ) -> tuple[list[Transaction], int]:
        base = self._filtered(user_id, filters)
        total = await self.db.scalar(select(func.count()).select_from(base.subquery()))
        rows = await self.db.scalars(
            base.order_by(Transaction.transaction_date.desc(), Transaction.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(rows), int(total or 0)

    async def count_for_category(self, category_id: int) -> int:
        return int(
            await self.db.scalar(
                select(func.count(Transaction.id)).where(Transaction.category_id == category_id)
            )
            or 0
        )

    async def count_for_account(self, account_id: int, user_id: int) -> int:
        return int(
            await self.db.scalar(
                select(func.count(Transaction.id)).where(
                    Transaction.account_id == account_id, Transaction.user_id == user_id
                )
            )
            or 0
        )

    # ------------------------------------------------------------ engine inputs
    async def cashflow_items(
        self,
        user_id: int,
        start: datetime,
        end: datetime,
        currency_code: str | None = None,
        category_id: int | None = None,
    ) -> list[CashflowItem]:
        """Rows in ``[start, end)`` as engine inputs (only the needed columns)."""

        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("start and end must be timezone-aware")
        stmt = select(
            Transaction.amount,
            Transaction.transaction_type,
            Transaction.currency_code,
            Transaction.transaction_date,
        ).where(
            Transaction.user_id == user_id,
            Transaction.transaction_date >= start,
            Transaction.transaction_date < end,
        )
        if currency_code is not None:
            stmt = stmt.where(Transaction.currency_code == currency_code)
        if category_id is not None:
            stmt = stmt.where(Transaction.category_id == category_id)
        rows = await self.db.execute(stmt.order_by(Transaction.transaction_date, Transaction.id))
        return [
            CashflowItem(
                amount=row.amount,
                transaction_type=row.transaction_type,
                currency_code=row.currency_code,
                occurred_at=row.transaction_date,
            )
            for row in rows
        ]

    async def sums_by_type(
        self,
        user_id: int,
        start: datetime,
        end: datetime,
        currency_code: str,
        category_id: int | None = None,
    ) -> TypeSums:
        _require_aware(start, end)
        stmt = (
            select(
                Transaction.transaction_type,
                func.sum(Transaction.amount),
                func.count(Transaction.id),
            )
            .where(
                Transaction.user_id == user_id,
                Transaction.currency_code == currency_code,
                Transaction.transaction_date >= start,
                Transaction.transaction_date < end,
            )
            .group_by(Transaction.transaction_type)
        )
        if category_id is not None:
            stmt = stmt.where(Transaction.category_id == category_id)
        result = TypeSums()
        for kind, total, count in await self.db.execute(stmt):
            result.sums[kind] = total
            result.count += count
        return result

    async def sums_by_currency_and_category(
        self, user_id: int, start: datetime, end: datetime, currency_codes: set[str]
    ) -> dict[tuple[str, int | None], TypeSums]:
        """Per (currency, category or ``None``) per-type sums in one query —
        the input for utilization of many budgets at once (no N+1)."""

        _require_aware(start, end)
        if not currency_codes:
            return {}
        stmt = (
            select(
                Transaction.currency_code,
                Transaction.category_id,
                Transaction.transaction_type,
                func.sum(Transaction.amount),
                func.count(Transaction.id),
            )
            .where(
                Transaction.user_id == user_id,
                Transaction.currency_code.in_(sorted(currency_codes)),
                Transaction.transaction_date >= start,
                Transaction.transaction_date < end,
            )
            .group_by(
                Transaction.currency_code, Transaction.category_id, Transaction.transaction_type
            )
        )
        result: dict[tuple[str, int | None], TypeSums] = defaultdict(TypeSums)
        for currency_code, category_id, kind, total, count in await self.db.execute(stmt):
            entry = result[(currency_code, category_id)]
            entry.sums[kind] = total
            entry.count += count
        return dict(result)

    async def sums_by_category(
        self, user_id: int, start: datetime, end: datetime, currency_code: str
    ) -> list[CategorySums]:
        _require_aware(start, end)
        stmt = (
            select(
                Category.id,
                Category.name,
                Category.user_id.is_(None),
                Transaction.transaction_type,
                func.sum(Transaction.amount),
                func.count(Transaction.id),
            )
            .join(Category, Category.id == Transaction.category_id)
            .where(
                Transaction.user_id == user_id,
                Transaction.currency_code == currency_code,
                Transaction.transaction_date >= start,
                Transaction.transaction_date < end,
            )
            .group_by(Category.id, Category.name, Category.user_id, Transaction.transaction_type)
        )
        by_category: dict[int, CategorySums] = {}
        for category_id, name, is_system, kind, total, count in await self.db.execute(stmt):
            entry = by_category.setdefault(category_id, CategorySums(category_id, name, is_system))
            entry.sums[kind] = total
            entry.count += count
        return list(by_category.values())

    async def monthly_sums_by_type(
        self, user_id: int, start: datetime, end: datetime, currency_code: str, tz_name: str
    ) -> dict[tuple[int, int], TypeSums]:
        """Per LOCAL calendar month in ``tz_name`` -> per-type sums."""

        _require_aware(start, end)
        if not _TZ_NAME.match(tz_name):
            raise ValueError("invalid time zone name")
        local_month = func.date_trunc(
            "month", func.timezone(literal_column(f"'{tz_name}'"), Transaction.transaction_date)
        )
        stmt = (
            select(
                local_month.label("month"),
                Transaction.transaction_type,
                func.sum(Transaction.amount),
                func.count(Transaction.id),
            )
            .where(
                Transaction.user_id == user_id,
                Transaction.currency_code == currency_code,
                Transaction.transaction_date >= start,
                Transaction.transaction_date < end,
            )
            .group_by(local_month, Transaction.transaction_type)
        )
        result: dict[tuple[int, int], TypeSums] = defaultdict(TypeSums)
        for month, kind, total, count in await self.db.execute(stmt):
            entry = result[(month.year, month.month)]
            entry.sums[kind] = total
            entry.count += count
        return dict(result)

    async def account_flows(self, user_id: int) -> dict[int, dict[TransactionType, Decimal]]:
        """Per-account per-type sums of linked transactions on or after the
        account's ``opening_balance_at`` (input for ``account_balance``)."""

        stmt = (
            select(Account.id, Transaction.transaction_type, func.sum(Transaction.amount))
            .join(
                Transaction,
                (Transaction.account_id == Account.id)
                & (Transaction.user_id == Account.user_id)
                & (Transaction.transaction_date >= Account.opening_balance_at),
            )
            .where(Account.user_id == user_id)
            .group_by(Account.id, Transaction.transaction_type)
        )
        flows: dict[int, dict[TransactionType, Decimal]] = defaultdict(dict)
        for account_id, kind, total in await self.db.execute(stmt):
            flows[account_id][kind] = total
        return dict(flows)
