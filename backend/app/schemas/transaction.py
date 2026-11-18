from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import CurrencyCodeStr, Page, PatchModel, PositiveMoney, UtcDatetime

_DATE_DESCRIPTION = (
    "ISO 8601 date-time. A value without an offset is interpreted as UTC; "
    "responses are always in UTC."
)


class TransactionType(str, Enum):
    """``amount`` is always positive; the type gives the direction.
    income: +income · expense: +expenses · refund: −expenses (not income) ·
    transfer_in / transfer_out: between own accounts, excluded from income,
    expenses, cash flow and savings rate."""

    income = "income"
    expense = "expense"
    refund = "refund"
    transfer_in = "transfer_in"
    transfer_out = "transfer_out"


class TransactionCreate(BaseModel):
    amount: PositiveMoney
    description: str | None = Field(default=None, max_length=500)
    transaction_type: TransactionType
    transaction_date: UtcDatetime = Field(description=_DATE_DESCRIPTION)
    category_id: int
    bank_id: int | None = None
    account_id: int | None = Field(
        default=None, description="Own account; the transaction must be in its currency"
    )
    currency: CurrencyCodeStr | None = Field(
        default=None,
        description="Defaults to the account's currency, else the user's default currency",
    )


class TransactionUpdate(PatchModel):
    nullable = frozenset({"description", "bank_id", "account_id"})

    amount: PositiveMoney | None = None
    description: str | None = Field(default=None, max_length=500)
    transaction_type: TransactionType | None = None
    transaction_date: UtcDatetime | None = Field(default=None, description=_DATE_DESCRIPTION)
    category_id: int | None = None
    bank_id: int | None = None
    account_id: int | None = None
    currency: CurrencyCodeStr | None = None


class TransactionResponse(BaseModel):
    id: int
    user_id: int
    amount: Decimal
    currency_code: str
    description: str | None
    transaction_type: TransactionType
    transaction_date: datetime
    category_id: int
    bank_id: int | None
    account_id: int | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TransactionDetail(TransactionResponse):
    category_name: str
    bank_name: str


class TransactionListResponse(Page[TransactionResponse]):
    pass


# ---------------------------------------------------------------- legacy (deprecated endpoints)
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
