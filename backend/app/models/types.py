"""Общие типы колонок."""

from __future__ import annotations

import enum

from sqlalchemy import Enum, Numeric

# Все денежные колонки: 12 знаков до запятой, 2 после (тиыны).
MONEY = Numeric(14, 2)
# Ставки в процентах: до 999.9999%.
RATE = Numeric(7, 4)


def str_enum(enum_cls: type[enum.Enum], name: str, length: int = 32) -> Enum:
    """
    Enum, хранящийся как VARCHAR + CHECK по значениям (не нативный PG enum).
    Добавление значения — это миграция CHECK, без ALTER TYPE.
    """

    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=length,
        values_callable=lambda members: [m.value for m in members],
        validate_strings=True,
    )
