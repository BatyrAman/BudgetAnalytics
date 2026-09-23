from decimal import Decimal

import pytest
from pydantic import BaseModel

from app.services.finance.money import (
    Currency,
    CurrencyMismatchError,
    Money,
    MoneyDecimal,
    MoneyError,
    percent,
    quantize_money,
    to_decimal,
)


def test_float_is_rejected():
    with pytest.raises(TypeError):
        to_decimal(0.1)
    with pytest.raises(TypeError):
        Money(0.1)  # type: ignore[arg-type]


def test_bool_is_rejected():
    with pytest.raises(TypeError):
        to_decimal(True)


def test_string_parsing_with_spaces_and_nbsp():
    assert to_decimal("1 234 567.89") == Decimal("1234567.89")
    assert to_decimal("12 000") == Decimal("12000")


@pytest.mark.parametrize("raw", ["abc", "NaN", "Infinity", ""])
def test_invalid_strings(raw):
    with pytest.raises(MoneyError):
        to_decimal(raw)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("0.005", "0.01"),  # half-up, не банковское округление
        ("0.015", "0.02"),
        ("0.025", "0.03"),
        ("-0.005", "-0.01"),
        ("2.344", "2.34"),
    ],
)
def test_rounding_is_half_up(raw, expected):
    assert quantize_money(raw) == Decimal(expected)


def test_classic_float_error_does_not_happen():
    total = sum((to_decimal("0.1") for _ in range(10)), Decimal("0"))
    assert total == Decimal("1.0")


def test_money_arithmetic_and_currency_guard():
    a = Money.of("100.10")
    b = Money.of("0.90")
    assert (a + b).amount == Decimal("101.00")
    assert (a - b).amount == Decimal("99.20")
    assert (a * 2).amount == Decimal("200.20")
    with pytest.raises(CurrencyMismatchError):
        _ = a + Money.of("1", Currency.USD)
    with pytest.raises(CurrencyMismatchError):
        _ = a < Money.of("1", Currency.USD)


def test_explicit_conversion_only():
    usd = Money.of("100", Currency.USD)
    kzt = usd.convert("475.555", Currency.KZT)
    assert kzt == Money.of("47555.50", Currency.KZT)
    with pytest.raises(MoneyError):
        usd.convert("0", Currency.KZT)


def test_percent_zero_division():
    assert percent(1, 0) is None
    assert percent(1, 3) == Decimal("33.33")


def test_very_large_numbers_keep_precision():
    big = to_decimal("999999999999.99")
    assert quantize_money(big * 2) == Decimal("1999999999999.98")


def test_json_serialization_is_string_with_two_decimals():
    class Out(BaseModel):
        amount: MoneyDecimal

    assert Out(amount=Decimal("10")).model_dump_json() == '{"amount":"10.00"}'
    assert Out(amount=Decimal("10.005")).model_dump(mode="json") == {"amount": "10.01"}
    # python-режим сохраняет Decimal
    assert Out(amount=Decimal("1.5")).model_dump()["amount"] == Decimal("1.5")
