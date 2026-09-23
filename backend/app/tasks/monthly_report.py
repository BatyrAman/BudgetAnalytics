"""Ежемесячный отчёт: итоги месяца и топ категорий. Идемпотентен (UPSERT)."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.reports import MonthlyReport
from app.models.user import User
from app.repositories.analytics import AnalyticsRepository, Scope
from app.services.analytics.ranges import month_range, shift_month
from app.services.finance.cashflow import savings_rate

logger = logging.getLogger(__name__)


async def build_report(session: AsyncSession, user_id: int, period_start: date) -> dict:
    repo = AnalyticsRepository(session)
    start, end = month_range(period_start.year, period_start.month)
    scope = Scope(user_id, settings.DEFAULT_CURRENCY, start, end)
    totals = await repo.totals(scope)
    categories = await repo.by_category(scope, limit=5)
    return {
        "currency": settings.DEFAULT_CURRENCY,
        "income": format(totals.income, "f"),
        "expense": format(totals.expense, "f"),
        "net": format(totals.income - totals.expense, "f"),
        "savings_rate": format(savings_rate(totals.income, totals.expense), "f"),
        "top_categories": [{"name": name, "amount": format(total, "f")} for _, name, _, total, _ in categories],
    }


async def generate_monthly_reports(
    period_start: date | None = None,
    session_factory: async_sessionmaker = SessionLocal,
) -> int:
    """Отчёт за прошлый месяц для всех активных пользователей. Повторный запуск перезаписывает."""

    period = (period_start or shift_month(date.today(), 1)).replace(day=1)
    count = 0
    async with session_factory() as session:
        user_ids = (await session.scalars(select(User.id).where(User.is_active.is_(True)))).all()
        for user_id in user_ids:
            data = await build_report(session, user_id, period)
            stmt = insert(MonthlyReport).values(user_id=user_id, period_start=period, data=data)
            await session.execute(
                stmt.on_conflict_do_update(
                    constraint="uq_monthly_reports_user_period",
                    set_={"data": stmt.excluded.data, "generated_at": datetime.now(timezone.utc)},
                )
            )
            count += 1
        await session.commit()
    logger.info("Monthly reports for %s: %s users", period, count)
    return count
