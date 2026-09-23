from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import MoneyDecimal, PercentDecimal, PositiveMoney


class DepositBase(BaseModel):
    amount: PositiveMoney = Field(description="Deposit amount")

    interest_rate: Decimal = Field(
        ...,
        ge=0,
        le=100,
        decimal_places=2,
        description="Annual interest rate (%)"
    )

    start_date: date

    end_date: date

    bank_id: int


class DepositCreate(DepositBase):
    pass


class DepositUpdate(BaseModel):
    amount: PositiveMoney | None = None

    interest_rate: Decimal | None = Field(
        default=None,
        ge=0,
        le=100,
        decimal_places=2
    )

    start_date: date | None = None

    end_date: date | None = None

    bank_id: int | None = None


class DepositResponse(BaseModel):
    id: int

    amount: MoneyDecimal

    interest_rate: PercentDecimal

    start_date: date

    end_date: date

    bank_id: int

    user_id: int

    created_at: datetime

    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True
    )


class DepositDetail(DepositResponse):
    bank_name: str

    duration_days: int

    expected_profit: MoneyDecimal

    expected_amount: MoneyDecimal

    is_active: bool


class DepositListResponse(BaseModel):
    items: list[DepositResponse]

    total: int


class DepositStatistics(BaseModel):
    total_deposits: int

    total_amount: MoneyDecimal

    total_expected_profit: MoneyDecimal

    total_expected_value: MoneyDecimal


class DepositForecast(BaseModel):
    deposit_id: int

    maturity_date: date

    expected_profit: MoneyDecimal

    expected_amount: MoneyDecimal


class DepositChartItem(BaseModel):
    label: str

    amount: MoneyDecimal
