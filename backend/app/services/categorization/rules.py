"""
Словарь правил категоризации: ключевое слово → системная категория.

Порядок важен: срабатывает первое совпадение. Более специфичные
ключи стоят раньше общих («yandex go» до «yandex»).
"""

from __future__ import annotations

from app.models.enums import TransactionType

EXPENSE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Такси", ("yandex go", "yandex.taxi", "яндекс go", "яндекс такси", "uber", "indrive", "такси", "taxi")),
    ("Подписки", ("netflix", "spotify", "youtube", "apple.com", "icloud", "yandex plus", "яндекс плюс", "кинопоиск", "ivi.")),
    ("Продукты", ("magnum", "магнум", "small", "galmart", "anvar", "арзан", "супермаркет", "supermarket", "продукт")),
    ("Кафе и рестораны", ("starbucks", "kfc", "mcdonald", "burger", "coffee", "кофе", "cafe", "кафе", "ресторан", "restaurant", "doner", "донер")),
    ("Транспорт", ("onay", "метро", "автобус", "азс", "helios", "sinooil", "qazaq oil", "бензин", "парковка", "parking")),
    ("Связь и интернет", ("beeline", "билайн", "kcell", "activ", "tele2", "altel", "казахтелеком", "kazakhtelecom", "megaline")),
    ("Коммунальные услуги", ("алсеко", "alseco", "коммунал", "ерц", "энергосбыт", "водоканал", "kazakhgas", "qazaqgaz")),
    ("Здоровье", ("аптека", "apteka", "pharm", "клиника", "clinic", "медицин", "стоматолог")),
    ("Одежда", ("zara", "lc waikiki", "h&m", "одежд", "adidas", "nike")),
    ("Развлечения", ("kinopark", "chaplin", "кинотеатр", "cinema", "концерт", "steam")),
    ("Образование", ("udemy", "coursera", "курс", "университет", "school", "школа")),
    ("Погашение кредитов", ("погашение кредита", "погашение", "рассрочк", "кредит")),
    ("Переводы", ("перевод", "transfer")),
)

INCOME_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Зарплата", ("зарплат", "заработн", "salary", "payroll")),
    ("Кэшбэк", ("cashback", "кэшбэк", "кешбэк", "бонус")),
    ("Проценты по вкладам", ("вознагражден", "проценты по", "депозит")),
    ("Переводы", ("перевод", "пополнение", "transfer")),
)


def rules_for(transaction_type: TransactionType) -> tuple[tuple[str, tuple[str, ...]], ...]:
    return INCOME_RULES if transaction_type == TransactionType.INCOME else EXPENSE_RULES
