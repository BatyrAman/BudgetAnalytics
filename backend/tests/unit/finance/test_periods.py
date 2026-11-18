from datetime import UTC, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.models.enums import TransactionType as T
from app.services.finance import (
    KZT,
    CashflowItem,
    FinanceInputError,
    month_period,
    monthly_summaries,
    summarize_period,
    year_period,
    yearly_summary,
)

ALMATY = ZoneInfo("Asia/Almaty")


def at(utc: str, amount: str = "100", kind: T = T.EXPENSE) -> CashflowItem:
    return CashflowItem(Decimal(amount), kind, "KZT", datetime.fromisoformat(utc))


class TestBoundaries:
    def test_month_is_half_open_in_local_time(self) -> None:
        march = month_period(2025, 3, ALMATY)
        # Almaty is UTC+5 since 2024-03-01.
        assert march.start == datetime(2025, 2, 28, 19, 0, tzinfo=UTC)
        assert march.end == datetime(2025, 3, 31, 19, 0, tzinfo=UTC)
        assert march.contains(datetime.fromisoformat("2025-03-31T18:59:59+00:00"))  # 23:59:59 local
        assert not march.contains(
            datetime.fromisoformat("2025-03-31T19:00:00+00:00")
        )  # Apr 1 00:00

    def test_historical_offset_is_used_before_2024_change(self) -> None:
        # Before 2024-03-01 Almaty was UTC+6: 2024-01-31T18:00Z is Feb 1 00:00 local.
        february = month_period(2024, 2, ALMATY)
        assert february.contains(datetime.fromisoformat("2024-01-31T18:00:00+00:00"))
        assert not month_period(2024, 1, ALMATY).contains(
            datetime.fromisoformat("2024-01-31T18:00:00+00:00")
        )

    def test_december_rolls_into_next_year(self) -> None:
        december = month_period(2025, 12, ALMATY)
        assert december.end == datetime(2026, 1, 1, tzinfo=ALMATY)
        assert december.label == "2025-12"

    def test_leap_february(self) -> None:
        feb = month_period(2024, 2, ALMATY)
        assert feb.contains(datetime(2024, 2, 29, 23, 59, tzinfo=ALMATY))

    def test_same_instant_differs_by_timezone(self) -> None:
        instant = datetime.fromisoformat("2025-03-31T20:00:00+00:00")
        assert not month_period(2025, 3, ALMATY).contains(instant)  # Apr 1 01:00 in Almaty
        assert month_period(2025, 3, ZoneInfo("UTC")).contains(instant)

    def test_naive_instant_is_rejected(self) -> None:
        with pytest.raises(FinanceInputError, match="timezone-aware"):
            month_period(2025, 3, ALMATY).contains(datetime(2025, 3, 10))

    @pytest.mark.parametrize(("year", "month"), [(2025, 0), (2025, 13), (1800, 1)])
    def test_invalid_period(self, year: int, month: int) -> None:
        with pytest.raises(FinanceInputError):
            month_period(year, month, ALMATY)


class TestSummaries:
    ITEMS = [
        at("2025-01-10T06:00:00+00:00", "300000", T.INCOME),
        at("2025-01-31T18:59:59+00:00", "1000"),  # Jan 31 23:59:59 local -> January
        at("2025-01-31T19:00:00+00:00", "2000"),  # Feb 1 00:00 local -> February
        at("2025-03-05T06:00:00+00:00", "50000"),
        at("2025-03-06T06:00:00+00:00", "10000", T.REFUND),
        at("2025-12-31T18:59:59+00:00", "700"),  # Dec 31 23:59:59 local -> 2025
        at("2025-12-31T19:00:00+00:00", "999"),  # Jan 1 2026 local -> excluded
        at("2024-12-31T18:59:59+00:00", "888"),  # Dec 31 2024 local -> excluded
    ]

    def test_twelve_months_including_empty_ones(self) -> None:
        months = monthly_summaries(self.ITEMS, 2025, KZT, ALMATY)
        assert [m.period.label for m in months] == [f"2025-{i:02d}" for i in range(1, 13)]
        expenses = {m.period.label: m.totals.net_expenses for m in months}
        assert expenses["2025-01"] == Decimal("1000.00")
        assert expenses["2025-02"] == Decimal("2000.00")
        assert expenses["2025-03"] == Decimal("40000.00")  # 50 000 − 10 000 refund
        assert expenses["2025-04"] == Decimal("0.00")  # empty month is present, not skipped
        assert expenses["2025-12"] == Decimal("700.00")
        assert months[0].savings_rate == Decimal("99.67")  # (300 000 − 1 000) / 300 000
        assert months[1].savings_rate is None  # no income in February

    def test_months_add_up_to_the_year(self) -> None:
        months = monthly_summaries(self.ITEMS, 2025, KZT, ALMATY)
        year = yearly_summary(self.ITEMS, 2025, KZT, ALMATY)
        assert sum(m.totals.income for m in months) == year.totals.income == Decimal("300000.00")
        assert sum(m.totals.net_expenses for m in months) == year.totals.net_expenses
        assert year.totals.net_expenses == Decimal("43700.00")  # 1000 + 2000 + 40000 + 700
        assert sum(m.totals.transaction_count for m in months) == year.totals.transaction_count == 6

    def test_period_without_items(self) -> None:
        summary = summarize_period([], year_period(2030, ALMATY), KZT)
        assert summary.totals.net_cash_flow == Decimal("0.00")
        assert summary.savings_rate is None
