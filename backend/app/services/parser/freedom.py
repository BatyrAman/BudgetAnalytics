from __future__ import annotations

from app.services.parser.base import CsvStatementParser


class FreedomParser(CsvStatementParser):
    """Выписка Freedom Bank (CSV-экспорт)."""

    slug = "freedom"
    bank_name = "Freedom Bank"
