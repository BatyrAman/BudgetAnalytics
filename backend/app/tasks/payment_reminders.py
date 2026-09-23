"""
Напоминания о платежах за 3 дня и в день платежа.

Идемпотентность: запись в payment_reminders вставляется через
ON CONFLICT DO NOTHING RETURNING — уведомление уходит только для
реально вставленных строк, повторный запуск ничего не дублирует.
"""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.database import SessionLocal
from app.models.debt import Debt
from app.models.reports import PaymentReminder
from app.services.finance.calendar import next_payment_date
from app.tasks.notifier import LoggingNotifier, Notifier, PaymentReminderMessage

logger = logging.getLogger(__name__)

REMINDER_KINDS = {3: "before_3_days", 0: "due_day"}


async def send_payment_reminders(
    today: date | None = None,
    notifier: Notifier | None = None,
    session_factory: async_sessionmaker = SessionLocal,
) -> int:
    today = today or date.today()
    notifier = notifier or LoggingNotifier()
    sent = 0
    async with session_factory() as session:
        debts = (
            await session.scalars(select(Debt).where(Debt.is_active.is_(True), Debt.balance > 0))
        ).all()
        messages: list[PaymentReminderMessage] = []
        for debt in debts:
            due = next_payment_date(today, debt.payment_day)
            kind = REMINDER_KINDS.get((due - today).days)
            if kind is None:
                continue
            inserted = await session.scalar(
                insert(PaymentReminder)
                .values(user_id=debt.user_id, debt_id=debt.id, due_date=due, kind=kind)
                .on_conflict_do_nothing(constraint="uq_payment_reminders_once")
                .returning(PaymentReminder.id)
            )
            if inserted is not None:
                messages.append(PaymentReminderMessage(debt.user_id, debt.id, due, kind))
        # Сначала фиксируем факт отправки, затем отправляем: лучше
        # потерять одно напоминание при сбое, чем слать дубли.
        await session.commit()
    for message in messages:
        await notifier.send_payment_reminder(message)
        sent += 1
    logger.info("Payment reminders sent: %s", sent)
    return sent
