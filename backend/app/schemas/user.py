from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserBase(BaseModel):
    full_name: str
    email: EmailStr


class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    full_name: str | None = None
    email: EmailStr | None = None


class UserResponse(UserBase):
    id: int
    is_active: bool
    default_currency_code: str = Field(
        description="ISO 4217 code used when a request omits `currency` (e.g. KZT)",
        examples=["KZT"],
    )
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserProfile(UserResponse):
    total_transactions: int = 0
    total_budgets: int = 0
    total_deposits: int = 0


class UserListResponse(BaseModel):
    users: list[UserResponse]


class UserStatistics(BaseModel):
    income: float
    expense: float
    balance: float
    savings: float
