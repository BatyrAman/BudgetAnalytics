from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.models.enums import TransactionType as T
from app.services.finance import (
    KZT,
    CashflowItem,
    CurrencySpec,
    FinanceInputError,
    net_cash_flow,
    savings_rate,
    summarize,
    summarize_by_currency,
    total_expenses,
    total_income,
)

WHEN = datetime(2025, 3, 15, 12, tzinfo=UTC)
USD = CurrencySpec("USD", 2)


def item(amount: str, kind: T, currency: str = "KZT") -> CashflowItem:
    return CashflowItem(Decimal(amount), kind, currency, WHEN)


# Hand-checked month: salary 500 000, side income 75 000.50, groceries 120 000,
# rent 230 000, refund 20 000 (for groceries), transfer to savings 100 000.
MONTH = [
    item("500000.00", T.INCOME),
    item("75000.50", T.INCOME),
    item("120000.00", T.EXPENSE),
    item("230000.00", T.EXPENSE),
    item("20000.00", T.REFUND),
    item("100000.00", T.TRANSFER_OUT),
    item("100000.00", T.TRANSFER_IN),
]


class TestSummarize:
    def test_hand_checked_month(self) -> None:
        totals = summarize(MONTH, KZT)
        assert totals.income == Decimal("575000.50")
        assert totals.gross_expenses == Decimal("350000.00")
        assert totals.refunds == Decimal("20000.00")
        assert totals.net_expenses == Decimal("330000.00")  # 350 000 − 20 000
        assert totals.net_cash_flow == Decimal("245000.50")  # 575 000.50 − 330 000
        assert totals.transfers_in == totals.transfers_out == Decimal("100000.00")
        assert totals.transaction_count == 7

    def test_transfers_do_not_change_income_expenses_or_cash_flow(self) -> None:
        without_transfers = [
            i for i in MONTH if i.transaction_type not in (T.TRANSFER_IN, T.TRANSFER_OUT)
        ]
        a, b = summarize(MONTH, KZT), summarize(without_transfers, KZT)
        assert (a.income, a.net_expenses, a.net_cash_flow) == (
            b.income,
            b.net_expenses,
            b.net_cash_flow,
        )

    def test_refund_is_not_income(self) -> None:
        totals = summarize([item("5000", T.REFUND)], KZT)
        assert totals.income == Decimal("0.00")
        assert totals.net_expenses == Decimal("-5000.00")

    def test_empty_input_gives_zero_totals(self) -> None:
        totals = summarize([], KZT)
        assert totals.income == totals.net_expenses == totals.net_cash_flow == Decimal("0.00")
        assert totals.transaction_count == 0
        assert totals.savings_rate is None

    def test_thin_wrappers(self) -> None:
        assert total_income(MONTH, KZT) == Decimal("575000.50")
        assert total_expenses(MONTH, KZT) == Decimal("330000.00")
        assert net_cash_flow(MONTH, KZT) == Decimal("245000.50")

    def test_many_small_amounts_have_no_float_drift(self) -> None:
        # 0.10 added 1000 times is exactly 100.00 (binary floats give 99.9999999999986).
        totals = summarize([item("0.10", T.EXPENSE)] * 1000, KZT)
        assert totals.gross_expenses == Decimal("100.00")

    def test_very_large_amounts(self) -> None:
        big = "9999999999999999.99"  # NUMERIC(18,2) maximum
        totals = summarize([item(big, T.INCOME), item(big, T.INCOME)], KZT)
        assert totals.income == Decimal("19999999999999999.98")

    @pytest.mark.parametrize("amount", ["0", "-1.00"])
    def test_non_positive_amount_is_rejected(self, amount: str) -> None:
        with pytest.raises(FinanceInputError, match="greater than zero"):
            summarize([item(amount, T.EXPENSE)], KZT)


class TestCurrencies:
    def test_mixed_currencies_are_never_added(self) -> None:
        with pytest.raises(FinanceInputError, match="exchange rate"):
            summarize([item("100", T.INCOME), item("100", T.INCOME, "USD")], KZT)

    def test_grouping_by_currency(self) -> None:
        result = summarize_by_currency(
            [item("100", T.INCOME), item("40", T.EXPENSE, "USD"), item("60", T.INCOME, "USD")],
            {"KZT": KZT, "USD": USD},
        )
        assert list(result) == ["KZT", "USD"]
        assert result["KZT"].income == Decimal("100.00")
        assert result["USD"].net_cash_flow == Decimal("20.00")

    def test_unknown_currency_in_grouping(self) -> None:
        with pytest.raises(FinanceInputError, match="Unknown currency"):
            summarize_by_currency([item("1", T.INCOME, "EUR")], {"KZT": KZT})


class TestSavingsRate:
    @pytest.mark.parametrize(
        ("income", "net_expenses", "expected"),
        [
            ("500000", "330000", "34.00"),  # (500 000 − 330 000) / 500 000
            ("575000.50", "330000", "42.61"),  # 245 000.50 / 575 000.50 = 0.426087...
            ("100000", "100000", "0.00"),
            ("100000", "150000", "-50.00"),  # spending more than earned
            ("100000", "0", "100.00"),
            ("100000", "-5000", "105.00"),  # refunds exceeded expenses
            ("3", "2", "33.33"),
            ("3", "1", "66.67"),
        ],
    )
    def test_values(self, income: str, net_expenses: str, expected: str) -> None:
        assert savings_rate(Decimal(income), Decimal(net_expenses)) == Decimal(expected)

    def test_zero_income_is_undefined_not_zero(self) -> None:
        assert savings_rate(Decimal(0), Decimal(1000)) is None
        assert savings_rate(Decimal(0), Decimal(0)) is None

    def test_negative_income_is_rejected(self) -> None:
        with pytest.raises(FinanceInputError):
            savings_rate(Decimal("-1"), Decimal(0))
