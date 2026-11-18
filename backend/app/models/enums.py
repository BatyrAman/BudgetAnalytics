"""Domain enums shared by models, services, parsers and the finance engine."""

import enum


class TransactionType(str, enum.Enum):
    """Explicit transaction semantics. ``amount`` is always positive; the type
    alone defines the direction and how the row enters calculations:

    * ``INCOME``       — money earned (salary, interest received, ...): +income
    * ``EXPENSE``      — money spent: +expenses
    * ``REFUND``       — money returned for an earlier expense: −expenses
                         (a refund is NOT income)
    * ``TRANSFER_IN``  — money moved in from the user's own account/card
    * ``TRANSFER_OUT`` — money moved out to the user's own account/card

    Transfers are excluded from income, expenses, cash flow and savings rate.

    Stored in PostgreSQL as the native ENUM ``transactiontype`` using member
    NAMES (``INCOME``, ...), as created by the initial migration.
    """

    INCOME = "income"
    EXPENSE = "expense"
    REFUND = "refund"
    TRANSFER_IN = "transfer_in"
    TRANSFER_OUT = "transfer_out"


class CategoryKind(str, enum.Enum):
    """Which transactions a category is meant for.

    * ``income``  — only income;
    * ``expense`` — expenses and their refunds;
    * ``any``     — no restriction (transfers, "uncategorized", and every
      category created before kinds existed — backward compatible).
    Transfers may use a category of any kind.
    """

    INCOME = "income"
    EXPENSE = "expense"
    ANY = "any"


_INCOME_SIDE = {"income"}
_EXPENSE_SIDE = {"expense", "refund"}


def category_allows(kind: "CategoryKind", transaction_type: "TransactionType") -> bool:
    """Business rule: income categories only for income; expense categories
    for expenses and refunds; ``any`` and transfers are unrestricted."""

    kind = CategoryKind(kind)
    value = TransactionType(transaction_type).value
    if kind is CategoryKind.ANY or value in ("transfer_in", "transfer_out"):
        return True
    if kind is CategoryKind.INCOME:
        return value in _INCOME_SIDE
    return value in _EXPENSE_SIDE


class AccountType(str, enum.Enum):
    CASH = "cash"
    CURRENT = "current"
    CARD = "card"
    SAVINGS = "savings"
    CREDIT_CARD = "credit_card"
    OTHER = "other"


class Capitalization(str, enum.Enum):
    """How often deposit interest is added to the principal.

    ``NONE`` = simple interest (paid at maturity, never compounded).
    """

    NONE = "none"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUALLY = "annually"


def enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    """Persist enum *values* (not names) for non-native string enums."""

    return [member.value for member in enum_cls]
