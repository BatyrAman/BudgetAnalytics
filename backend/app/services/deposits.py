"""Adapter between the ``Deposit`` model and the finance engine.

All deposit math lives in ``app.services.finance.deposit``; this module only
maps a stored deposit to engine inputs, so the API endpoints (investments,
dashboard) share one implementation.

Stored currencies always have 2 minor units (see ``app.models.types``).

Stored deposits may predate the term bounds (``deposit_term_issue``): the
legacy API accepted any dates. Such a deposit is never deleted, but it gets
no maturity estimate (``data_issue`` names the broken rule) and is excluded
from every aggregate — use ``valid_deposits`` / ``valid_term_clause``.
"""

from collections.abc import Iterable
from datetime import date
from decimal import Decimal

from sqlalchemy import ColumnElement, Date, and_, cast, func

from app.core.errors import DomainValidationError
from app.models.deposit import Deposit
from app.models.types import SUPPORTED_MINOR_UNITS
from app.services.finance import CurrencySpec, DepositMaturity, deposit_maturity
from app.services.finance.deposit import (
    MAX_DEPOSIT_DATE,
    MAX_DEPOSIT_TERM_MONTHS,
    MIN_DEPOSIT_DATE,
    deposit_term_issue,
    term_issue_message,
)


def validate_deposit_term(start_date: date, end_date: date) -> None:
    """Reject a term that breaks a bound (422 with a stable ``code``)."""

    issue = deposit_term_issue(start_date, end_date)
    if issue is not None:
        raise DomainValidationError(term_issue_message(issue), code=issue)


def deposit_data_issue(deposit: Deposit) -> str | None:
    """Stable code of the rule a stored deposit breaks, or ``None``."""

    return deposit_term_issue(deposit.start_date, deposit.end_date)


def maturity_of(deposit: Deposit) -> DepositMaturity:
    """Maturity estimate of a VALID deposit. Raises ``FinanceInputError``
    otherwise — code reading stored rows uses ``valid_maturity_of``."""

    return deposit_maturity(
        principal=deposit.amount,
        annual_rate_percent=deposit.interest_rate,
        start_date=deposit.start_date,
        end_date=deposit.end_date,
        capitalization=deposit.capitalization,
        currency=CurrencySpec(deposit.currency_code, SUPPORTED_MINOR_UNITS),
    )


def expected_profit(deposit: Deposit) -> Decimal:
    return maturity_of(deposit).interest


def valid_maturity_of(deposit: Deposit) -> DepositMaturity | None:
    """Maturity estimate, or ``None`` for a deposit with a ``data_issue``."""

    if deposit_data_issue(deposit) is not None:
        return None
    return maturity_of(deposit)


def valid_deposits(deposits: Iterable[Deposit]) -> list[Deposit]:
    """Deposits that may enter aggregates (no ``data_issue``)."""

    return [d for d in deposits if deposit_data_issue(d) is None]


def valid_term_clause() -> ColumnElement[bool]:
    """SQL twin of ``deposit_data_issue(d) is None`` for aggregate queries.

    PostgreSQL ``date + interval 'N months'`` clamps to the month end exactly
    like ``add_months`` (29 Feb + 12 months = 28 Feb).
    """

    max_end = cast(Deposit.start_date + func.make_interval(0, MAX_DEPOSIT_TERM_MONTHS), Date)
    return and_(
        Deposit.start_date >= MIN_DEPOSIT_DATE,
        Deposit.start_date <= MAX_DEPOSIT_DATE,
        Deposit.end_date >= MIN_DEPOSIT_DATE,
        Deposit.end_date <= MAX_DEPOSIT_DATE,
        Deposit.end_date > Deposit.start_date,
        Deposit.end_date <= max_end,
    )
