from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr


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
