from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AccountType
from app.schemas.common import CurrencyCodeStr, Name100, PatchModel, SignedMoney, UtcDatetime

_LAST4 = Field(
    default=None, pattern=r"^[0-9]{4}$", description="Last 4 digits only — never a full number"
)


class AccountCreate(BaseModel):
    name: Name100
    account_type: AccountType
    currency: CurrencyCodeStr | None = Field(
        default=None, description="Defaults to the user's default currency; cannot be changed later"
    )
    bank_id: int | None = None
    last4: str | None = _LAST4
    opening_balance: SignedMoney = Field(
        default=Decimal("0"), description="Balance at opening_balance_at (negative for debt)"
    )
    opening_balance_at: UtcDatetime | None = Field(
        default=None, description="Defaults to now. Earlier linked transactions are not counted."
    )


class AccountUpdate(PatchModel):
    nullable = frozenset({"bank_id", "last4"})

    name: Name100 | None = None
    account_type: AccountType | None = None
    bank_id: int | None = None
    last4: str | None = _LAST4
    is_archived: bool | None = None
    opening_balance: SignedMoney | None = None
    opening_balance_at: UtcDatetime | None = None


class AccountResponse(BaseModel):
    id: int
    name: str
    account_type: AccountType
    currency_code: str
    bank_id: int | None
    last4: str | None
    is_archived: bool
    opening_balance: Decimal
    opening_balance_at: datetime
    balance: Decimal = Field(
        description="opening_balance + linked inflows − linked outflows since opening_balance_at"
    )
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
