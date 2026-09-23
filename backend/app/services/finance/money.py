"""
Деньги в BudgetAnalytics.

Правила (единые для всего проекта):

* Тип — только Decimal. float для денег запрещён: to_decimal()
  бросает TypeError, если ему передали float.
* Точность хранения — Numeric(14, 2): тенге и тиыны.
* Округление — ROUND_HALF_UP до тиына (0.01) в конце каждого
  «денежного события»: начисление процентов за месяц, платёж,
  итоговая сумма. Промежуточные коэффициенты (ставка за месяц,
  дисконт-факторы) не округляются.
* Проценты (ставки, доли) — Decimal в процентах, 2 знака
  (RATE_QUANT можно сузить до 4 знаков для ГЭСВ).
* Валюта — ISO-код. Операции между разными валютами запрещены;
  конвертация только явная, по переданному курсу (convert()).
* Сериализация в JSON — строка с двумя знаками ("1234.50"),
  чтобы клиент не потерял точность на float (см. MoneyDecimal).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, localcontext
from enum import StrEnum
from typing import Annotated, Any

from pydantic import PlainSerializer

MONEY_QUANT = Decimal("0.01")
PERCENT_QUANT = Decimal("0.01")
ROUNDING = ROUND_HALF_UP

ZERO = Decimal("0")
ONE = Decimal("1")
HUNDRED = Decimal("100")

# Максимальное значение, которое помещается в Numeric(14, 2).
MAX_AMOUNT = Decimal("999999999999.99")


class Currency(StrEnum):
    KZT = "KZT"
    USD = "USD"
    EUR = "EUR"
    RUB = "RUB"


class MoneyError(ValueError):
    pass


class CurrencyMismatchError(MoneyError):
    pass


def to_decimal(value: Any) -> Decimal:
    """Приводит int/str/Decimal к Decimal. float и bool запрещены."""

    if isinstance(value, Decimal):
        if not value.is_finite():
            raise MoneyError("Amount must be a finite number")
        return value
    if isinstance(value, bool) or isinstance(value, float):
        raise TypeError(
            f"{type(value).__name__} is not allowed for money; use Decimal or str"
        )
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        cleaned = value.strip().replace(" ", "").replace(" ", "")
        try:
            result = Decimal(cleaned)
        except InvalidOperation as exc:
            raise MoneyError(f"Invalid amount: {value!r}") from exc
        if not result.is_finite():
            raise MoneyError("Amount must be a finite number")
        return result
    raise TypeError(f"Unsupported money type: {type(value).__name__}")


def quantize_money(value: Any) -> Decimal:
    return to_decimal(value).quantize(MONEY_QUANT, rounding=ROUNDING)


def quantize_percent(value: Any, quant: Decimal = PERCENT_QUANT) -> Decimal:
    return to_decimal(value).quantize(quant, rounding=ROUNDING)


def percent(part: Any, whole: Any) -> Decimal | None:
    """part / whole * 100, округлённое до 0.01. None, если whole == 0."""

    part_d, whole_d = to_decimal(part), to_decimal(whole)
    if whole_d == 0:
        return None
    with localcontext() as ctx:
        ctx.prec = 34
        return quantize_percent(part_d / whole_d * HUNDRED)


def percent_or_zero(part: Any, whole: Any) -> Decimal:
    value = percent(part, whole)
    return value if value is not None else Decimal("0.00")


def share(value: Any, ratio: Any) -> Decimal:
    """value * ratio, округлённое до тиына."""

    return quantize_money(to_decimal(value) * to_decimal(ratio))


@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency: Currency = Currency.KZT

    def __post_init__(self) -> None:
        object.__setattr__(self, "amount", to_decimal(self.amount))
        object.__setattr__(self, "currency", Currency(self.currency))

    @classmethod
    def zero(cls, currency: Currency | str = Currency.KZT) -> "Money":
        return cls(ZERO, Currency(currency))

    @classmethod
    def of(cls, amount: Any, currency: Currency | str = Currency.KZT) -> "Money":
        return cls(to_decimal(amount), Currency(currency))

    def _check(self, other: "Money") -> None:
        if not isinstance(other, Money):
            raise TypeError("Money can only be combined with Money")
        if other.currency != self.currency:
            raise CurrencyMismatchError(
                f"Cannot combine {self.currency} and {other.currency}"
            )

    def __add__(self, other: "Money") -> "Money":
        self._check(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: "Money") -> "Money":
        self._check(other)
        return Money(self.amount - other.amount, self.currency)

    def __mul__(self, factor: Any) -> "Money":
        if isinstance(factor, Money):
            raise TypeError("Money cannot be multiplied by Money")
        return Money(self.amount * to_decimal(factor), self.currency)

    __rmul__ = __mul__

    def __neg__(self) -> "Money":
        return Money(-self.amount, self.currency)

    def __lt__(self, other: "Money") -> bool:
        self._check(other)
        return self.amount < other.amount

    def __le__(self, other: "Money") -> bool:
        self._check(other)
        return self.amount <= other.amount

    def __gt__(self, other: "Money") -> bool:
        self._check(other)
        return self.amount > other.amount

    def __ge__(self, other: "Money") -> bool:
        self._check(other)
        return self.amount >= other.amount

    def rounded(self) -> "Money":
        return Money(quantize_money(self.amount), self.currency)

    def is_zero(self) -> bool:
        return self.amount == 0

    def convert(self, rate: Any, to: Currency | str) -> "Money":
        """Явная конвертация по курсу `rate` (единиц `to` за 1 единицу self)."""

        rate_d = to_decimal(rate)
        if rate_d <= 0:
            raise MoneyError("Exchange rate must be positive")
        return Money(quantize_money(self.amount * rate_d), Currency(to))

    def __str__(self) -> str:
        return f"{quantize_money(self.amount)} {self.currency}"


def _serialize_money(value: Decimal) -> str:
    return format(quantize_money(value), "f")


def _serialize_percent(value: Decimal) -> str:
    return format(quantize_percent(value), "f")


# Pydantic-типы для API: Decimal внутри, строка с 2 знаками в JSON.
MoneyDecimal = Annotated[
    Decimal, PlainSerializer(_serialize_money, return_type=str, when_used="json")
]
PercentDecimal = Annotated[
    Decimal, PlainSerializer(_serialize_percent, return_type=str, when_used="json")
]
