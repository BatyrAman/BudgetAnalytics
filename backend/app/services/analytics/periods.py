"""
Периоды аналитики и шаг группировки.

    period     диапазон                         точка графика
    day        сегодня                          час
    week       7 дней (включая сегодня)         день
    month      30 дней (включая сегодня)        день
    half_year  6 месяцев                        неделя (с понедельника)
    year       12 календарных месяцев           месяц
    custom     date_from..date_to включительно  авто: час/день/неделя/месяц

Интервалы полуоткрытые: [date_from, date_to). Предыдущий период —
такой же длины непосредственно перед текущим.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import StrEnum

from app.core.errors import DomainValidationError
from app.services.finance.calendar import add_months

MAX_CUSTOM_DAYS = 366 * 5


class Period(StrEnum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    HALF_YEAR = "half_year"
    YEAR = "year"
    CUSTOM = "custom"


@dataclass(frozen=True, slots=True)
class ResolvedPeriod:
    period: Period
    date_from: datetime
    date_to: datetime  # не включительно
    granularity: str  # hour | day | week | month

    @property
    def previous(self) -> tuple[datetime, datetime]:
        length = self.date_to - self.date_from
        return self.date_from - length, self.date_from

    @property
    def days(self) -> int:
        return max((self.date_to - self.date_from).days, 1)


def _start(d: date) -> datetime:
    return datetime.combine(d, time.min)


def _auto_granularity(days: int) -> str:
    if days <= 2:
        return "hour"
    if days <= 62:
        return "day"
    if days <= 190:
        return "week"
    return "month"


def resolve_period(
    period: Period,
    today: date,
    date_from: date | None = None,
    date_to: date | None = None,
) -> ResolvedPeriod:
    if date_from is not None or date_to is not None or period is Period.CUSTOM:
        if date_from is None or date_to is None:
            raise DomainValidationError(
                "date_from and date_to are required for a custom period",
                code="INVALID_PERIOD",
            )
        if date_from > date_to:
            raise DomainValidationError("date_from must be <= date_to", code="INVALID_PERIOD")
        days = (date_to - date_from).days + 1
        if days > MAX_CUSTOM_DAYS:
            raise DomainValidationError(
                f"Custom period cannot exceed {MAX_CUSTOM_DAYS} days", code="INVALID_PERIOD"
            )
        return ResolvedPeriod(
            Period.CUSTOM, _start(date_from), _start(date_to + timedelta(days=1)), _auto_granularity(days)
        )

    end = _start(today + timedelta(days=1))
    if period is Period.DAY:
        return ResolvedPeriod(period, _start(today), end, "hour")
    if period is Period.WEEK:
        return ResolvedPeriod(period, _start(today - timedelta(days=6)), end, "day")
    if period is Period.MONTH:
        return ResolvedPeriod(period, _start(today - timedelta(days=29)), end, "day")
    if period is Period.HALF_YEAR:
        return ResolvedPeriod(period, _start(add_months(today, -6) + timedelta(days=1)), end, "week")
    return ResolvedPeriod(period, _start(add_months(today.replace(day=1), -11)), end, "month")


def bucket_starts(resolved: ResolvedPeriod) -> list[datetime]:
    """Все точки графика периода — чтобы пустые интервалы были нулями, а не дырами."""

    start = resolved.date_from
    g = resolved.granularity
    if g == "hour":
        cursor = start.replace(minute=0, second=0, microsecond=0)
        step = timedelta(hours=1)
    elif g == "day":
        cursor = start.replace(hour=0, minute=0, second=0, microsecond=0)
        step = timedelta(days=1)
    elif g == "week":
        cursor = _start(start.date() - timedelta(days=start.weekday()))
        step = timedelta(days=7)
    else:
        cursor = _start(start.date().replace(day=1))
        step = None

    buckets: list[datetime] = []
    while cursor < resolved.date_to:
        buckets.append(cursor)
        cursor = cursor + step if step else _start(add_months(cursor.date(), 1))
    return buckets


def bucket_label(bucket: datetime, granularity: str) -> str:
    if granularity == "hour":
        return bucket.strftime("%Y-%m-%d %H:00")
    if granularity == "month":
        return bucket.strftime("%Y-%m")
    return bucket.strftime("%Y-%m-%d")
