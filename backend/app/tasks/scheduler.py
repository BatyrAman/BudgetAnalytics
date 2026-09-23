"""
Расписание фоновых задач (ARQ).

ARQ выбран как async-нативный и лёгкий (Redis) вариант под
SQLAlchemy async. Зависимость опциональна: requirements-worker.txt.

    arq app.tasks.scheduler.WorkerSettings
"""

from __future__ import annotations

from app.tasks.bank_products import update_bank_products
from app.tasks.monthly_report import generate_monthly_reports
from app.tasks.payment_reminders import send_payment_reminders
from app.tasks.statement_import import process_statement_import


async def _monthly_reports(ctx) -> int:
    return await generate_monthly_reports()


async def _payment_reminders(ctx) -> int:
    return await send_payment_reminders()


async def _bank_products(ctx) -> int:
    return len(await update_bank_products())


async def _statement_import(ctx, import_id: int, content: bytes):
    return await process_statement_import(import_id, content)


try:  # pragma: no cover - требует arq/redis
    from arq import cron
    from arq.connections import RedisSettings

    from app.core.config import settings

    class WorkerSettings:
        functions = [_statement_import]
        cron_jobs = [
            cron(_payment_reminders, hour={9}, minute={0}),
            cron(_bank_products, hour={4}, minute={0}),
            cron(_monthly_reports, day={1}, hour={6}, minute={0}),
        ]
        redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)

except ImportError:  # arq не установлен — задачи доступны через app.tasks.run
    WorkerSettings = None  # type: ignore[assignment]
