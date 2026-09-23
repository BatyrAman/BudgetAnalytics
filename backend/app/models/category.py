from sqlalchemy import ForeignKey, Index, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import CategoryKind
from app.models.types import str_enum


class Category(Base):
    """
    Категория операций.

    user_id IS NULL  → системная (видна всем, изменять нельзя);
    user_id = X      → пользовательская (видна только X).

    Имя уникально (без учёта регистра) в пределах владельца и типа.
    """

    __tablename__ = "categories"
    __table_args__ = (
        Index(
            "uq_categories_system_name_kind",
            func.lower(text("name")),
            "kind",
            unique=True,
            postgresql_where=text("user_id IS NULL"),
        ),
        Index(
            "uq_categories_user_name_kind",
            "user_id",
            func.lower(text("name")),
            "kind",
            unique=True,
            postgresql_where=text("user_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(100))

    kind: Mapped[CategoryKind] = mapped_column(
        str_enum(CategoryKind, "category_kind", 16),
        default=CategoryKind.EXPENSE,
        server_default=CategoryKind.EXPENSE.value,
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

    @property
    def is_system(self) -> bool:
        return self.user_id is None
