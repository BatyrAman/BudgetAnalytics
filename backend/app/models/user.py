from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)

    full_name: Mapped[str] = mapped_column(String(255))

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True
    )

    hashed_password: Mapped[str] = mapped_column(String(255))

    is_active: Mapped[bool] = mapped_column(default=True)

    transactions = relationship(
        "Transaction",
        back_populates="user",
        cascade="all, delete"
    )

    budgets = relationship(
        "Budget",
        back_populates="user",
        cascade="all, delete"
    )

    deposits = relationship(
        "Deposit",
        back_populates="user",
        cascade="all, delete"
    )