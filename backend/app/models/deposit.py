from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Deposit(Base, TimestampMixin):
    __tablename__ = "deposits"

    id: Mapped[int] = mapped_column(primary_key=True)

    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2)
    )

    interest_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2)
    )

    start_date: Mapped[date] = mapped_column(Date)

    end_date: Mapped[date] = mapped_column(Date)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id")
    )

    bank_id: Mapped[int] = mapped_column(
        ForeignKey("banks.id")
    )

    user = relationship(
        "User",
        back_populates="deposits"
    )

    bank = relationship(
        "Bank",
        back_populates="deposits"
    )