from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class BankBase(BaseModel):
    name: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Bank name"
    )

    logo: str | None = Field(
        default=None,
        max_length=255,
        description="Bank logo URL"
    )


class BankCreate(BankBase):
    pass


class BankUpdate(BaseModel):
    name: str | None = Field(
        default=None,
        min_length=2,
        max_length=100
    )

    logo: str | None = Field(
        default=None,
        max_length=255
    )


class BankResponse(BankBase):
    id: int

    model_config = ConfigDict(
        from_attributes=True
    )


class BankDetail(BankResponse):
    transaction_count: int = 0

    deposit_count: int = 0


class BankListResponse(BaseModel):
    items: list[BankResponse]

    total: int


class BankStatistics(BaseModel):
    bank_id: int

    bank_name: str

    income: float

    expense: float

    balance: float

    transaction_count: int


class SupportedBank(BaseModel):
    name: str

    parser: str

    supported: bool