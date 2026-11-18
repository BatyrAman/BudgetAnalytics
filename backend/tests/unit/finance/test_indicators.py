from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.models.enums import TransactionType as T
from app.services.finance import (
    KZT,
    CashflowItem,
    FinanceInputError,
    account_balance,
    average,
    emergency_fund_months,
    expense_to_income_percent,
    percent_change,
    share_percent,
    summarize,
    totals_from_sums,
)

D = Decimal


class TestTotalsFromSums:
    def test_equals_row_by_row_summary(self) -> None:
        items = [
            CashflowItem(D(a), t, "KZT", datetime(2025, 1, 1, tzinfo=UTC))
            for a, t in [
                ("500000", T.INCOME),
                ("120000", T.EXPENSE),
                ("20000", T.REFUND),
                ("5000", T.TRANSFER_OUT),
            ]
        ]
        sums = {
            T.INCOME: D("500000"),
            T.EXPENSE: D("120000"),
            T.REFUND: D("20000"),
            T.TRANSFER_OUT: D("5000"),
        }
        assert totals_from_sums(sums, 4, KZT) == summarize(items, KZT)

    def test_missing_types_are_zero(self) -> None:
        totals = totals_from_sums({}, 0, KZT)
        assert totals.income == totals.net_cash_flow == D("0.00")
        assert totals.savings_rate is None

    @pytest.mark.parametrize("sums", [{T.INCOME: D("-1")}, {T.EXPENSE: D("NaN")}])
    def test_invalid_sums(self, sums: dict[T, Decimal]) -> None:
        with pytest.raises(FinanceInputError):
            totals_from_sums(sums, 1, KZT)


class TestPercentChange:
    @pytest.mark.parametrize(
        ("current", "previous", "expected"),
        [
            ("150", "100", "50.00"),
            ("50", "100", "-50.00"),
            ("100", "100", "0.00"),
            ("0", "100", "-100.00"),
            ("1", "3", "-66.67"),
            ("-50", "-100", "50.00"),  # relative to |previous|: less negative = improvement
            ("100", "-100", "200.00"),
        ],
    )
    def test_values(self, current: str, previous: str, expected: str) -> None:
        assert percent_change(D(current), D(previous)) == D(expected)

    def test_from_zero_is_undefined(self) -> None:
        assert percent_change(D("100"), D("0")) is None
        assert percent_change(D("0"), D("0")) is None


class TestShares:
    def test_share(self) -> None:
        assert share_percent(D("1"), D("3")) == D("33.33")
        assert share_percent(D("2"), D("3")) == D("66.67")

    @pytest.mark.parametrize("total", ["0", "-10"])
    def test_non_positive_total(self, total: str) -> None:
        assert share_percent(D("1"), D(total)) is None

    def test_expense_to_income(self) -> None:
        assert expense_to_income_percent(D("500000"), D("330000")) == D("66.00")
        assert expense_to_income_percent(D("0"), D("10")) is None
        with pytest.raises(FinanceInputError):
            expense_to_income_percent(D("-1"), D("10"))


class TestEmergencyFund:
    @pytest.mark.parametrize(
        ("balance", "avg", "expected"),
        [
            ("900000", "300000", "3.00"),
            ("1000000", "300000", "3.33"),
            ("-50000", "300000", "0.00"),  # debt covers nothing
            ("0", "300000", "0.00"),
        ],
    )
    def test_months(self, balance: str, avg: str, expected: str) -> None:
        assert emergency_fund_months(D(balance), D(avg)) == D(expected)

    @pytest.mark.parametrize("avg", ["0", "-1"])
    def test_undefined_without_spending(self, avg: str) -> None:
        assert emergency_fund_months(D("100"), D(avg)) is None


class TestAverageAndBalance:
    def test_average(self) -> None:
        assert average([D("100"), D("200"), D("300")], KZT) == D("200.00")
        assert average([D("1"), D("1"), D("2")], KZT) == D("1.33")
        assert average([], KZT) is None

    def test_account_balance(self) -> None:
        # 100 000 opening + 250 000 income + 3 000 refund + 50 000 in
        # − 80 000 expense − 20 000 out = 303 000
        sums = {
            T.INCOME: D("250000"),
            T.REFUND: D("3000"),
            T.TRANSFER_IN: D("50000"),
            T.EXPENSE: D("80000"),
            T.TRANSFER_OUT: D("20000"),
        }
        assert account_balance(D("100000"), sums, KZT) == D("303000.00")

    def test_balance_can_be_negative(self) -> None:
        assert account_balance(D("-5000.50"), {T.EXPENSE: D("1000")}, KZT) == D("-6000.50")
