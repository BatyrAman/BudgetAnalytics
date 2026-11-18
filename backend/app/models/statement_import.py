"""Statement import history and preview rows.

The uploaded FILE is never stored — only its SHA-256, size and sanitized name.
Parsed rows are stored for the preview → commit flow (they become
transactions anyway); descriptions are stored with full card numbers and IINs
masked. Preview rows of imports that are not committed expire.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CHAR,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.types import Money


class StatementImport(Base, TimestampMixin):
    """``status``: preview | committed | failed | cancelled | expired."""

    __tablename__ = "statement_imports"
    __table_args__ = (Index("ix_statement_imports_user_id_created_at", "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    bank: Mapped[str] = mapped_column(String(32))
    parser_version: Mapped[str] = mapped_column(String(32))
    file_name: Mapped[str] = mapped_column(String(255))
    file_format: Mapped[str] = mapped_column(String(8))
    file_size: Mapped[int] = mapped_column(Integer)
    file_sha256: Mapped[str] = mapped_column(CHAR(64))
    status: Mapped[str] = mapped_column(String(16))
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    total_rows: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    valid_rows: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    invalid_rows: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    duplicate_rows: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    imported_rows: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Safe, user-readable reason (never a stack trace or raw file content).
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class StatementImportRow(Base):
    """``status``: valid | invalid | duplicate | possible_duplicate | imported | skipped.

    * duplicate — same fingerprint as an already imported transaction or an
      earlier row of this file beyond its own occurrence (never imported);
    * possible_duplicate — a manually entered transaction with the same day,
      amount, type and currency exists (imported only if the user includes it).
    """

    __tablename__ = "statement_import_rows"
    __table_args__ = (
        UniqueConstraint("import_id", "row_number", name="uq_statement_import_rows_import_row"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    import_id: Mapped[int] = mapped_column(ForeignKey("statement_imports.id", ondelete="CASCADE"))
    row_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24))
    transaction_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    amount: Mapped[Decimal | None] = mapped_column(Money(), nullable=True)
    currency_code: Mapped[str | None] = mapped_column(CHAR(3), nullable=True)
    transaction_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    type_source: Mapped[str | None] = mapped_column(String(16), nullable=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    merchant: Mapped[str | None] = mapped_column(String(200), nullable=True)
    category_hint: Mapped[str | None] = mapped_column(String(100), nullable=True)
    fingerprint: Mapped[str | None] = mapped_column(CHAR(64), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(300), nullable=True)
    transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
