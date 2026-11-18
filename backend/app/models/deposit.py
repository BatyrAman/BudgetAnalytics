from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, Enum, ForeignKey, Index, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import Capitalization, enum_values
from app.models.types import CurrencyCode, Money, RatePercent


class Deposit(Base, TimestampMixin):
    """A term deposit.

    * ``interest_rate`` — NOMINAL annual rate in percent (e.g. 14.5).
    * ``effective_rate`` — the bank-published effective rate (ГЭСВ) in percent,
      stored as given. It is never derived from, nor used as, the nominal rate.
    * ``capitalization`` — ``none`` (simple interest; the behavior of all
      deposits created before this field existed) or a compounding frequency.
    """

    __tablename__ = "deposits"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint("interest_rate >= 0 AND interest_rate <= 100", name="interest_rate_range"),
        CheckConstraint(
            "effective_rate IS NULL OR (effective_rate >= 0 AND effective_rate <= 1000)",
            name="effective_rate_range",
        ),
        CheckConstraint("end_date > start_date", name="term_positive"),
        Index("ix_deposits_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    amount: Mapped[Decimal] = mapped_column(Money())

    currency_code: Mapped[str] = mapped_column(
        CurrencyCode(), ForeignKey("currencies.code"), default="KZT", server_default="KZT"
    )

    # NUMERIC(5, 2) kept from the initial schema so API output is unchanged.
    interest_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2))

    effective_rate: Mapped[Decimal | None] = mapped_column(RatePercent(), nullable=True)

    capitalization: Mapped[Capitalization] = mapped_column(
        Enum(
            Capitalization,
            name="capitalization",
            native_enum=False,
            create_constraint=True,
            length=20,
            values_callable=enum_values,
            validate_strings=True,
        ),
        default=Capitalization.NONE,
        server_default=Capitalization.NONE.value,
    )

    start_date: Mapped[date] = mapped_column(Date)

    end_date: Mapped[date] = mapped_column(Date)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    bank_id: Mapped[int] = mapped_column(ForeignKey("banks.id"))

    user = relationship("User", back_populates="deposits")
    bank = relationship("Bank", back_populates="deposits")
    currency = relationship("Currency")
