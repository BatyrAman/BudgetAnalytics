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


class CategoryKind(str, enum.Enum):
    INCOME = "income"
    EXPENSE = "expense"


class CategorySource(str, enum.Enum):
    """Откуда у операции категория — основа «памяти» категоризации."""

    USER = "user"            # пользователь выбрал/исправил вручную
    MEMORY = "memory"        # перенесено с прошлой ручной правки
    RULE = "rule"            # словарь правил по ключевым словам
    STATEMENT = "statement"  # категория из самой выписки
    DEFAULT = "default"      # не удалось определить


class CardType(str, enum.Enum):
    DEBIT = "debit"
    CREDIT = "credit"


class ImportStatus(str, enum.Enum):
    """
    Состояния импорта выписки:

        PENDING → PROCESSING → COMPLETED | PARTIAL | FAILED

    COMPLETED/PARTIAL/FAILED — терминальные.
    """

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"

    @property
    def is_terminal(self) -> bool:
        return self in _TERMINAL


_TERMINAL = {ImportStatus.COMPLETED, ImportStatus.PARTIAL, ImportStatus.FAILED}

IMPORT_TRANSITIONS: dict[ImportStatus, set[ImportStatus]] = {
    ImportStatus.PENDING: {ImportStatus.PROCESSING, ImportStatus.FAILED},
    ImportStatus.PROCESSING: {ImportStatus.COMPLETED, ImportStatus.PARTIAL, ImportStatus.FAILED},
    ImportStatus.COMPLETED: set(),
    ImportStatus.PARTIAL: set(),
    ImportStatus.FAILED: set(),
}
