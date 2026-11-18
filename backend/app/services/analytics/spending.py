from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.enums import TransactionType
from app.models.transaction import Transaction


class SpendingAnalyticsService:
    """
    Сервис аналитики расходов.
    """

    def __init__(self, db: AsyncSession, currency_code: str = "KZT"):
        # LEGACY: only rows in this currency are aggregated (never mixed).
        self.db = db
        self.currency_code = currency_code

    async def get_total_expenses(
        self,
        user_id: int,
    ) -> Decimal:
        """
        Общая сумма расходов пользователя.
        """

        stmt = select(
            func.coalesce(
                func.sum(Transaction.amount),
                0,
            )
        ).where(
            Transaction.user_id == user_id,
            Transaction.currency_code == self.currency_code,
            Transaction.transaction_type == TransactionType.EXPENSE,
        )

        result = await self.db.scalar(stmt)

        return Decimal(result or 0)

    async def get_monthly_expenses(
        self,
        user_id: int,
        year: int,
        month: int,
    ) -> Decimal:
        """
        Расходы за выбранный месяц.
        """

        stmt = select(
            func.coalesce(
                func.sum(Transaction.amount),
                0,
            )
        ).where(
            Transaction.user_id == user_id,
            Transaction.currency_code == self.currency_code,
            Transaction.transaction_type == TransactionType.EXPENSE,
            func.extract("year", Transaction.transaction_date) == year,
            func.extract("month", Transaction.transaction_date) == month,
        )

        result = await self.db.scalar(stmt)

        return Decimal(result or 0)

    async def get_average_expense(
        self,
        user_id: int,
    ) -> Decimal:
        """
        Средний размер расходной операции.
        """

        stmt = select(
            func.coalesce(
                func.avg(Transaction.amount),
                0,
            )
        ).where(
            Transaction.user_id == user_id,
            Transaction.currency_code == self.currency_code,
            Transaction.transaction_type == TransactionType.EXPENSE,
        )

        result = await self.db.scalar(stmt)

        return Decimal(result or 0)

    async def get_transactions_count(
        self,
        user_id: int,
    ) -> int:
        """
        Количество расходных операций.
        """

        stmt = select(func.count(Transaction.id)).where(
            Transaction.user_id == user_id,
            Transaction.currency_code == self.currency_code,
            Transaction.transaction_type == TransactionType.EXPENSE,
        )

        result = await self.db.scalar(stmt)

        return int(result or 0)

    async def get_top_categories(
        self,
        user_id: int,
        limit: int = 5,
    ):
        """
        Самые затратные категории.
        """

        stmt = (
            select(
                Category.name,
                func.sum(Transaction.amount).label("total"),
            )
            .join(
                Category,
                Category.id == Transaction.category_id,
            )
            .where(
                Transaction.user_id == user_id,
                Transaction.currency_code == self.currency_code,
                Transaction.transaction_type == TransactionType.EXPENSE,
            )
            .group_by(Category.name)
            .order_by(func.sum(Transaction.amount).desc())
            .limit(limit)
        )

        result = await self.db.execute(stmt)

        return result.all()

    async def get_current_month_summary(
        self,
        user_id: int,
    ) -> dict:
        """
        Краткая статистика расходов за текущий месяц.
        """

        now = datetime.utcnow()

        total = await self.get_monthly_expenses(
            user_id=user_id,
            year=now.year,
            month=now.month,
        )

        average = await self.get_average_expense(user_id)

        count = await self.get_transactions_count(user_id)

        categories = await self.get_top_categories(user_id)

        return {
            "total_expense": total,
            "average_expense": average,
            "transactions": count,
            "top_categories": categories,
        }
