from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.types import CurrencyCode


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)

    full_name: Mapped[str] = mapped_column(String(255))

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)

    hashed_password: Mapped[str] = mapped_column(String(255))

    is_active: Mapped[bool] = mapped_column(default=True)

    # Embedded in access tokens; incrementing it invalidates every access
    # token issued before (logout-all, password change).
    token_version: Mapped[int] = mapped_column(default=0, server_default="0")

    # Currency used when the user does not specify one (KZT for the first release).
    default_currency_code: Mapped[str] = mapped_column(
        CurrencyCode(), ForeignKey("currencies.code"), default="KZT", server_default="KZT"
    )

    # ORM-level cascades (unchanged behavior for the existing collections).
    transactions = relationship("Transaction", back_populates="user", cascade="all, delete")
    budgets = relationship("Budget", back_populates="user", cascade="all, delete")
    deposits = relationship("Deposit", back_populates="user", cascade="all, delete")
    accounts = relationship("Account", back_populates="user", cascade="all, delete")
    categories = relationship("Category", back_populates="user", cascade="all, delete")
    goals = relationship("FinancialGoal", back_populates="user", cascade="all, delete")
