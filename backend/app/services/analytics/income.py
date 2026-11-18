from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.enums import TransactionType
from app.models.transaction import Transaction


class IncomeAnalyticsService:
    """
    Сервис аналитики доходов.
    """

    def __init__(self, db: AsyncSession, currency_code: str = "KZT"):
        # LEGACY: only rows in this currency are aggregated (never mixed).
        self.db = db
        self.currency_code = currency_code

    async def get_total_income(
        self,
        user_id: int,
    ) -> Decimal:
        """
        Общая сумма доходов пользователя.
        """

        stmt = select(
            func.coalesce(
                func.sum(Transaction.amount),
                0,
            )
        ).where(
            Transaction.user_id == user_id,
            Transaction.currency_code == self.currency_code,
            Transaction.transaction_type == TransactionType.INCOME,
        )

        result = await self.db.scalar(stmt)

        return Decimal(result or 0)

    async def get_monthly_income(
        self,
        user_id: int,
        year: int,
        month: int,
    ) -> Decimal:
        """
        Доход за выбранный месяц.
        """

        stmt = select(
            func.coalesce(
                func.sum(Transaction.amount),
                0,
            )
        ).where(
            Transaction.user_id == user_id,
            Transaction.currency_code == self.currency_code,
            Transaction.transaction_type == TransactionType.INCOME,
            func.extract("year", Transaction.transaction_date) == year,
            func.extract("month", Transaction.transaction_date) == month,
        )

        result = await self.db.scalar(stmt)

        return Decimal(result or 0)

    async def get_average_income(
        self,
        user_id: int,
    ) -> Decimal:
        """
        Средний размер доходной операции.
        """

        stmt = select(
            func.coalesce(
                func.avg(Transaction.amount),
                0,
            )
        ).where(
            Transaction.user_id == user_id,
            Transaction.currency_code == self.currency_code,
            Transaction.transaction_type == TransactionType.INCOME,
        )

        result = await self.db.scalar(stmt)

        return Decimal(result or 0)

    async def get_transactions_count(
        self,
        user_id: int,
    ) -> int:
        """
        Количество доходных операций.
        """

        stmt = select(func.count(Transaction.id)).where(
            Transaction.user_id == user_id,
            Transaction.currency_code == self.currency_code,
            Transaction.transaction_type == TransactionType.INCOME,
        )

        result = await self.db.scalar(stmt)

        return int(result or 0)

    async def get_income_by_category(
        self,
        user_id: int,
        limit: int = 10,
    ):
        """
        Доход по категориям.
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
                Transaction.transaction_type == TransactionType.INCOME,
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
        Общая статистика текущего месяца.
        """

        now = datetime.utcnow()

        total = await self.get_monthly_income(
            user_id=user_id,
            year=now.year,
            month=now.month,
        )

        average = await self.get_average_income(user_id)

        count = await self.get_transactions_count(user_id)

        categories = await self.get_income_by_category(user_id)

        return {
            "total_income": total,
            "average_income": average,
            "transactions": count,
            "categories": categories,
        }

    async def compare_months(
        self,
        user_id: int,
        current_year: int,
        current_month: int,
        previous_year: int,
        previous_month: int,
    ) -> dict:
        """
        Сравнение доходов двух месяцев.
        """

        current = await self.get_monthly_income(
            user_id,
            current_year,
            current_month,
        )

        previous = await self.get_monthly_income(
            user_id,
            previous_year,
            previous_month,
        )

        difference = current - previous

        percent = (difference / previous * 100) if previous > 0 else Decimal("100")

        return {
            "current": current,
            "previous": previous,
            "difference": difference,
            "percent": round(percent, 2),
        }
