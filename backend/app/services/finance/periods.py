"""Calendar periods and monthly / yearly summaries.

BOUNDARIES: every period is a half-open interval ``[start, end)`` of
timezone-aware instants, built from LOCAL midnight in the given time zone
(default ``Asia/Almaty``; Kazakhstan uses a single UTC+5 zone since
2024-03-01 and the IANA database encodes the earlier history):

* month ``2025-03`` = [2025-03-01 00:00 local, 2025-04-01 00:00 local)
* year  ``2025``    = [2025-01-01 00:00 local, 2026-01-01 00:00 local)

A transaction at 2025-03-31 23:59:59 local belongs to March; one at
2025-04-01 00:00:00 local belongs to April. Naive datetimes are rejected:
the caller must state the time zone of every instant.

Empty months are reported with zero totals (they are not skipped), so
averages and charts never silently drop months without activity.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.services.finance.cashflow import CashflowItem, CashflowTotals, summarize
from app.services.finance.money import CurrencySpec, FinanceInputError

DEFAULT_TIMEZONE = ZoneInfo("Asia/Almaty")


@dataclass(frozen=True)
class Period:
    label: str
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise FinanceInputError("Period boundaries must be timezone-aware")
        if self.end <= self.start:
            raise FinanceInputError("Period end must be after its start")

    def contains(self, instant: datetime) -> bool:
        if instant.tzinfo is None:
            raise FinanceInputError("Transaction time must be timezone-aware")
        return self.start <= instant < self.end


@dataclass(frozen=True)
class PeriodSummary:
    period: Period
    totals: CashflowTotals

    @property
    def savings_rate(self) -> Decimal | None:
        return self.totals.savings_rate


def _validate_year(year: int) -> None:
    if not 1900 <= year <= 2200:
        raise FinanceInputError("year must be between 1900 and 2200")


def month_period(year: int, month: int, tz: ZoneInfo = DEFAULT_TIMEZONE) -> Period:
    _validate_year(year)
    if not 1 <= month <= 12:
        raise FinanceInputError("month must be between 1 and 12")
    start = datetime(year, month, 1, tzinfo=tz)
    end = (
        datetime(year + 1, 1, 1, tzinfo=tz)
        if month == 12
        else datetime(year, month + 1, 1, tzinfo=tz)
    )
    return Period(label=f"{year:04d}-{month:02d}", start=start, end=end)


def year_period(year: int, tz: ZoneInfo = DEFAULT_TIMEZONE) -> Period:
    _validate_year(year)
    return Period(
        label=f"{year:04d}",
        start=datetime(year, 1, 1, tzinfo=tz),
        end=datetime(year + 1, 1, 1, tzinfo=tz),
    )


def summarize_period(
    items: Iterable[CashflowItem], period: Period, currency: CurrencySpec
) -> PeriodSummary:
    selected = [item for item in items if period.contains(item.occurred_at)]
    return PeriodSummary(period=period, totals=summarize(selected, currency))


def monthly_summaries(
    items: Iterable[CashflowItem],
    year: int,
    currency: CurrencySpec,
    tz: ZoneInfo = DEFAULT_TIMEZONE,
) -> list[PeriodSummary]:
    """Twelve summaries (January..December), including empty months."""

    materialized = list(items)
    return [
        summarize_period(materialized, month_period(year, month, tz), currency)
        for month in range(1, 13)
    ]


def yearly_summary(
    items: Iterable[CashflowItem],
    year: int,
    currency: CurrencySpec,
    tz: ZoneInfo = DEFAULT_TIMEZONE,
) -> PeriodSummary:
    return summarize_period(items, year_period(year, tz), currency)
