from decimal import Decimal

import pytest

from app.services.finance.money import (
    KZT,
    CurrencySpec,
    FinanceInputError,
    quantize_money,
    quantize_rate_percent,
    quantize_ratio_percent,
    require_positive,
    to_decimal,
)


class TestInputValidation:
    def test_float_is_rejected(self) -> None:
        with pytest.raises(TypeError, match="Decimal or int"):
            to_decimal(0.1, "amount")  # type: ignore[arg-type]

    def test_bool_is_rejected(self) -> None:
        with pytest.raises(TypeError):
            to_decimal(True, "amount")  # type: ignore[arg-type]

    def test_string_is_rejected(self) -> None:
        with pytest.raises(TypeError):
            to_decimal("100", "amount")  # type: ignore[arg-type]

    @pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")])
    def test_non_finite_is_rejected(self, value: Decimal) -> None:
        with pytest.raises(FinanceInputError, match="finite"):
            to_decimal(value, "amount")

    def test_int_is_accepted_exactly(self) -> None:
        assert to_decimal(5, "x") == Decimal(5)

    @pytest.mark.parametrize("value", [Decimal(0), Decimal("-0.01")])
    def test_require_positive(self, value: Decimal) -> None:
        with pytest.raises(FinanceInputError, match="greater than zero"):
            require_positive(value, "amount")


class TestRounding:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("0.005", "0.01"),  # half up, not banker's rounding (would give 0.00)
            ("0.015", "0.02"),
            ("0.025", "0.03"),  # banker's rounding would give 0.02
            ("0.004999", "0.00"),
            ("-0.005", "-0.01"),  # symmetric: half away from zero
            ("1234567.895", "1234567.90"),
            ("100", "100.00"),
        ],
    )
    def test_money_is_half_up_to_minor_units(self, value: str, expected: str) -> None:
        result = quantize_money(Decimal(value), KZT)
        assert result == Decimal(expected)
        assert result.as_tuple().exponent == -2

    def test_currency_precision_is_respected(self) -> None:
        assert quantize_money(Decimal("1234.5"), CurrencySpec("JPY", 0)) == Decimal("1235")
        assert quantize_money(Decimal("1.2345"), CurrencySpec("KWD", 3)) == Decimal("1.235")

    def test_rate_and_ratio_precision(self) -> None:
        assert quantize_rate_percent(Decimal("12.68250301")) == Decimal("12.6825")
        assert quantize_ratio_percent(Decimal("33.333333")) == Decimal("33.33")


class TestCurrencySpec:
    @pytest.mark.parametrize("code", ["kzt", "KZ", "KZTT", "K1T", ""])
    def test_invalid_codes(self, code: str) -> None:
        with pytest.raises(FinanceInputError):
            CurrencySpec(code, 2)

    def test_invalid_minor_units(self) -> None:
        with pytest.raises(FinanceInputError):
            CurrencySpec("KZT", 5)
