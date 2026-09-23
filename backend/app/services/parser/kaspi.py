from __future__ import annotations

from app.services.parser.base import CsvStatementParser


class KaspiParser(CsvStatementParser):
    """
    Выписка Kaspi Bank (CSV-экспорт).

    Помимо канонических колонок понимает русские заголовки выписки
    Kaspi Gold: «Дата», «Сумма», «Операция», «Детали».
    PDF-выписки пока не поддерживаются — нужен набор реальных образцов.
    """

    slug = "kaspi"
    bank_name = "Kaspi Bank"
