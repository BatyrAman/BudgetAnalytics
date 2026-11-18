"""Expected values come from tests/unit/finance/reference.py (exact rational
arithmetic, no shared code with the engine) and, where noted, from standard
textbook examples."""

from decimal import Decimal

import pytest

from app.services.finance import (
    KZT,
    DayCount,
    FinanceInputError,
    compound_amount,
    compound_interest,
    effective_annual_rate,
    inflation_adjusted_return,
    simple_interest,
)
from tests.unit.finance import reference as ref


class TestSimpleInterest:
    @pytest.mark.parametrize(
        ("principal", "rate", "days", "basis", "expected"),
        [
            ("1000000", "14", 365, DayCount.ACT_365_FIXED, "140000.00"),
            ("100000", "10", 30, DayCount.ACT_365_FIXED, "821.92"),  # 821.9178...
            ("100000", "10", 30, DayCount.ACT_360, "833.33"),  # 833.3333...
            ("365000", "10", 366, DayCount.ACT_365_FIXED, "36600.00"),  # leap year, /365
            ("365", "0.5", 1, DayCount.ACT_365_FIXED, "0.01"),  # exactly 0.005 -> HALF_UP
            ("0", "15", 100, DayCount.ACT_365_FIXED, "0.00"),  # zero principal
            ("500000", "0", 100, DayCount.ACT_365_FIXED, "0.00"),  # zero rate
            ("500000", "15", 0, DayCount.ACT_365_FIXED, "0.00"),  # zero days
        ],
    )
    def test_values(
        self, principal: str, rate: str, days: int, basis: DayCount, expected: str
    ) -> None:
        result = simple_interest(Decimal(principal), Decimal(rate), days, KZT, basis)
        assert result == Decimal(expected)
        assert result == ref.simple_interest(principal, rate, days, int(basis))

    @pytest.mark.parametrize(
        ("principal", "rate", "days"),
        [("-1", "10", 10), ("100", "-0.01", 10), ("100", "1000.01", 10)],
    )
    def test_invalid_inputs(self, principal: str, rate: str, days: int) -> None:
        with pytest.raises(FinanceInputError):
            simple_interest(Decimal(principal), Decimal(rate), days)

    def test_negative_days(self) -> None:
        with pytest.raises(FinanceInputError):
            simple_interest(Decimal("100"), Decimal("10"), -1)

    def test_float_rate_is_rejected(self) -> None:
        with pytest.raises(TypeError):
            simple_interest(Decimal("100"), 10.5, 10)  # type: ignore[arg-type]


class TestCompound:
    def test_textbook_example(self) -> None:
        # 1 000 at 5 % compounded annually for 10 years = 1 628.89 (1.05^10 = 1.628894...)
        assert compound_amount(Decimal("1000"), Decimal("5"), 1, 10) == Decimal("1628.89")

    @pytest.mark.parametrize(
        ("principal", "rate", "per_year", "periods"),
        [
            ("1000000", "16", 12, 12),
            ("2500000.55", "13.75", 4, 20),
            ("99.99", "1", 365, 365),
            ("1000000", "12", 12, 360),  # 30 years monthly
            ("0.01", "200", 1, 3),
        ],
    )
    def test_matches_exact_rational_reference(
        self, principal: str, rate: str, per_year: int, periods: int
    ) -> None:
        expected = ref.compound_amount(principal, rate, per_year, periods)
        assert compound_amount(Decimal(principal), Decimal(rate), per_year, periods) == expected
        assert compound_interest(
            Decimal(principal), Decimal(rate), per_year, periods
        ) == expected - Decimal(principal)

    def test_zero_periods_returns_principal(self) -> None:
        assert compound_amount(Decimal("1234.56"), Decimal("20"), 12, 0) == Decimal("1234.56")

    def test_zero_rate_returns_principal(self) -> None:
        assert compound_interest(Decimal("1000"), Decimal("0"), 12, 120) == Decimal("0.00")

    def test_compounding_more_often_never_earns_less(self) -> None:
        amounts = [
            compound_amount(Decimal("1000000"), Decimal("15"), m, m) for m in (1, 2, 4, 12, 365)
        ]
        assert amounts == sorted(amounts)

    @pytest.mark.parametrize(("per_year", "periods"), [(0, 1), (12, -1)])
    def test_invalid_periods(self, per_year: int, periods: int) -> None:
        with pytest.raises(FinanceInputError):
            compound_amount(Decimal("100"), Decimal("10"), per_year, periods)


class TestEffectiveAnnualRate:
    @pytest.mark.parametrize(
        ("nominal", "per_year", "expected"),
        [
            ("12", 12, "12.6825"),  # textbook: (1.01)^12 − 1 = 12.6825 %
            ("18", 4, "19.2519"),  # (1.045)^4 − 1 = 19.25186 %
            ("16", 12, "17.2271"),
            ("10", 365, "10.5156"),
            ("14", 1, "14.0000"),  # annual compounding: EAR = nominal
            ("0", 12, "0.0000"),
        ],
    )
    def test_values(self, nominal: str, per_year: int, expected: str) -> None:
        assert effective_annual_rate(Decimal(nominal), per_year) == Decimal(expected)
        assert effective_annual_rate(Decimal(nominal), per_year) == ref.effective_annual_rate(
            nominal, per_year
        )

    def test_invalid(self) -> None:
        with pytest.raises(FinanceInputError):
            effective_annual_rate(Decimal("-1"), 12)
        with pytest.raises(FinanceInputError):
            effective_annual_rate(Decimal("10"), 0)


class TestInflationAdjustedReturn:
    @pytest.mark.parametrize(
        ("nominal", "inflation", "expected"),
        [
            ("10", "8.5", "1.3825"),  # 1.10 / 1.085 − 1
            ("14.5", "8.4", "5.6273"),
            ("5", "-2", "7.1429"),  # deflation raises the real return
            ("8", "8", "0.0000"),
            ("0", "10", "-9.0909"),  # holding cash during 10 % inflation
            ("-100", "5", "-100.0000"),  # total loss
        ],
    )
    def test_exact_fisher_relation(self, nominal: str, inflation: str, expected: str) -> None:
        result = inflation_adjusted_return(Decimal(nominal), Decimal(inflation))
        assert result == Decimal(expected)
        assert result == ref.real_return(nominal, inflation)

    def test_not_the_naive_subtraction(self) -> None:
        # Naive 10 − 8.5 = 1.5 % overstates the real return.
        assert inflation_adjusted_return(Decimal("10"), Decimal("8.5")) != Decimal("1.5000")

    @pytest.mark.parametrize(("nominal", "inflation"), [("10", "-100"), ("-100.01", "5")])
    def test_invalid(self, nominal: str, inflation: str) -> None:
        with pytest.raises(FinanceInputError):
            inflation_adjusted_return(Decimal(nominal), Decimal(inflation))
