from decimal import Decimal

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.types import MONEY


class Budget(Base, TimestampMixin):
    """
    Месячный бюджет.

    Если задан category_id — потраченное считается запросом по
    расходам категории за текущий календарный месяц. Колонка spent
    остаётся для бюджетов без категории (ручной учёт, как раньше).
    """

    __tablename__ = "budgets"

    id: Mapped[int] = mapped_column(primary_key=True)

    title: Mapped[str] = mapped_column(
        String(100)
    )

    monthly_limit: Mapped[Decimal] = mapped_column(MONEY)

    spent: Mapped[Decimal] = mapped_column(
        MONEY,
        default=0
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )

    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
    )

    user = relationship(
        "User",
        back_populates="budgets"
    )

    category = relationship("Category")
