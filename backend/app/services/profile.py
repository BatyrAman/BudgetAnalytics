"""
Финансовый профиль пользователя — агрегаты для расчётов.

Только числа (доход, расходы, платежи), никаких персональных данных:
этот объект безопасно передавать в DecisionEngine и в будущий AI.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.enums import TransactionType
from app.models.user import User
from app.repositories.analytics import AnalyticsRepository, Scope
from app.repositories.debts import DebtRepository
from app.schemas.user import FinancialProfileUpdate
from app.services.finance.calendar import add_months
from app.services.finance.cashflow import monthly_average
from app.services.finance.money import ZERO, quantize_money

PROFILE_WINDOW_MONTHS = 6

# Обязательные расходы: базовые системные категории.
MANDATORY_CATEGORIES = frozenset(
    {
        "Продукты",
        "Транспорт",
        "Коммунальные услуги",
        "Связь и интернет",
        "Здоровье",
        "Образование",
    }
)


@dataclass(frozen=True, slots=True)
class FinancialProfile:
    currency: str
    monthly_income: Decimal | None
    income_source: str  # declared | transactions | none
    average_monthly_expenses: Decimal
    mandatory_expenses: Decimal
    debt_payments: Decimal
    debt_balance: Decimal
    active_debts: int
    dependents: int
    months_of_data: int


def _window(today: date) -> tuple[datetime, datetime]:
    """Последние PROFILE_WINDOW_MONTHS полных месяцев (текущий не учитывается)."""

    end = today.replace(day=1)
    start = add_months(end, -PROFILE_WINDOW_MONTHS)
    return datetime.combine(start, datetime.min.time()), datetime.combine(end, datetime.min.time())


class FinancialProfileService:
    def __init__(self, session: AsyncSession, today: date | None = None) -> None:
        self.session = session
        self.analytics = AnalyticsRepository(session)
        self.debts = DebtRepository(session)
        self.today = today or date.today()

    async def update(self, user: User, payload: FinancialProfileUpdate) -> User:
        updates = payload.model_dump(exclude_unset=True)
        consent = updates.pop("consent", None)
        for field, value in updates.items():
            if field == "dependents" and value is None:
                continue
            setattr(user, field, value)
        if consent is True and user.consent_at is None:
            user.consent_at = datetime.now(timezone.utc)
        elif consent is False:
            user.consent_at = None
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def build(self, user: User) -> FinancialProfile:
        date_from, date_to = _window(self.today)
        scope = Scope(
            user_id=user.id,
            currency=settings.DEFAULT_CURRENCY,
            date_from=date_from,
            date_to=date_to,
        )
        monthly = await self.analytics.series(scope, "month")
        months_with_data = len(monthly)

        avg_income = monthly_average([income for _, income, _ in monthly])
        avg_expense = monthly_average([expense for _, _, expense in monthly])

        categories = await self.analytics.by_category(scope, TransactionType.EXPENSE)
        mandatory_total = sum(
            (total for _, name, _, total, _ in categories if name in MANDATORY_CATEGORIES), ZERO
        )
        mandatory = quantize_money(mandatory_total / months_with_data) if months_with_data else ZERO

        if user.monthly_income_declared is not None:
            income, source = user.monthly_income_declared, "declared"
        elif months_with_data and avg_income > 0:
            income, source = avg_income, "transactions"
        else:
            income, source = None, "none"

        debts = await self.debts.list_active(user.id)
        return FinancialProfile(
            currency=settings.DEFAULT_CURRENCY,
            monthly_income=income,
            income_source=source,
            average_monthly_expenses=avg_expense,
            mandatory_expenses=mandatory,
            debt_payments=sum((d.monthly_payment for d in debts), ZERO),
            debt_balance=sum((d.balance for d in debts), ZERO),
            active_debts=len(debts),
            dependents=user.dependents or 0,
            months_of_data=months_with_data,
        )
