from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import CategorySource, TransactionType
from app.models.types import MONEY, str_enum


class Transaction(Base, TimestampMixin):
    __tablename__ = "transactions"
    __table_args__ = (
        # Идемпотентный импорт: одна и та же операция из выписки
        # не может попасть к пользователю дважды. У ручных операций
        # external_hash = NULL, NULL'ы в unique не конфликтуют.
        UniqueConstraint("user_id", "external_hash", name="uq_transactions_user_external_hash"),
        # Графики и аналитика по периодам.
        Index("ix_transactions_user_date", "user_id", "transaction_date"),
        Index("ix_transactions_user_category", "user_id", "category_id"),
        Index("ix_transactions_user_card_date", "user_id", "card_id", "transaction_date"),
        Index("ix_transactions_user_merchant", "user_id", "merchant"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    amount: Mapped[Decimal] = mapped_column(MONEY)

    currency: Mapped[str] = mapped_column(String(3), default="KZT", server_default="KZT")

    description: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True
    )

    # Нормализованное название контрагента (магазин, сервис).
    merchant: Mapped[str | None] = mapped_column(String(255), nullable=True)

    transaction_type: Mapped[TransactionType] = mapped_column(
        Enum(TransactionType)
    )

    # Локальное время операции из выписки/ввода (без таймзоны).
    transaction_date: Mapped[datetime] = mapped_column(
        DateTime
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )

    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
    )

    category_source: Mapped[CategorySource | None] = mapped_column(
        str_enum(CategorySource, "category_source", 16),
        nullable=True,
    )

    bank_id: Mapped[int] = mapped_column(
        ForeignKey("banks.id")
    )

    card_id: Mapped[int | None] = mapped_column(
        ForeignKey("cards.id", ondelete="SET NULL"),
        nullable=True,
    )

    import_id: Mapped[int | None] = mapped_column(
        ForeignKey("statement_imports.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    external_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    is_recurring: Mapped[bool] = mapped_column(default=False, server_default="false")

    user = relationship(
        "User",
        back_populates="transactions"
    )

    category = relationship(
        "Category",
        back_populates="transactions"
    )

    bank = relationship(
        "Bank",
        back_populates="transactions"
    )

    card = relationship("Card")
