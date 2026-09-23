from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Bank(Base):
    """Справочник банков — общий для всех пользователей (не персональные данные)."""

    __tablename__ = "banks"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(
        String(100),
        unique=True
    )

    logo: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True
    )

    transactions = relationship(
        "Transaction",
        back_populates="bank"
    )

    deposits = relationship(
        "Deposit",
        back_populates="bank"
    )
