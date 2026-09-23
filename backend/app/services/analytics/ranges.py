from __future__ import annotations

from datetime import date, datetime, time

from app.services.finance.calendar import add_months


def month_range(year: int, month: int) -> tuple[datetime, datetime]:
    start = date(year, month, 1)
    return datetime.combine(start, time.min), datetime.combine(add_months(start, 1), time.min)


def shift_month(base: date, months_back: int) -> date:
    """Первое число месяца, отстоящего на months_back месяцев назад."""

    return add_months(base.replace(day=1), -months_back)
