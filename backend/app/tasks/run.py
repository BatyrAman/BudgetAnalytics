"""
Запуск задач без очереди (cron/systemd timer):

    python -m app.tasks.run payment_reminders
    python -m app.tasks.run monthly_reports
    python -m app.tasks.run bank_products
"""

from __future__ import annotations

import asyncio
import sys

from app.core.config import settings
from app.core.logging import configure_logging
from app.tasks.bank_products import update_bank_products
from app.tasks.monthly_report import generate_monthly_reports
from app.tasks.payment_reminders import send_payment_reminders

TASKS = {
    "payment_reminders": send_payment_reminders,
    "monthly_reports": generate_monthly_reports,
    "bank_products": update_bank_products,
}


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in TASKS:
        print(f"usage: python -m app.tasks.run [{'|'.join(TASKS)}]", file=sys.stderr)
        return 2
    configure_logging(settings.LOG_LEVEL, settings.LOG_JSON)
    asyncio.run(TASKS[argv[1]]())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
