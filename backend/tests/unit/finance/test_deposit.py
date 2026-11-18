from datetime import date
from decimal import Decimal

import pytest

from app.models.enums import Capitalization as C
from app.services.finance import FinanceInputError, add_months, deposit_maturity
from tests.unit.finance import reference as ref


class TestAddMonths:
    @pytest.mark.parametrize(
        ("start", "months", "expected"),
        [
            (date(2025, 1, 31), 1, date(2025, 2, 28)),
            (date(2024, 1, 31), 1, date(2024, 2, 29)),  # leap year
            (date(2025, 1, 31), 2, date(2025, 3, 31)),  # computed from start, not chained
            (date(2025, 11, 30), 3, date(2026, 2, 28)),
            (date(2024, 2, 29), 12, date(2025, 2, 28)),
            (date(2025, 5, 15), 0, date(2025, 5, 15)),
        ],
    )
    def test_end_of_month_clamping(self, start: date, months: int, expected: date) -> None:
        assert add_months(start, months) == expected


class TestSimpleDeposit:
    def test_one_year_without_capitalization(self) -> None:
        result = deposit_maturity(
            Decimal("1000000"), Decimal("14"), date(2025, 1, 1), date(2026, 1, 1)
        )
        assert result.interest == Decimal("140000.00")
        assert result.maturity_amount == Decimal("1140000.00")
        assert result.term_days == 365
        assert result.capitalization is C.NONE

    def test_matches_previous_api_formula(self) -> None:
        # P · r · days / 365 — what /investments returned before this change.
        result = deposit_maturity(
            Decimal("100000.00"), Decimal("10.00"), date(2025, 1, 1), date(2025, 1, 31)
        )
        assert result.interest == Decimal("821.92") == ref.simple_interest("100000", "10", 30)


class TestCapitalizedDeposit:
    @pytest.mark.parametrize(
        ("principal", "rate", "start", "end", "mode", "months", "interest", "periods", "stub"),
        [
            # 1 000 000 at 16 %, monthly, exactly 12 months: 1 000 000 · ((1 + 0.16/12)^12 − 1)
            ("1000000", "16", date(2025, 1, 1), date(2026, 1, 1), C.MONTHLY, 1, "172270.80", 12, 0),
            # Quarterly from Jan 31: anniversaries Apr 30, Jul 31; 15-day stub to Aug 15.
            (
                "500000",
                "12",
                date(2025, 1, 31),
                date(2025, 8, 15),
                C.QUARTERLY,
                3,
                "33065.92",
                2,
                15,
            ),
            # Monthly from Jan 31: Feb 28, Mar 31; 10-day stub to Apr 10.
            (
                "2000000",
                "15",
                date(2025, 1, 31),
                date(2025, 4, 10),
                C.MONTHLY,
                1,
                "58738.44",
                2,
                10,
            ),
            # Monthly from Jan 31 to Mar 29: only Feb 28 is an anniversary (the next one
            # is Mar 31, NOT Mar 28 — anniversaries are not chained from clamped dates);
            # 1 000 000 · 1.01 = 1 010 000, stub 1 010 000 · 12 % · 29/365 = 9 629.59.
            (
                "1000000",
                "12",
                date(2025, 1, 31),
                date(2025, 3, 29),
                C.MONTHLY,
                1,
                "19629.59",
                1,
                29,
            ),
            # Annually from Feb 29 2024: anniversary Feb 28 2025; 183-day stub.
            (
                "300000",
                "9",
                date(2024, 2, 29),
                date(2025, 8, 30),
                C.ANNUALLY,
                12,
                "41755.32",
                1,
                183,
            ),
        ],
    )
    def test_independently_verified_cases(
        self,
        principal: str,
        rate: str,
        start: date,
        end: date,
        mode: C,
        months: int,
        interest: str,
        periods: int,
        stub: int,
    ) -> None:
        result = deposit_maturity(Decimal(principal), Decimal(rate), start, end, mode)
        assert result.interest == Decimal(interest)
        assert result.capitalization_periods == periods
        assert result.stub_days == stub
        assert result.maturity_amount == Decimal(principal) + Decimal(interest)
        assert (result.interest, periods, stub) == ref.compounded_deposit_interest(
            principal, rate, start, end, months
        )

    def test_term_shorter_than_one_period_is_simple_interest(self) -> None:
        compounded = deposit_maturity(
            Decimal("100000"), Decimal("10"), date(2025, 1, 1), date(2025, 1, 31), C.MONTHLY
        )
        simple = deposit_maturity(
            Decimal("100000"), Decimal("10"), date(2025, 1, 1), date(2025, 1, 31)
        )
        assert compounded.capitalization_periods == 0
        assert compounded.interest == simple.interest == Decimal("821.92")

    def test_more_frequent_capitalization_never_pays_less(self) -> None:
        args = (Decimal("1000000"), Decimal("15"), date(2025, 1, 1), date(2027, 1, 1))
        interests = [
            deposit_maturity(*args, mode).interest
            for mode in (C.NONE, C.ANNUALLY, C.QUARTERLY, C.MONTHLY)
        ]
        assert interests == sorted(interests)
        assert len(set(interests)) == 4

    def test_zero_rate_and_zero_principal(self) -> None:
        assert deposit_maturity(
            Decimal("500000"), Decimal("0"), date(2025, 1, 1), date(2026, 1, 1), C.MONTHLY
        ).interest == Decimal("0.00")
        assert deposit_maturity(
            Decimal("0"), Decimal("15"), date(2025, 1, 1), date(2026, 1, 1), C.MONTHLY
        ).maturity_amount == Decimal("0.00")


class TestInvalidInputs:
    @pytest.mark.parametrize(
        ("start", "end"),
        [(date(2025, 1, 1), date(2025, 1, 1)), (date(2025, 2, 1), date(2025, 1, 1))],
    )
    def test_zero_or_negative_term(self, start: date, end: date) -> None:
        with pytest.raises(FinanceInputError, match="term"):
            deposit_maturity(Decimal("1000"), Decimal("10"), start, end)

    @pytest.mark.parametrize(
        ("principal", "rate"), [("-1", "10"), ("1000", "-1"), ("1000", "1001")]
    )
    def test_invalid_amounts(self, principal: str, rate: str) -> None:
        with pytest.raises(FinanceInputError):
            deposit_maturity(Decimal(principal), Decimal(rate), date(2025, 1, 1), date(2026, 1, 1))

    def test_unknown_capitalization(self) -> None:
        with pytest.raises(ValueError):
            deposit_maturity(
                Decimal("1000"),
                Decimal("10"),
                date(2025, 1, 1),
                date(2026, 1, 1),
                "weekly",  # type: ignore[arg-type]
            )
