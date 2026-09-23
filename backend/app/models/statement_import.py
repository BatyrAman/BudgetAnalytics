from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.enums import IMPORT_TRANSITIONS, ImportStatus
from app.models.types import str_enum


class InvalidImportTransition(RuntimeError):
    pass


class StatementImport(Base, TimestampMixin):
    """Журнал импорта выписок + state machine статусов."""

    __tablename__ = "statement_imports"
    __table_args__ = (
        Index("ix_statement_imports_user_created", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    bank_id: Mapped[int] = mapped_column(ForeignKey("banks.id"))

    card_id: Mapped[int | None] = mapped_column(
        ForeignKey("cards.id", ondelete="SET NULL"),
        nullable=True,
    )

    parser: Mapped[str] = mapped_column(String(32))

    file_name: Mapped[str] = mapped_column(String(255))

    file_sha256: Mapped[str] = mapped_column(String(64))

    status: Mapped[ImportStatus] = mapped_column(
        str_enum(ImportStatus, "import_status", 16),
        default=ImportStatus.PENDING,
    )

    rows_total: Mapped[int] = mapped_column(Integer, default=0)
    rows_imported: Mapped[int] = mapped_column(Integer, default=0)
    # Дубликаты уже импортированных операций.
    rows_skipped: Mapped[int] = mapped_column(Integer, default=0)
    rows_failed: Mapped[int] = mapped_column(Integer, default=0)

    # [{"row": 12, "message": "..."}] — без содержимого строки выписки.
    errors: Mapped[list] = mapped_column(JSONB, default=list)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def transition(self, new_status: ImportStatus) -> None:
        current = ImportStatus(self.status)
        if new_status not in IMPORT_TRANSITIONS[current]:
            raise InvalidImportTransition(f"{current.value} -> {new_status.value}")
        self.status = new_status
