from __future__ import annotations

import csv
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from app.models.enums import TransactionType
from app.schemas.transaction import ImportTransaction


class KaspiParser:
    """
    Парсер CSV-выписок Kaspi Bank.
    """

    BANK_NAME = "Kaspi Bank"

    REQUIRED_COLUMNS = {
        "date",
        "category",
        "description",
        "amount",
    }

    DATE_FORMATS = (
        "%Y-%m-%d",
        "%d.%m.%Y",
        "%Y-%m-%d %H:%M:%S",
        "%d.%m.%Y %H:%M:%S",
    )

    @staticmethod
    def validate_columns(headers: list[str]) -> None:
        headers = {header.strip().lower() for header in headers}

        missing = KaspiParser.REQUIRED_COLUMNS - headers

        if missing:
            raise ValueError(
                f"Missing required columns: {', '.join(missing)}"
            )

    @classmethod
    def _parse_date(cls, raw_date: str) -> datetime:
        raw_date = raw_date.strip()

        for fmt in cls.DATE_FORMATS:
            try:
                return datetime.strptime(raw_date, fmt)
            except ValueError:
                continue

        raise ValueError(f"Unrecognized date format: {raw_date!r}")

    async def parse(
        self,
        file_path: str | Path,
    ) -> list[ImportTransaction]:

        file_path = Path(file_path)

        transactions: list[ImportTransaction] = []

        with open(
            file_path,
            encoding="utf-8-sig",
            newline=""
        ) as csvfile:

            reader = csv.DictReader(csvfile)

            self.validate_columns(reader.fieldnames or [])

            for row in reader:

                amount = Decimal(
                    row["amount"].strip().replace(" ", "").replace(",", ".")
                )

                transaction = ImportTransaction(
                    amount=abs(amount),
                    description=row.get("description") or None,
                    transaction_type=(
                        TransactionType.INCOME
                        if amount > 0
                        else TransactionType.EXPENSE
                    ),
                    transaction_date=self._parse_date(row["date"]),
                    category_name=(row.get("category") or "Без категории").strip(),
                    bank_name=self.BANK_NAME,
                )

                transactions.append(transaction)

        return transactions
