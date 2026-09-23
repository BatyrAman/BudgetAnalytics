"""
Нормализация строк выписки в DTO и стабильный хеш для дедупликации.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.models.enums import TransactionType
from app.services.finance.money import quantize_money
from app.services.parser.base import ParsedRow

_SPACES = re.compile(r"\s+")


def normalize_text(value: str | None) -> str:
    return _SPACES.sub(" ", value or "").strip()


def normalize_merchant(description: str | None) -> str | None:
    """Название контрагента для группировки: пробелы схлопнуты, верхний регистр."""

    text = normalize_text(description)
    return text.upper()[:255] if text else None


@dataclass(frozen=True, slots=True)
class NormalizedTransaction:
    row_number: int
    transaction_date: datetime
    amount: Decimal
    transaction_type: TransactionType
    currency: str
    description: str | None
    merchant: str | None
    operation: str | None
    category_hint: str | None
    external_hash: str


def account_key(bank_id: int, card_id: int | None) -> str:
    return f"card:{card_id}" if card_id is not None else f"bank:{bank_id}"


def transaction_hash(
    *,
    user_id: int,
    account: str,
    transaction_date: datetime,
    transaction_type: TransactionType,
    amount: Decimal,
    description: str | None,
    occurrence: int,
) -> str:
    """
    Стабильный хеш операции: user + счёт/карта + дата + направление +
    сумма + нормализованное описание + номер повтора в файле.

    Номер повтора различает честные одинаковые операции в одной
    выписке (два одинаковых кофе в одну минуту), при этом повторный
    импорт того же файла даёт те же хеши и не создаёт дублей.
    """

    parts = [
        str(user_id),
        account,
        transaction_date.isoformat(timespec="seconds"),
        transaction_type.value,
        format(quantize_money(amount), "f"),
        normalize_text(description).casefold(),
        str(occurrence),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def normalize_rows(
    rows: list[ParsedRow],
    *,
    user_id: int,
    bank_id: int,
    card_id: int | None,
    default_currency: str,
) -> list[NormalizedTransaction]:
    account = account_key(bank_id, card_id)
    seen: Counter[tuple] = Counter()
    result: list[NormalizedTransaction] = []

    for row in rows:
        amount = quantize_money(row.amount)
        description = normalize_text(row.description) or None
        key = (row.transaction_date, row.transaction_type, amount, (description or "").casefold())
        seen[key] += 1
        result.append(
            NormalizedTransaction(
                row_number=row.row_number,
                transaction_date=row.transaction_date,
                amount=amount,
                transaction_type=row.transaction_type,
                currency=row.currency or default_currency,
                description=description,
                merchant=normalize_merchant(description),
                operation=normalize_text(row.operation) or None,
                category_hint=normalize_text(row.category_hint) or None,
                external_hash=transaction_hash(
                    user_id=user_id,
                    account=account,
                    transaction_date=row.transaction_date,
                    transaction_type=row.transaction_type,
                    amount=amount,
                    description=description,
                    occurrence=seen[key],
                ),
            )
        )
    return result
