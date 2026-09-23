from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Index, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.types import MONEY


class User(Base, TimestampMixin):
    __tablename__ = "users"
    # Логин без учёта регистра email.
    __table_args__ = (Index("ix_users_email_lower", func.lower(text("email"))),)

    id: Mapped[int] = mapped_column(primary_key=True)

    full_name: Mapped[str] = mapped_column(String(255))

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True
    )

    hashed_password: Mapped[str] = mapped_column(String(255))

    is_active: Mapped[bool] = mapped_column(default=True)

    # Увеличивается при смене пароля / выходе со всех устройств:
    # access-токены с прежней версией перестают приниматься сразу.
    token_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    # --- финансовый профиль (для расчётов, не для LLM напрямую) ---
    monthly_income_declared: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    dependents: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Каскад удаления обеспечивают FK ON DELETE CASCADE в БД.
    transactions = relationship("Transaction", back_populates="user", passive_deletes=True)
    budgets = relationship("Budget", back_populates="user", passive_deletes=True)
    deposits = relationship("Deposit", back_populates="user", passive_deletes=True)
