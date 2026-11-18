from datetime import date, datetime
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, Field, model_validator

from app.models.enums import Capitalization
from app.schemas.common import CurrencyCodeStr, Page, PatchModel, PositiveMoney

_NOMINAL = Field(ge=0, le=100, max_digits=5, decimal_places=2, description="Nominal annual rate, %")
_EFFECTIVE = Field(
    default=None,
    ge=0,
    le=1000,
    max_digits=7,
    decimal_places=4,
    description=(
        "ГЭСВ as published by the bank, % (stored as given; never used as the nominal rate)"
    ),
)

ASSUMPTIONS = [
    "Nominal rate, ACT/365 day count; interest rounded once to the currency minor unit (half up).",
    "Capitalization on monthly/quarterly/annual anniversaries of the start date; "
    "simple interest for the remaining days.",
    "No top-ups, withdrawals, fees, taxes or early-termination rules are modelled; "
    "the bank's figures may differ.",
]


class DepositCreate(BaseModel):
    bank_id: int
    principal: PositiveMoney
    currency: CurrencyCodeStr | None = Field(
        default=None, description="Defaults to the user's default currency"
    )
    interest_rate: Decimal = _NOMINAL
    effective_rate: Decimal | None = _EFFECTIVE
    capitalization: Capitalization = Capitalization.NONE
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def _term(self) -> Self:
        if self.end_date <= self.start_date:
            raise ValueError("end_date must be after start_date")
        return self


class DepositUpdate(PatchModel):
    nullable = frozenset({"effective_rate"})

    bank_id: int | None = None
    principal: PositiveMoney | None = None
    interest_rate: Decimal | None = Field(
        default=None, ge=0, le=100, max_digits=5, decimal_places=2
    )
    effective_rate: Decimal | None = _EFFECTIVE
    capitalization: Capitalization | None = None
    start_date: date | None = None
    end_date: date | None = None


class Maturity(BaseModel):
    term_days: int
    capitalization_periods: int
    stub_days: int
    interest: Decimal
    maturity_amount: Decimal
    effective_annual_rate: Decimal | None = Field(
        description="EAR of the nominal rate for this capitalization (None without "
        "capitalization). A compounding conversion only — NOT the bank's ГЭСВ."
    )
    assumptions: list[str] = ASSUMPTIONS


class DepositResponse(BaseModel):
    id: int
    bank_id: int
    principal: Decimal
    currency_code: str
    interest_rate: Decimal
    effective_rate: Decimal | None
    capitalization: Capitalization
    start_date: date
    end_date: date
    maturity: Maturity
    created_at: datetime
    updated_at: datetime


class DepositListResponse(Page[DepositResponse]):
    pass


class DepositCalculationRequest(BaseModel):
    """Stateless calculator: give either ``end_date`` or ``term_months``."""

    principal: PositiveMoney
    currency: CurrencyCodeStr = "KZT"
    interest_rate: Decimal = _NOMINAL
    capitalization: Capitalization = Capitalization.NONE
    start_date: date
    end_date: date | None = None
    term_months: int | None = Field(default=None, ge=1, le=600)

    @model_validator(mode="after")
    def _one_term(self) -> Self:
        if (self.end_date is None) == (self.term_months is None):
            raise ValueError("Provide exactly one of end_date or term_months")
        if self.end_date is not None and self.end_date <= self.start_date:
            raise ValueError("end_date must be after start_date")
        return self


class DepositCalculationResponse(BaseModel):
    principal: Decimal
    currency_code: str
    interest_rate: Decimal
    capitalization: Capitalization
    start_date: date
    maturity_date: date
    maturity: Maturity
