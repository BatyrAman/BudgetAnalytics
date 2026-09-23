from datetime import date, datetime

import pytest

from app.core.errors import DomainValidationError
from app.services.analytics.periods import Period, bucket_label, bucket_starts, resolve_period

TODAY = date(2025, 3, 15)  # суббота


def test_day():
    p = resolve_period(Period.DAY, TODAY)
    assert (p.date_from, p.date_to, p.granularity) == (datetime(2025, 3, 15), datetime(2025, 3, 16), "hour")
    assert len(bucket_starts(p)) == 24
    assert p.previous == (datetime(2025, 3, 14), datetime(2025, 3, 15))


def test_week_and_month():
    week = resolve_period(Period.WEEK, TODAY)
    assert week.date_from == datetime(2025, 3, 9)
    assert len(bucket_starts(week)) == 7
    month = resolve_period(Period.MONTH, TODAY)
    assert month.date_from == datetime(2025, 2, 14)
    assert len(bucket_starts(month)) == 30
    assert month.previous[0] == datetime(2025, 1, 15)


def test_half_year_weekly_buckets_start_on_monday():
    p = resolve_period(Period.HALF_YEAR, TODAY)
    assert p.granularity == "week"
    buckets = bucket_starts(p)
    assert all(b.weekday() == 0 for b in buckets)
    assert buckets[0] <= p.date_from < buckets[1]


def test_year_is_12_calendar_months():
    p = resolve_period(Period.YEAR, TODAY)
    buckets = bucket_starts(p)
    assert [bucket_label(b, "month") for b in buckets][0] == "2024-04"
    assert len(buckets) == 12
    assert bucket_label(buckets[-1], "month") == "2025-03"


def test_leap_year_month_end():
    p = resolve_period(Period.YEAR, date(2024, 2, 29))
    assert p.date_from == datetime(2023, 3, 1)
    assert len(bucket_starts(p)) == 12


@pytest.mark.parametrize(
    "start, end, granularity",
    [
        (date(2025, 1, 1), date(2025, 1, 2), "hour"),
        (date(2025, 1, 1), date(2025, 2, 28), "day"),
        (date(2025, 1, 1), date(2025, 6, 30), "week"),
        (date(2024, 1, 1), date(2025, 12, 31), "month"),
    ],
)
def test_custom_auto_granularity(start, end, granularity):
    p = resolve_period(Period.CUSTOM, TODAY, start, end)
    assert p.granularity == granularity
    # date_to включительно → полуинтервал до следующего дня
    assert p.date_from == datetime.combine(start, datetime.min.time())
    assert (p.date_to - datetime.combine(end, datetime.min.time())).days == 1


def test_dates_imply_custom():
    p = resolve_period(Period.MONTH, TODAY, date(2025, 1, 1), date(2025, 1, 31))
    assert p.period is Period.CUSTOM
    assert p.date_to == datetime(2025, 2, 1)


@pytest.mark.parametrize(
    "start, end",
    [(None, None), (date(2025, 1, 2), date(2025, 1, 1)), (date(2010, 1, 1), date(2025, 1, 1)), (date(2025, 1, 1), None)],
)
def test_invalid_custom(start, end):
    with pytest.raises(DomainValidationError):
        resolve_period(Period.CUSTOM, TODAY, start, end)
