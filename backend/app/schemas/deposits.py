from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from app.models.enums import Capitalization
from app.schemas.common import CurrencyCodeStr, Page, PatchModel, PositiveMoney
from app.services.finance.deposit import (
    MAX_DEPOSIT_DATE,
    MIN_DEPOSIT_DATE,
    add_months,
    deposit_term_issue,
    term_issue_message,
)

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

# Why a stored deposit has no maturity estimate (see services/deposits.py).
DataIssue = Literal["invalid_date_range", "date_out_of_range", "term_too_long"]


def _check_term(start: date, end: date) -> None:
    issue = deposit_term_issue(start, end)
    if issue is not None:
        raise ValueError(term_issue_message(issue))


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
    start_date: date = Field(ge=MIN_DEPOSIT_DATE, le=MAX_DEPOSIT_DATE)
    end_date: date = Field(ge=MIN_DEPOSIT_DATE, le=MAX_DEPOSIT_DATE)

    @model_validator(mode="after")
    def _term(self) -> Self:
        _check_term(self.start_date, self.end_date)
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
    # The combined term (with stored dates) is checked by the service.
    start_date: date | None = Field(default=None, ge=MIN_DEPOSIT_DATE, le=MAX_DEPOSIT_DATE)
    end_date: date | None = Field(default=None, ge=MIN_DEPOSIT_DATE, le=MAX_DEPOSIT_DATE)


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
    maturity: Maturity | None = Field(
        description="None when the stored deposit breaks a term rule (see data_issue)"
    )
    data_issue: DataIssue | None = Field(
        default=None,
        description="Stable code of the term rule a stored (legacy) deposit breaks; "
        "such a deposit has no estimate and is excluded from totals",
    )
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
    start_date: date = Field(ge=MIN_DEPOSIT_DATE, le=MAX_DEPOSIT_DATE)
    end_date: date | None = Field(default=None, ge=MIN_DEPOSIT_DATE, le=MAX_DEPOSIT_DATE)
    term_months: int | None = Field(default=None, ge=1, le=600)

    @model_validator(mode="after")
    def _one_term(self) -> Self:
        if (self.end_date is None) == (self.term_months is None):
            raise ValueError("Provide exactly one of end_date or term_months")
        _check_term(self.start_date, self.maturity_date)
        return self

    @property
    def maturity_date(self) -> date:
        if self.end_date is not None:
            return self.end_date
        # start_date <= 2200-12-31 and term_months <= 600 keep this in range
        # of ``date``; _check_term then rejects a maturity after 2200-12-31.
        return add_months(self.start_date, self.term_months or 0)


class DepositCalculationResponse(BaseModel):
    principal: Decimal
    currency_code: str
    interest_rate: Decimal
    capitalization: Capitalization
    start_date: date
    maturity_date: date
    maturity: Maturity
