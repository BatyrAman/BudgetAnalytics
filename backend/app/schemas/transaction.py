from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import CategorySource, TransactionType
from app.schemas.common import MoneyDecimal, PositiveMoney

__all__ = ["TransactionType"]


class TransactionBase(BaseModel):
    amount: PositiveMoney = Field(description="Transaction amount (always positive)")

    description: str | None = Field(
        default=None,
        max_length=500
    )

    transaction_type: TransactionType

    transaction_date: datetime

    category_id: int

    bank_id: int


class TransactionCreate(TransactionBase):
    card_id: int | None = None
    merchant: str | None = Field(default=None, max_length=255)
    is_recurring: bool = False


class TransactionUpdate(BaseModel):
    amount: PositiveMoney | None = None

    description: str | None = Field(
        default=None,
        max_length=500
    )

    transaction_type: TransactionType | None = None

    transaction_date: datetime | None = None

    category_id: int | None = None

    bank_id: int | None = None

    card_id: int | None = None

    merchant: str | None = Field(default=None, max_length=255)

    is_recurring: bool | None = None


class TransactionResponse(BaseModel):
    id: int
    amount: MoneyDecimal
    currency: str
    description: str | None
    merchant: str | None
    transaction_type: TransactionType
    transaction_date: datetime
    category_id: int | None
    category_source: CategorySource | None
    bank_id: int
    card_id: int | None
    is_recurring: bool
    user_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True
    )


class TransactionDetail(TransactionResponse):
    category_name: str

    bank_name: str


class TransactionListResponse(BaseModel):
    items: list[TransactionResponse]

    total: int


class MonthlyTransactionSummary(BaseModel):
    income: MoneyDecimal

    expense: MoneyDecimal

    balance: MoneyDecimal


class TransactionStatistics(BaseModel):
    total_transactions: int

    total_income: MoneyDecimal

    total_expense: MoneyDecimal

    current_balance: MoneyDecimal

    average_expense: MoneyDecimal

    average_income: MoneyDecimal


class TransactionChartItem(BaseModel):
    label: str

    income: MoneyDecimal

    expense: MoneyDecimal
