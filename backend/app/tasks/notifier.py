from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Protocol

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PaymentReminderMessage:
    user_id: int
    debt_id: int
    due_date: date
    kind: str


class Notifier(Protocol):
    async def send_payment_reminder(self, message: PaymentReminderMessage) -> None: ...


class LoggingNotifier:
    """Заглушка канала доставки (push/e-mail/Telegram появятся позже). Суммы не логируются."""

    async def send_payment_reminder(self, message: PaymentReminderMessage) -> None:
        logger.info(
            "Payment reminder: user=%s debt=%s due=%s kind=%s",
            message.user_id,
            message.debt_id,
            message.due_date,
            message.kind,
        )
