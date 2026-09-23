from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import MoneyDecimal, PercentDecimal
from app.services.analytics.periods import Period


class PeriodInfo(BaseModel):
    type: Period
    date_from: datetime
    date_to: datetime  # не включительно
    granularity: str
    currency: str


class PeriodTotals(BaseModel):
    income: MoneyDecimal
    expense: MoneyDecimal
    net: MoneyDecimal


class OverviewSummary(BaseModel):
    income: MoneyDecimal
    expense: MoneyDecimal
    net: MoneyDecimal
    savings_rate: PercentDecimal
    income_count: int
    expense_count: int
    average_daily_expense: MoneyDecimal
    previous: PeriodTotals
    # % изменения к прошлому периоду; null — в прошлом периоде нуль
    income_change_percent: PercentDecimal | None
    expense_change_percent: PercentDecimal | None


class SeriesPoint(BaseModel):
    bucket: datetime
    label: str
    income: MoneyDecimal
    expense: MoneyDecimal
    net: MoneyDecimal


class CategoryShare(BaseModel):
    category_id: int | None
    name: str
    color: str | None
    amount: MoneyDecimal
    share_percent: PercentDecimal
    transaction_count: int


class MerchantTotal(BaseModel):
    merchant: str
    amount: MoneyDecimal
    transaction_count: int


class TopExpense(BaseModel):
    transaction_id: int
    transaction_date: datetime
    amount: MoneyDecimal
    merchant: str | None
    category_id: int | None


class RecurringPayment(BaseModel):
    merchant: str
    amount: MoneyDecimal
    occurrences: int
    months: int
    last_date: datetime


class BankShare(BaseModel):
    bank_id: int
    bank_name: str
    income: MoneyDecimal
    expense: MoneyDecimal
    transaction_count: int


class CardShare(BaseModel):
    card_id: int | None
    last4: str | None
    income: MoneyDecimal
    expense: MoneyDecimal
    transaction_count: int


class WeekdayTotal(BaseModel):
    weekday: int  # 1 = понедельник … 7 = воскресенье
    amount: MoneyDecimal
    transaction_count: int


class AnalyticsOverview(BaseModel):
    period: PeriodInfo
    summary: OverviewSummary
    series: list[SeriesPoint]
    categories: list[CategoryShare]
    top_merchants: list[MerchantTotal]
    top_expenses: list[TopExpense]
    recurring: list[RecurringPayment]
    banks: list[BankShare]
    cards: list[CardShare]
    weekdays: list[WeekdayTotal]
