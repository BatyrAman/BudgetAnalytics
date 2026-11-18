"""One parser per bank on a shared, profile-driven base.

``BankStatementParser.parse`` turns a validated file into normalized rows and
per-row errors. Structural problems (no header, missing required columns, too
many rows) raise ``FileRejected``; problems of single rows never fail the whole
file — they are reported per row in the preview.
"""

import asyncio
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from app.services.imports.files import FileRejected, UploadedFile, read_csv, read_xlsx
from app.services.imports.normalize import (
    InvalidRow,
    NormalizedRow,
    RowError,
    classify,
    clean_text,
    detect_currency,
    extract_merchant,
    parse_amount,
    parse_date,
)
from app.services.imports.profiles import PROFILES, BankProfile

HEADER_SEARCH_ROWS = 30


@dataclass
class ParseResult:
    rows: list[NormalizedRow] = field(default_factory=list)
    errors: list[InvalidRow] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.rows) + len(self.errors)


def _norm(cell: Any) -> str:
    return re.sub(r"\s+", " ", str(cell or "")).strip().lower().rstrip(":")


class BankStatementParser:
    profile: BankProfile

    def find_header(self, table: list[list[Any]]) -> tuple[int, dict[str, int]]:
        for index, row in enumerate(table[:HEADER_SEARCH_ROWS]):
            labels = [_norm(c) for c in row]
            mapping: dict[str, int] = {}
            for field_name, aliases in self.profile.columns.items():
                for position, label in enumerate(labels):
                    if label in aliases and position not in mapping.values():
                        mapping[field_name] = position
                        break
            if "date" in mapping and ("amount" in mapping or {"credit", "debit"} <= mapping.keys()):
                return index, mapping
        raise FileRejected(
            "missing_columns",
            "Required columns were not found: a date column and an amount column "
            "(or separate credit and debit columns)",
        )

    def signed_amount(self, cells: dict[str, Any]) -> tuple[Decimal, str | None]:
        if "amount" in cells and cells["amount"] not in (None, ""):
            return parse_amount(cells["amount"])
        credit, debit = cells.get("credit"), cells.get("debit")
        has_credit = credit not in (None, "")
        has_debit = debit not in (None, "")
        if has_credit == has_debit:
            raise RowError("invalid_amount", "exactly one of credit or debit must be filled")
        value, currency = parse_amount(credit if has_credit else debit)
        return (abs(value) if has_credit else -abs(value)), currency

    def normalize(self, row_number: int, cells: dict[str, Any], today: date) -> NormalizedRow:
        signed, currency_in_amount = self.signed_amount(cells)
        when = parse_date(
            cells.get("date"), self.profile.date_formats, self.profile.timezone, today
        )
        currency_cell = clean_text(cells.get("currency"), 20)
        if currency_cell is None:
            currency = currency_in_amount or self.profile.default_currency
        elif re.fullmatch(r"[A-Za-z]{3}", currency_cell):
            currency = currency_cell.upper()
        else:
            detected = detect_currency(currency_cell)
            if detected is None:
                raise RowError("invalid_currency", "currency is not recognized")
            currency = detected
        if currency_in_amount and currency_in_amount != currency:
            raise RowError("invalid_currency", "currency column and amount disagree")
        operation = clean_text(cells.get("operation"), 100)
        description = clean_text(cells.get("description"), 500) or operation
        kind, source = classify(signed, operation, description)
        merchant = clean_text(cells.get("merchant"), 200)
        if merchant is None and kind.value in ("expense", "refund"):
            merchant = extract_merchant(description, operation)
        return NormalizedRow(
            row_number=row_number,
            transaction_date=when,
            amount=abs(signed),
            currency_code=currency,
            transaction_type=kind,
            type_source=source,
            description=description,
            merchant=merchant,
            category_hint=clean_text(cells.get("category"), 100),
        )

    async def parse(self, file: UploadedFile, max_rows: int, today: date) -> ParseResult:
        reader = read_xlsx if file.format == "xlsx" else read_csv
        table = await asyncio.to_thread(reader, file.content, max_rows)
        header_index, mapping = self.find_header(table)
        result = ParseResult()
        for offset, row in enumerate(table[header_index + 1 :], start=header_index + 2):
            if not any(c not in (None, "") and str(c).strip() for c in row):
                continue  # empty line
            first = _norm(row[0]) if row else ""
            if any(first.startswith(marker) for marker in self.profile.summary_markers):
                continue  # totals/balance lines below the table
            cells = {f: row[i] if i < len(row) else None for f, i in mapping.items()}
            try:
                result.rows.append(self.normalize(offset, cells, today))
            except RowError as exc:
                result.errors.append(InvalidRow(offset, exc.code, exc.message))
            if result.total > max_rows:
                raise FileRejected("too_many_rows", f"The statement has more than {max_rows} rows")
        if result.total == 0:
            raise FileRejected("no_transactions", "No transactions were found in the file")
        return result


class KaspiParser(BankStatementParser):
    profile = PROFILES["kaspi"]


class HalykParser(BankStatementParser):
    profile = PROFILES["halyk"]


class FreedomParser(BankStatementParser):
    profile = PROFILES["freedom"]


PARSERS: dict[str, type[BankStatementParser]] = {
    "kaspi": KaspiParser,
    "halyk": HalykParser,
    "freedom": FreedomParser,
}


def get_parser(bank: str) -> BankStatementParser:
    parser_cls = PARSERS.get(bank.lower())
    if parser_cls is None:
        raise FileRejected(
            "unsupported_bank", f"Unsupported bank. Supported: {', '.join(PARSERS)}", 400
        )
    return parser_cls()
