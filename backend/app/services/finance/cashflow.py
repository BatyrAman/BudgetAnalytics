"""Income, expenses, net cash flow and savings rate.

DEFINITIONS (one currency at a time — amounts in different currencies are
never added together and no exchange rate is ever applied implicitly):

    income        = Σ amount where type = INCOME
    gross_expenses= Σ amount where type = EXPENSE
    refunds       = Σ amount where type = REFUND
    net_expenses  = gross_expenses − refunds        (may be < 0 if refunds
                                                     exceed expenses)
    net_cash_flow = income − net_expenses
    transfers_in / transfers_out are reported separately and EXCLUDED from
    income, expenses, net cash flow and savings rate (moving money between the
    user's own accounts is neither earning nor spending).

    savings_rate  = (income − net_expenses) / income × 100 %
                    undefined (None) when income = 0 — it is NOT reported as 0 %
                    or 100 %, because neither would be true. May be negative.

Net cash flow is NOT an account balance: it only covers the transactions in
the analysed set and ignores opening balances.

Rounding: sums of 2-decimal amounts are exact; totals are still passed
through ``quantize_money`` (ROUND_HALF_UP) as a guard. Savings rate is rounded
to 2 decimal places of a percent.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.models.enums import TransactionType
from app.services.finance.money import (
    HUNDRED,
    ZERO,
    CurrencySpec,
    FinanceInputError,
    calc_context,
    quantize_money,
    quantize_ratio_percent,
    require_positive,
    to_decimal,
)


@dataclass(frozen=True)
class CashflowItem:
    amount: Decimal
    transaction_type: TransactionType
    currency_code: str
    occurred_at: datetime


@dataclass(frozen=True)
class CashflowTotals:
    currency_code: str
    income: Decimal
    gross_expenses: Decimal
    refunds: Decimal
    net_expenses: Decimal
    net_cash_flow: Decimal
    transfers_in: Decimal
    transfers_out: Decimal
    transaction_count: int

    @property
    def savings_rate(self) -> Decimal | None:
        return savings_rate(self.income, self.net_expenses)


def summarize(items: Iterable[CashflowItem], currency: CurrencySpec) -> CashflowTotals:
    """Totals for items that are ALL in ``currency``; any other currency raises
    ``FinanceInputError`` (use ``summarize_by_currency`` for mixed sets)."""

    sums = {t: ZERO for t in TransactionType}
    count = 0
    with calc_context():
        for item in items:
            if item.currency_code != currency.code:
                raise FinanceInputError(
                    f"Cannot add {item.currency_code} to {currency.code} totals "
                    "without an explicit exchange rate"
                )
            amount = require_positive(item.amount, "amount")
            sums[TransactionType(item.transaction_type)] += amount
            count += 1

    return totals_from_sums(sums, count, currency)


def totals_from_sums(
    sums: Mapping[TransactionType, Decimal], count: int, currency: CurrencySpec
) -> CashflowTotals:
    """Same definitions as ``summarize``, from per-type sums already
    aggregated (e.g. by SQL ``SUM(amount) GROUP BY transaction_type``) for ONE
    currency. Missing types count as zero; sums must be >= 0."""

    if count < 0:
        raise FinanceInputError("count must not be negative")
    clean = {t: ZERO for t in TransactionType}
    for kind, value in sums.items():
        amount = to_decimal(value, f"sum of {TransactionType(kind).value}")
        if amount < 0:
            raise FinanceInputError("aggregated sums must not be negative")
        clean[TransactionType(kind)] = amount
    sums = clean

    with calc_context():
        net_expenses = sums[TransactionType.EXPENSE] - sums[TransactionType.REFUND]
        net_cash_flow = sums[TransactionType.INCOME] - net_expenses

    return CashflowTotals(
        currency_code=currency.code,
        income=quantize_money(sums[TransactionType.INCOME], currency),
        gross_expenses=quantize_money(sums[TransactionType.EXPENSE], currency),
        refunds=quantize_money(sums[TransactionType.REFUND], currency),
        net_expenses=quantize_money(net_expenses, currency),
        net_cash_flow=quantize_money(net_cash_flow, currency),
        transfers_in=quantize_money(sums[TransactionType.TRANSFER_IN], currency),
        transfers_out=quantize_money(sums[TransactionType.TRANSFER_OUT], currency),
        transaction_count=count,
    )


def summarize_by_currency(
    items: Iterable[CashflowItem], currencies: Mapping[str, CurrencySpec]
) -> dict[str, CashflowTotals]:
    """One ``CashflowTotals`` per currency present in ``items``."""

    grouped: dict[str, list[CashflowItem]] = {}
    for item in items:
        grouped.setdefault(item.currency_code, []).append(item)

    result: dict[str, CashflowTotals] = {}
    for code in sorted(grouped):
        if code not in currencies:
            raise FinanceInputError(f"Unknown currency: {code}")
        result[code] = summarize(grouped[code], currencies[code])
    return result


def total_income(items: Iterable[CashflowItem], currency: CurrencySpec) -> Decimal:
    return summarize(items, currency).income


def total_expenses(items: Iterable[CashflowItem], currency: CurrencySpec) -> Decimal:
    """Net expenses (expenses minus refunds)."""

    return summarize(items, currency).net_expenses


def net_cash_flow(items: Iterable[CashflowItem], currency: CurrencySpec) -> Decimal:
    return summarize(items, currency).net_cash_flow


def savings_rate(income: Decimal, net_expenses: Decimal) -> Decimal | None:
    """(income − net_expenses) / income × 100, rounded to 0.01 %.

    Returns ``None`` when income is zero (undefined). Negative income is an
    input error; negative net expenses (refunds > expenses) are allowed.
    """

    income = to_decimal(income, "income")
    net_expenses = to_decimal(net_expenses, "net_expenses")
    if income < 0:
        raise FinanceInputError("income must not be negative")
    if income == 0:
        return None
    with calc_context():
        rate = (income - net_expenses) / income * HUNDRED
    return quantize_ratio_percent(rate)
