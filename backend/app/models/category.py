from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(
        String(100),
        unique=True
    )

    color: Mapped[str] = mapped_column(
        String(30),
        default="#3B82F6"
    )

    icon: Mapped[str] = mapped_column(
        String(50),
        default="wallet"
    )

    transactions = relationship(
        "Transaction",
        back_populates="category"
    )