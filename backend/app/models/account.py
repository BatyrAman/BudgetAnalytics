from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import AccountType, enum_values
from app.models.types import CurrencyCode, Money


class Account(Base, TimestampMixin):
    """A user's account, card or cash wallet — METADATA ONLY.

    Never store a full card/account number, CVV, PIN or bank credentials.
    ``last4`` (optional) is the only part of a number that may be kept.

    BALANCE: the user states ``opening_balance`` as of ``opening_balance_at``.
    The current balance is computed (never stored) as

        opening_balance + Σ(income + refund + transfer_in)
                        − Σ(expense + transfer_out)

    over transactions LINKED to this account with
    ``transaction_date >= opening_balance_at``. Earlier transactions are
    assumed to be already reflected in the opening balance. Income minus
    expenses over unlinked transactions is never presented as a balance.
    """

    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_accounts_user_id_name"),
        # Target of the composite FK from transactions: guarantees that a
        # transaction can only reference an account of the same user.
        UniqueConstraint("id", "user_id", name="uq_accounts_id_user_id"),
        # Target of the 3-column FK from transactions: a linked transaction must
        # be in the account's currency (so balances never mix currencies).
        UniqueConstraint(
            "id", "user_id", "currency_code", name="uq_accounts_id_user_id_currency_code"
        ),
        CheckConstraint("last4 IS NULL OR last4 ~ '^[0-9]{4}$'", name="last4_digits"),
        CheckConstraint("length(btrim(name)) > 0", name="name_not_blank"),
        Index("ix_accounts_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    bank_id: Mapped[int | None] = mapped_column(ForeignKey("banks.id"), nullable=True)

    name: Mapped[str] = mapped_column(String(100))

    account_type: Mapped[AccountType] = mapped_column(
        Enum(
            AccountType,
            name="account_type",
            native_enum=False,
            create_constraint=True,
            length=20,
            values_callable=enum_values,
            validate_strings=True,
        )
    )

    currency_code: Mapped[str] = mapped_column(CurrencyCode(), ForeignKey("currencies.code"))

    last4: Mapped[str | None] = mapped_column(String(4), nullable=True)

    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    opening_balance: Mapped[Decimal] = mapped_column(Money(), default=0, server_default="0")

    opening_balance_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user = relationship("User", back_populates="accounts")
    bank = relationship("Bank", back_populates="accounts")
    currency = relationship("Currency")
