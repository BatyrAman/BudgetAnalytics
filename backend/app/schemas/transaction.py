from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class TransactionType(str, Enum):
    income = "income"
    expense = "expense"


class TransactionBase(BaseModel):
    amount: Decimal = Field(
        ...,
        gt=0,
        decimal_places=2,
        description="Transaction amount"
    )

    description: str | None = Field(
        default=None,
        max_length=500
    )

    transaction_type: TransactionType

    transaction_date: datetime

    category_id: int

    bank_id: int


class TransactionCreate(TransactionBase):
    pass


class TransactionUpdate(BaseModel):
    amount: Decimal | None = Field(
        default=None,
        gt=0,
        decimal_places=2
    )

    description: str | None = Field(
        default=None,
        max_length=500
    )

    transaction_type: TransactionType | None = None

    transaction_date: datetime | None = None

    category_id: int | None = None

    bank_id: int | None = None


class TransactionResponse(TransactionBase):
    id: int

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


class TransactionFilter(BaseModel):
    start_date: datetime | None = None

    end_date: datetime | None = None

    category_id: int | None = None

    bank_id: int | None = None

    transaction_type: TransactionType | None = None

    min_amount: Decimal | None = None

    max_amount: Decimal | None = None


class MonthlyTransactionSummary(BaseModel):
    income: Decimal

    expense: Decimal

    balance: Decimal


class TransactionStatistics(BaseModel):
    total_transactions: int

    total_income: Decimal

    total_expense: Decimal

    current_balance: Decimal

    average_expense: Decimal

    average_income: Decimal


class TransactionChartItem(BaseModel):
    label: str

    income: Decimal

    expense: Decimal


class ImportTransaction(BaseModel):
    amount: Decimal

    description: str | None = None

    transaction_type: TransactionType

    transaction_date: datetime

    category_name: str | None = None

    bank_name: str | None = None