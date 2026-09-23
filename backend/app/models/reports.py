from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MonthlyReport(Base):
    """Ежемесячный отчёт. UNIQUE(user_id, period_start) делает генерацию идемпотентной."""

    __tablename__ = "monthly_reports"
    __table_args__ = (UniqueConstraint("user_id", "period_start", name="uq_monthly_reports_user_period"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    period_start: Mapped[date] = mapped_column(Date)
    data: Mapped[dict] = mapped_column(JSONB)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PaymentReminder(Base):
    """
    Отправленное напоминание о платеже. UNIQUE(debt_id, due_date, kind):
    повторный запуск задачи не отправит напоминание второй раз.
    """

    __tablename__ = "payment_reminders"
    __table_args__ = (UniqueConstraint("debt_id", "due_date", "kind", name="uq_payment_reminders_once"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    debt_id: Mapped[int] = mapped_column(ForeignKey("debts.id", ondelete="CASCADE"))
    due_date: Mapped[date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(20))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
