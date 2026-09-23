from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.common import MoneyDecimal, NonNegativeMoney


class UserResponse(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FinancialProfileResponse(BaseModel):
    monthly_income_declared: MoneyDecimal | None
    dependents: int
    city: str | None
    consent_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class FinancialProfileUpdate(BaseModel):
    monthly_income_declared: NonNegativeMoney | None = None
    dependents: int | None = Field(default=None, ge=0, le=20)
    city: str | None = Field(default=None, max_length=100)
    # true — пользователь дал согласие на обработку персональных данных.
    consent: bool | None = None
