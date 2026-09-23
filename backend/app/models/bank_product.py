from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import ProductType
from app.models.types import MONEY, RATE, str_enum


class BankProduct(Base, TimestampMixin):
    """
    Банковский продукт с условиями (кредит, ипотека, депозит...).

    Ставки живут только здесь — не в коде и не в промптах. У каждой
    записи обязательны source/source_url и fetched_at (когда данные
    проверены у источника). Обновляет таблицу фоновая задача
    update_bank_products, а не API-запрос.
    """

    __tablename__ = "bank_products"
    __table_args__ = (
        UniqueConstraint("bank_id", "product_type", "external_key", name="uq_bank_products_key"),
        CheckConstraint("rate_min >= 0 AND rate_max >= rate_min", name="rate_range"),
        CheckConstraint("term_min IS NULL OR term_max IS NULL OR term_max >= term_min", name="term_range"),
        CheckConstraint(
            "amount_min IS NULL OR amount_max IS NULL OR amount_max >= amount_min", name="amount_range"
        ),
        Index("ix_bank_products_type_active", "product_type", "is_active"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    bank_id: Mapped[int] = mapped_column(ForeignKey("banks.id"))
    product_type: Mapped[ProductType] = mapped_column(str_enum(ProductType, "product_type", 32))
    name: Mapped[str] = mapped_column(String(200))
    # Идентификатор продукта у источника — ключ идемпотентного upsert.
    external_key: Mapped[str] = mapped_column(String(100))

    rate_min: Mapped[Decimal] = mapped_column(RATE)
    rate_max: Mapped[Decimal] = mapped_column(RATE)
    gesv: Mapped[Decimal | None] = mapped_column(RATE, nullable=True)
    term_min: Mapped[int | None] = mapped_column(Integer, nullable=True)  # месяцы
    term_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    amount_min: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    amount_max: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="KZT", server_default="KZT")
    conditions: Mapped[dict] = mapped_column(JSONB, default=dict)

    source: Mapped[str] = mapped_column(String(100))
    source_url: Mapped[str] = mapped_column(String(500))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(default=True, server_default="true")

    bank = relationship("Bank")
