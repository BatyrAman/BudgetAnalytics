from sqlalchemy import Enum, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import CategoryKind, enum_values


class Category(Base, TimestampMixin):
    """Transaction category.

    * ``user_id IS NULL`` — system category, visible to every user, read-only.
    * ``user_id = <id>``  — private category of that user, visible only to them.

    Names are unique per owner (and unique among system categories). The API
    additionally refuses a private name that equals a system name, so the set
    of names visible to one user is unambiguous.

    ``kind`` (income | expense | any) restricts which transaction types may use
    the category; see ``CategoryKind``.
    """

    __tablename__ = "categories"
    __table_args__ = (
        Index(
            "uq_categories_user_id_name",
            "user_id",
            "name",
            unique=True,
            postgresql_where=text("user_id IS NOT NULL"),
        ),
        Index(
            "uq_categories_system_name",
            "name",
            unique=True,
            postgresql_where=text("user_id IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    name: Mapped[str] = mapped_column(String(100))

    color: Mapped[str] = mapped_column(String(30), default="#3B82F6")

    icon: Mapped[str] = mapped_column(String(50), default="wallet")

    kind: Mapped[CategoryKind] = mapped_column(
        Enum(
            CategoryKind,
            name="category_kind",
            native_enum=False,
            create_constraint=True,
            length=16,
            values_callable=enum_values,
            validate_strings=True,
        ),
        default=CategoryKind.ANY,
        server_default=CategoryKind.ANY.value,
    )

    user = relationship("User", back_populates="categories")
    transactions = relationship("Transaction", back_populates="category")
    budgets = relationship("Budget", back_populates="category")
