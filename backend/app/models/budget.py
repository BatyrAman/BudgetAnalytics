from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.types import CurrencyCode, Money


class Budget(Base, TimestampMixin):
    """Monthly spending limit, optionally for one category.

    ``spent`` is the legacy, manually maintained value used by the existing
    API. Actual utilization is computed from transactions by
    ``services.finance.budget`` (category + month + currency) and does not
    rely on this column.
    """

    __tablename__ = "budgets"
    __table_args__ = (
        CheckConstraint("monthly_limit > 0", name="monthly_limit_positive"),
        CheckConstraint("spent >= 0", name="spent_non_negative"),
        Index("ix_budgets_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    title: Mapped[str] = mapped_column(String(100))

    monthly_limit: Mapped[Decimal] = mapped_column(Money())

    spent: Mapped[Decimal] = mapped_column(Money(), default=0)

    currency_code: Mapped[str] = mapped_column(
        CurrencyCode(), ForeignKey("currencies.code"), default="KZT", server_default="KZT"
    )

    # Must be a category visible to the owner (system or own) — enforced by
    # CategoryRepository/API, since system categories have no owner.
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), nullable=True)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    user = relationship("User", back_populates="budgets")
    category = relationship("Category", back_populates="budgets")
    currency = relationship("Currency")
