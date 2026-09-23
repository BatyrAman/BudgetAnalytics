import enum


class TransactionType(str, enum.Enum):
    """
    Единый enum типа транзакции.

    Используется моделью Transaction, сервисами аналитики
    (app/services/analytics/*) и банковскими парсерами
    (app/services/parser/*), поэтому вынесен в отдельный модуль,
    чтобы избежать дублирования и рассинхронизации.
    """

    INCOME = "income"
    EXPENSE = "expense"
