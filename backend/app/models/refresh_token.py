from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class RefreshToken(Base, TimestampMixin):
    """
    Выданные refresh-токены (серверное состояние для ротации и отзыва).

    Храним только jti (идентификатор) — сам токен без подписи
    бесполезен. family_id объединяет цепочку ротаций: повторное
    использование уже заменённого токена отзывает всю семью.
    """

    __tablename__ = "refresh_tokens"
    __table_args__ = (Index("ix_refresh_tokens_user_family", "user_id", "family_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    jti: Mapped[str] = mapped_column(String(64), unique=True)

    family_id: Mapped[str] = mapped_column(String(64))

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    replaced_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
