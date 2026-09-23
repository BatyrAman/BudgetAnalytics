from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import CardType
from app.schemas.common import MoneyDecimal, NonNegativeMoney


class CardCreate(BaseModel):
    bank_id: int
    # Только последние 4 цифры. Полный номер карты не принимается.
    last4: str = Field(pattern=r"^\d{4}$", description="Last 4 digits only; never send the full PAN")
    card_type: CardType = CardType.DEBIT
    credit_limit: NonNegativeMoney | None = None
    currency: str = Field(default="KZT", pattern=r"^[A-Z]{3}$")
    nickname: str | None = Field(default=None, max_length=100)


class CardUpdate(BaseModel):
    card_type: CardType | None = None
    credit_limit: NonNegativeMoney | None = None
    nickname: str | None = Field(default=None, max_length=100)
    is_active: bool | None = None


class CardResponse(BaseModel):
    id: int
    bank_id: int
    bank_name: str
    last4: str
    card_type: CardType
    credit_limit: MoneyDecimal | None
    currency: str
    nickname: str | None
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
