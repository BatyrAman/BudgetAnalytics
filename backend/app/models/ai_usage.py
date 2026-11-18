from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AIUsage(Base):
    """One AI request (or a refused/fallback attempt) — METADATA ONLY.

    Never stores prompts, answers, questions or financial figures; only what is
    needed for cost accounting, limits and operations.
    ``outcome``: success | fallback_invalid | fallback_error | limited | disabled.
    """

    __tablename__ = "ai_usage"
    __table_args__ = (Index("ix_ai_usage_user_id_created_at", "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    feature: Mapped[str] = mapped_column(String(32))
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(32))
    outcome: Mapped[str] = mapped_column(String(32))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # USD; None when prices are not configured.
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(14, 6), nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
