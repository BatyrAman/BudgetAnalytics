from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.types import CurrencyCode, Money


class FinancialGoal(Base, TimestampMixin):
    """A savings goal. ``saved_amount`` is maintained by the user (it is not
    inferred from cash flow, which is not the same as money actually set aside)."""

    __tablename__ = "financial_goals"
    __table_args__ = (
        CheckConstraint("target_amount > 0", name="target_amount_positive"),
        CheckConstraint("saved_amount >= 0", name="saved_amount_non_negative"),
        CheckConstraint("length(btrim(name)) > 0", name="name_not_blank"),
        UniqueConstraint("user_id", "name", name="uq_financial_goals_user_id_name"),
        Index("ix_financial_goals_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    name: Mapped[str] = mapped_column(String(100))

    target_amount: Mapped[Decimal] = mapped_column(Money())

    saved_amount: Mapped[Decimal] = mapped_column(Money(), default=0, server_default="0")

    currency_code: Mapped[str] = mapped_column(CurrencyCode(), ForeignKey("currencies.code"))

    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    user = relationship("User", back_populates="goals")
    currency = relationship("Currency")
