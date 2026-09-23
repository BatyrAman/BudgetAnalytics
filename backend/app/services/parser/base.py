"""
Парсеры банковских выписок.

Парсер — чистая функция `parse(content, filename) -> ParsedStatement`:
он не знает про БД, пользователя и категории. Ошибки отдельных строк
не прерывают разбор (partial failure), а собираются в errors.
Ошибка всего файла (кодировка, нет обязательных колонок) —
StatementParseError.
"""

from __future__ import annotations

import csv
import io
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import ClassVar

from app.models.enums import TransactionType

MAX_ROWS = 50_000


class StatementParseError(ValueError):
    """Файл целиком не может быть разобран."""


class RowParseError(ValueError):
    """Одна строка не может быть разобрана (сообщение без содержимого строки)."""


@dataclass(frozen=True, slots=True)
class ParsedRow:
    row_number: int
    transaction_date: datetime
    amount: Decimal  # всегда > 0; направление — в transaction_type
    transaction_type: TransactionType
    description: str | None
    category_hint: str | None = None
    operation: str | None = None
    currency: str | None = None


@dataclass(frozen=True, slots=True)
class RowError:
    row_number: int | None
    message: str


@dataclass(slots=True)
class ParsedStatement:
    bank_name: str
    rows: list[ParsedRow] = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)

    @property
    def rows_total(self) -> int:
        return len(self.rows) + len(self.errors)


class BaseStatementParser(ABC):
    slug: ClassVar[str]
    bank_name: ClassVar[str]
    extensions: ClassVar[tuple[str, ...]] = (".csv",)

    def supports(self, filename: str) -> bool:
        return filename.lower().endswith(self.extensions)

    @abstractmethod
    def parse(self, content: bytes, filename: str = "") -> ParsedStatement:
        raise NotImplementedError


_AMOUNT_JUNK = re.compile(r"[\s  ₸$€₽]|KZT|тг\.?", re.IGNORECASE)


def parse_amount(raw: str | None) -> Decimal:
    """
    Разбирает сумму из выписки: "- 1 500,00 ₸", "+10 000.50", "(250,00)",
    "1,234.56", "1.234,56". Знак определяет направление операции.
    """

    if raw is None or not raw.strip():
        raise RowParseError("amount is empty")
    text = raw.strip().replace("−", "-")
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative, text = True, text[1:-1]
    text = _AMOUNT_JUNK.sub("", text)
    if text.startswith("-"):
        negative, text = True, text[1:]
    elif text.startswith("+"):
        text = text[1:]

    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")

    if not re.fullmatch(r"\d+(\.\d+)?", text):
        raise RowParseError("amount is not a number")
    try:
        value = Decimal(text)
    except InvalidOperation as exc:  # pragma: no cover - regex guards it
        raise RowParseError("amount is not a number") from exc
    if value.as_tuple().exponent < -2:
        raise RowParseError("amount has more than 2 decimal places")
    return -value if negative else value


def parse_date(raw: str | None, formats: tuple[str, ...]) -> datetime:
    if raw is None or not raw.strip():
        raise RowParseError("date is empty")
    value = raw.strip()
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise RowParseError("unrecognized date format")


def decode(content: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1251"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise StatementParseError("Unsupported file encoding (expected UTF-8 or Windows-1251)")


class CsvStatementParser(BaseStatementParser):
    """
    Общий CSV-парсер. Банковские парсеры задают только различия:
    имя банка, алиасы колонок и форматы дат.

    Канонические колонки: date, amount (обязательные), description,
    category, operation, currency.
    """

    COLUMN_ALIASES: ClassVar[dict[str, tuple[str, ...]]] = {
        "date": ("date", "дата", "дата операции", "transaction date"),
        "amount": ("amount", "сумма", "сумма операции", "sum"),
        "description": ("description", "детали", "описание", "назначение", "details"),
        "category": ("category", "категория"),
        "operation": ("operation", "операция", "тип операции"),
        "currency": ("currency", "валюта"),
    }
    REQUIRED: ClassVar[frozenset[str]] = frozenset({"date", "amount"})
    DATE_FORMATS: ClassVar[tuple[str, ...]] = (
        "%Y-%m-%d",
        "%d.%m.%Y",
        "%d.%m.%y",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%d.%m.%Y %H:%M:%S",
        "%d.%m.%Y %H:%M",
    )

    def _column_map(self, headers: list[str]) -> dict[str, str]:
        normalized = {h.strip().lower(): h for h in headers if h}
        mapping: dict[str, str] = {}
        for canonical, aliases in self.COLUMN_ALIASES.items():
            for alias in aliases:
                if alias in normalized:
                    mapping[canonical] = normalized[alias]
                    break
        missing = self.REQUIRED - mapping.keys()
        if missing:
            raise StatementParseError(f"Missing required columns: {', '.join(sorted(missing))}")
        return mapping

    @staticmethod
    def _dialect(text: str) -> type[csv.Dialect] | csv.Dialect:
        sample = text[:4096]
        try:
            return csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            return csv.excel

    def parse(self, content: bytes, filename: str = "") -> ParsedStatement:
        text = decode(content)
        if not text.strip():
            return ParsedStatement(bank_name=self.bank_name)

        reader = csv.DictReader(io.StringIO(text, newline=""), dialect=self._dialect(text))
        columns = self._column_map(reader.fieldnames or [])
        statement = ParsedStatement(bank_name=self.bank_name)

        for index, row in enumerate(reader, start=2):  # строка 1 — заголовок
            if index - 1 > MAX_ROWS:
                raise StatementParseError(f"Statement has more than {MAX_ROWS} rows")
            if not any((value or "").strip() for value in row.values() if isinstance(value, str)):
                continue
            try:
                statement.rows.append(self._parse_row(index, row, columns))
            except RowParseError as exc:
                statement.errors.append(RowError(row_number=index, message=str(exc)))

        return statement

    def _parse_row(self, index: int, row: dict, columns: dict[str, str]) -> ParsedRow:
        def get(name: str) -> str | None:
            column = columns.get(name)
            value = row.get(column) if column else None
            value = value.strip() if isinstance(value, str) else None
            return value or None

        amount = parse_amount(get("amount"))
        if amount == 0:
            raise RowParseError("amount is zero")

        description = get("description")
        if description is not None:
            description = description[:500]

        category = get("category")
        return ParsedRow(
            row_number=index,
            transaction_date=parse_date(get("date"), self.DATE_FORMATS),
            amount=abs(amount),
            transaction_type=TransactionType.INCOME if amount > 0 else TransactionType.EXPENSE,
            description=description,
            category_hint=category[:100] if category else None,
            operation=get("operation"),
            currency=(get("currency") or "").upper()[:3] or None,
        )
