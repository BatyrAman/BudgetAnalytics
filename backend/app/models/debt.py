from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import DebtPaymentStatus, DebtScheduleType
from app.models.types import MONEY, RATE, str_enum
from app.services.finance.debt_strategy import DebtType


class Debt(Base, TimestampMixin):
    """
    Долг пользователя: кредит, рассрочка, кредитная карта, ипотека,
    автокредит, МФО, личный долг.

    balance — текущий остаток основного долга. monthly_payment —
    обязательный (минимальный) ежемесячный платёж.
    """

    __tablename__ = "debts"
    __table_args__ = (
        CheckConstraint("principal > 0", name="principal_positive"),
        CheckConstraint("balance >= 0", name="balance_non_negative"),
        CheckConstraint("annual_rate >= 0", name="rate_non_negative"),
        CheckConstraint("monthly_payment >= 0", name="payment_non_negative"),
        CheckConstraint("payment_day BETWEEN 1 AND 31", name="payment_day_range"),
        Index("ix_debts_user_active", "user_id", "is_active"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    bank_id: Mapped[int | None] = mapped_column(ForeignKey("banks.id"), nullable=True)

    name: Mapped[str] = mapped_column(String(100))

    debt_type: Mapped[DebtType] = mapped_column(str_enum(DebtType, "debt_type", 32))

    principal: Mapped[Decimal] = mapped_column(MONEY)

    balance: Mapped[Decimal] = mapped_column(MONEY)

    annual_rate: Mapped[Decimal] = mapped_column(RATE)

    # ГЭСВ из договора (справочно; расчёты идут по annual_rate).
    gesv: Mapped[Decimal | None] = mapped_column(RATE, nullable=True)

    monthly_payment: Mapped[Decimal] = mapped_column(MONEY)

    payment_day: Mapped[int] = mapped_column(Integer)

    start_date: Mapped[date] = mapped_column(Date)

    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    schedule_type: Mapped[DebtScheduleType] = mapped_column(
        str_enum(DebtScheduleType, "debt_schedule_type", 16),
        default=DebtScheduleType.ANNUITY,
    )

    currency: Mapped[str] = mapped_column(String(3), default="KZT", server_default="KZT")

    is_active: Mapped[bool] = mapped_column(default=True, server_default="true")

    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    bank = relationship("Bank")
    payments = relationship(
        "DebtPayment",
        back_populates="debt",
        passive_deletes=True,
        order_by="DebtPayment.due_date",
    )


class DebtPayment(Base, TimestampMixin):
    """
    Платёж по долгу (фактически внесённый).

    user_id денормализован для изоляции: любые выборки платежей
    фильтруются по владельцу без JOIN на debts.
    """

    __tablename__ = "debt_payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint("principal_part >= 0 AND interest_part >= 0", name="parts_non_negative"),
        # Одна банковская операция не может погасить два платежа.
        UniqueConstraint("transaction_id", name="uq_debt_payments_transaction_id"),
        Index("ix_debt_payments_debt_due", "debt_id", "due_date"),
        Index("ix_debt_payments_user_paid", "user_id", "paid_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    debt_id: Mapped[int] = mapped_column(ForeignKey("debts.id", ondelete="CASCADE"))

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    due_date: Mapped[date] = mapped_column(Date)

    amount: Mapped[Decimal] = mapped_column(MONEY)

    principal_part: Mapped[Decimal] = mapped_column(MONEY)

    interest_part: Mapped[Decimal] = mapped_column(MONEY)

    paid_at: Mapped[date] = mapped_column(Date)

    status: Mapped[DebtPaymentStatus] = mapped_column(
        str_enum(DebtPaymentStatus, "debt_payment_status", 16),
        default=DebtPaymentStatus.PAID,
    )

    transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="SET NULL"),
        nullable=True,
    )

    debt = relationship("Debt", back_populates="payments")
