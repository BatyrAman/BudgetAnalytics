from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CHAR,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import TransactionType
from app.models.types import CurrencyCode, Money


class Transaction(Base, TimestampMixin):
    """A single money movement of one user.

    * ``amount`` is always > 0; direction comes from ``transaction_type``
      (see ``TransactionType``).
    * ``currency_code`` is the currency of ``amount``. No implicit conversion
      ever happens: totals are computed per currency.
    * ``transaction_date`` is timezone-aware and stored in UTC.
    * ``account_id`` (optional) must belong to the same user AND have the same
      currency — enforced by the composite foreign key
      ``(account_id, user_id, currency_code) -> accounts(id, user_id, currency_code)``.
    * ``bank_id`` is optional (cash has no bank).
    """

    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        ForeignKeyConstraint(
            ["account_id", "user_id", "currency_code"],
            ["accounts.id", "accounts.user_id", "accounts.currency_code"],
            name="fk_transactions_account_user_currency_accounts",
        ),
        Index("ix_transactions_user_id_transaction_date", "user_id", "transaction_date"),
        Index("ix_transactions_category_id", "category_id"),
        Index("ix_transactions_account_id", "account_id"),
        Index("ix_transactions_bank_id", "bank_id"),
        # Idempotent statement imports: one row per fingerprint per user.
        Index(
            "uq_transactions_user_id_import_hash",
            "user_id",
            "import_hash",
            unique=True,
            postgresql_where=text("import_hash IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    amount: Mapped[Decimal] = mapped_column(Money())

    currency_code: Mapped[str] = mapped_column(
        CurrencyCode(), ForeignKey("currencies.code"), default="KZT", server_default="KZT"
    )

    description: Mapped[str | None] = mapped_column(String(500), nullable=True)

    merchant: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Set only for imported rows: SHA-256 fingerprint used for deduplication.
    import_hash: Mapped[str | None] = mapped_column(CHAR(64), nullable=True)

    import_id: Mapped[int | None] = mapped_column(
        ForeignKey("statement_imports.id", ondelete="SET NULL"), nullable=True
    )

    # Native PostgreSQL ENUM storing member NAMES (unchanged from the initial schema).
    transaction_type: Mapped[TransactionType] = mapped_column(
        Enum(TransactionType, name="transactiontype")
    )

    transaction_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    account_id: Mapped[int | None] = mapped_column(nullable=True)

    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))

    bank_id: Mapped[int | None] = mapped_column(ForeignKey("banks.id"), nullable=True)

    user = relationship("User", back_populates="transactions", foreign_keys=[user_id])

    account = relationship(
        "Account",
        primaryjoin="and_(Transaction.account_id == Account.id, "
        "Transaction.user_id == Account.user_id, "
        "Transaction.currency_code == Account.currency_code)",
        foreign_keys=[account_id],
        viewonly=True,
    )

    category = relationship("Category", back_populates="transactions")

    bank = relationship("Bank", back_populates="transactions")

    currency = relationship("Currency")
