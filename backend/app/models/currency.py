from sqlalchemy import Boolean, CheckConstraint, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.types import SUPPORTED_MINOR_UNITS, CurrencyCode


class Currency(Base, TimestampMixin):
    """ISO 4217 reference data (global, not user-owned).

    ``minor_units`` is the number of decimal places used for amounts in this
    currency (KZT, USD, EUR, RUB: 2). It is the single source of currency
    precision for rounding in the finance engine. Only 2 is accepted in this
    release (see ``app.models.types``).
    """

    __tablename__ = "currencies"
    __table_args__ = (
        CheckConstraint("code ~ '^[A-Z]{3}$'", name="code_iso4217"),
        CheckConstraint(f"minor_units = {SUPPORTED_MINOR_UNITS}", name="minor_units_supported"),
    )

    code: Mapped[str] = mapped_column(CurrencyCode(), primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    symbol: Mapped[str | None] = mapped_column(String(8), nullable=True)
    minor_units: Mapped[int] = mapped_column(SmallInteger)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
