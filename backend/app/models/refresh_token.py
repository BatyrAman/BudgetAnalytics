from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class RefreshToken(Base):
    """Server-side record of an issued refresh token (the token itself is a
    JWT; only its ``jti`` is stored, never the token string).

    * Rotation: every refresh revokes the presented token and issues a new one
      in the same ``family_id``.
    * Reuse detection: presenting an already revoked token revokes the whole
      family (the token was probably stolen).
    * Logout revokes the family; logout-all and password change revoke every
      token of the user.
    """

    __tablename__ = "refresh_tokens"
    __table_args__ = (
        Index("ix_refresh_tokens_user_id", "user_id"),
        Index("ix_refresh_tokens_family_id", "family_id"),
    )

    jti: Mapped[str] = mapped_column(String(36), primary_key=True)
    family_id: Mapped[str] = mapped_column(String(36))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
