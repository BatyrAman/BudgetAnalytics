from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import CardType
from app.models.types import MONEY, str_enum


class Card(Base, TimestampMixin):
    """
    Карта пользователя.

    Храним только последние 4 цифры. PAN, CVV, срок действия и PIN
    не хранятся никогда (иначе проект попадает под PCI DSS).
    """

    __tablename__ = "cards"
    __table_args__ = (
        CheckConstraint("last4 ~ '^[0-9]{4}$'", name="last4_digits"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )

    bank_id: Mapped[int] = mapped_column(ForeignKey("banks.id"))

    last4: Mapped[str] = mapped_column(String(4))

    card_type: Mapped[CardType] = mapped_column(
        str_enum(CardType, "card_type", 16),
        default=CardType.DEBIT,
    )

    credit_limit: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)

    currency: Mapped[str] = mapped_column(String(3), default="KZT", server_default="KZT")

    nickname: Mapped[str | None] = mapped_column(String(100), nullable=True)

    is_active: Mapped[bool] = mapped_column(default=True, server_default="true")

    bank = relationship("Bank")
