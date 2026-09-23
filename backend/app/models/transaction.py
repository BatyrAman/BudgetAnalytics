from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import TransactionType


class Transaction(Base, TimestampMixin):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)

    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2)
    )

    description: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True
    )

    transaction_type: Mapped[TransactionType] = mapped_column(
        Enum(TransactionType)
    )

    transaction_date: Mapped[datetime] = mapped_column(
        DateTime
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id")
    )

    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id")
    )

    bank_id: Mapped[int] = mapped_column(
        ForeignKey("banks.id")
    )

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