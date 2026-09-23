"""Базовые метрики денежного потока (чистые функции)."""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

from app.services.finance.money import ZERO, percent, quantize_money, to_decimal


def net_cash_flow(income, expense) -> Decimal:
    return quantize_money(to_decimal(income) - to_decimal(expense))


def savings_rate(income, expense) -> Decimal:
    """(доход - расход) / доход * 100. 0 при нулевом доходе."""

    income_d = to_decimal(income)
    if income_d <= 0:
        return Decimal("0.00")
    return percent(income_d - to_decimal(expense), income_d)


def growth_percent(current, previous) -> Decimal | None:
    """Изменение к прошлому периоду в %, None если прошлого значения нет."""

    previous_d = to_decimal(previous)
    if previous_d <= 0:
        return None
    return percent(to_decimal(current) - previous_d, previous_d)


def monthly_average(totals: Iterable) -> Decimal:
    values = [to_decimal(v) for v in totals]
    if not values:
        return Decimal("0.00")
    return quantize_money(sum(values, ZERO) / len(values))
