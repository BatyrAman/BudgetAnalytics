from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import TransactionType
from app.models.transaction import Transaction


class ForecastingService:
    """
    Сервис прогнозирования доходов и расходов.

    В текущей версии используется среднее значение
    за последние месяцы.

    В будущем можно заменить на:
        - Prophet
        - ARIMA
        - XGBoost
        - LSTM
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _monthly_average(
        self,
        user_id: int,
        transaction_type: TransactionType,
    ) -> Decimal:
        """
        Средняя сумма операций в месяц.
        """

        stmt = (
            select(
                func.extract("year", Transaction.transaction_date).label("year"),
                func.extract("month", Transaction.transaction_date).label("month"),
                func.sum(Transaction.amount).label("total"),
            )
            .where(
                Transaction.user_id == user_id,
                Transaction.transaction_type == transaction_type,
            )
            .group_by(
                func.extract("year", Transaction.transaction_date),
                func.extract("month", Transaction.transaction_date),
            )
        )

        result = await self.db.execute(stmt)

        rows = result.all()

        if not rows:
            return Decimal("0")

        total = sum(row.total for row in rows)

        return Decimal(total / len(rows))

    async def forecast_income(
        self,
        user_id: int,
    ) -> Decimal:
        """
        Прогноз дохода следующего месяца.
        """

        return await self._monthly_average(
            user_id=user_id,
            transaction_type=TransactionType.INCOME,
        )

    async def forecast_expense(
        self,
        user_id: int,
    ) -> Decimal:
        """
        Прогноз расходов следующего месяца.
        """

        return await self._monthly_average(
            user_id=user_id,
            transaction_type=TransactionType.EXPENSE,
        )

    async def forecast_balance(
        self,
        user_id: int,
    ) -> Decimal:
        """
        Прогноз остатка.
        """

        income = await self.forecast_income(user_id)

        expense = await self.forecast_expense(user_id)

        return income - expense

    async def forecast_summary(
        self,
        user_id: int,
    ) -> dict:
        """
        Полный прогноз следующего месяца.
        """

        income = await self.forecast_income(user_id)

        expense = await self.forecast_expense(user_id)

        balance = income - expense

        if income > 0:
            saving_rate = round(
                (balance / income) * 100,
                2,
            )
        else:
            saving_rate = Decimal("0")

        return {
            "forecast_date": datetime.utcnow().date(),
            "predicted_income": income,
            "predicted_expense": expense,
            "predicted_balance": balance,
            "saving_rate": saving_rate,
        }

    async def risk_level(
        self,
        user_id: int,
    ) -> str:
        """
        Оценка риска следующего месяца.
        """

        balance = await self.forecast_balance(user_id)

        if balance >= 100000:
            return "LOW"

        if balance >= 30000:
            return "MEDIUM"

        if balance >= 0:
            return "HIGH"

        return "CRITICAL"

    async def full_forecast(
        self,
        user_id: int,
    ) -> dict:
        """
        Полный прогноз для Dashboard.
        """

        summary = await self.forecast_summary(user_id)

        summary["risk"] = await self.risk_level(user_id)

        return summary