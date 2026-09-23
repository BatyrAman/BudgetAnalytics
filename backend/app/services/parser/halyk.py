from __future__ import annotations

from app.services.parser.base import CsvStatementParser


class HalykParser(CsvStatementParser):
    """Выписка Halyk Bank (CSV-экспорт)."""

    slug = "halyk"
    bank_name = "Halyk Bank"
    COLUMN_ALIASES = {
        **CsvStatementParser.COLUMN_ALIASES,
        "amount": CsvStatementParser.COLUMN_ALIASES["amount"] + ("сумма в валюте счета",),
        "date": CsvStatementParser.COLUMN_ALIASES["date"] + ("дата проведения",),
    }
