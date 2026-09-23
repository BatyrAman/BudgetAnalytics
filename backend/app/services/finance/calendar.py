"""Календарные хелперы для графиков платежей (конец месяца, високосные годы)."""

from __future__ import annotations

import calendar
from datetime import date


def days_in_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def clamp_day(year: int, month: int, day: int) -> date:
    """Дата с днём `day`, прижатым к концу месяца (31 → 28/29/30)."""

    return date(year, month, min(max(day, 1), days_in_month(year, month)))


def add_months(base: date, months: int, day: int | None = None) -> date:
    """
    Сдвигает дату на `months` месяцев.

    `day` — желаемый день платежа (по умолчанию день base).
    Если в целевом месяце такого дня нет, берётся последний день
    месяца: 31 января + 1 месяц = 28/29 февраля, а через ещё месяц
    снова 31 марта (якорный день не «съезжает»).
    """

    index = base.year * 12 + (base.month - 1) + months
    year, month = divmod(index, 12)
    return clamp_day(year, month + 1, day if day is not None else base.day)


def next_payment_date(today: date, payment_day: int) -> date:
    """Ближайшая дата платежа с днём payment_day, не раньше today."""

    candidate = clamp_day(today.year, today.month, payment_day)
    if candidate < today:
        candidate = add_months(candidate, 1, payment_day)
    return candidate


def month_start(value: date) -> date:
    return value.replace(day=1)


def months_between(start: date, end: date) -> int:
    """Полных месяцев между датами (не меньше 0)."""

    months = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day < start.day and end.day != days_in_month(end.year, end.month):
        months -= 1
    return max(months, 0)
