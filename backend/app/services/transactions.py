"""Transaction use cases with ownership checks on every referenced resource.

Rules:
* category: must be visible to the user (system or own) — else 400
  "Category not found" (the same answer for missing and foreign ids);
* account: must be the user's own — else 400 "Account not found";
  a linked transaction must be in the account's currency (also enforced by a
  composite foreign key in the database);
* currency: an existing currency; defaults to the account's, else the user's.
"""

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, NotFoundError
from app.models.bank import Bank
from app.models.enums import TransactionType, category_allows
from app.models.transaction import Transaction
from app.models.user import User
from app.repositories.account import AccountRepository
from app.repositories.category import CategoryRepository
from app.repositories.currency import CurrencyRepository
from app.repositories.transaction import TransactionFilters, TransactionRepository
from app.schemas.transaction import TransactionCreate, TransactionUpdate


class TransactionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.transactions = TransactionRepository(db)

    async def get(self, transaction_id: int, user_id: int) -> Transaction:
        transaction = await self.transactions.get_for_user(transaction_id, user_id)
        if transaction is None:
            raise NotFoundError("Transaction not found")
        return transaction

    async def list(
        self, user_id: int, filters: TransactionFilters, limit: int, offset: int
    ) -> tuple[list[Transaction], int]:
        return await self.transactions.list_filtered(user_id, filters, limit, offset)

    # ------------------------------------------------------------ validation
    async def _check_category(
        self, category_id: int, user_id: int, transaction_type: TransactionType | None = None
    ) -> None:
        # Another user's private category is reported exactly like a missing one.
        category = await CategoryRepository(self.db).get_visible(category_id, user_id)
        if category is None:
            raise AppError("Category not found")
        if transaction_type is not None and not category_allows(category.kind, transaction_type):
            raise AppError(
                f"Category '{category.name}' ({category.kind.value}) cannot be used "
                f"for a {transaction_type.value} transaction"
            )

    async def _check_bank(self, bank_id: int | None) -> None:
        if bank_id is not None and await self.db.get(Bank, bank_id) is None:
            raise AppError("Bank not found")

    async def _resolve_currency(
        self, user: User, account_id: int | None, requested: str | None
    ) -> str:
        if account_id is not None:
            account = await AccountRepository(self.db).get_for_user(account_id, user.id)
            if account is None:
                raise AppError("Account not found")
            if requested is not None and requested != account.currency_code:
                raise AppError("Currency must match the account's currency")
            return account.currency_code
        currency = requested or user.default_currency_code
        if await CurrencyRepository(self.db).get(currency) is None:
            raise AppError("Unknown currency")
        return currency

    # ------------------------------------------------------------ commands
    async def create(self, payload: TransactionCreate, user: User) -> Transaction:
        await self._check_category(
            payload.category_id, user.id, TransactionType(payload.transaction_type.value)
        )
        await self._check_bank(payload.bank_id)
        currency = await self._resolve_currency(user, payload.account_id, payload.currency)
        transaction = Transaction(
            amount=payload.amount,
            currency_code=currency,
            description=payload.description,
            transaction_type=TransactionType(payload.transaction_type.value),
            transaction_date=payload.transaction_date,
            category_id=payload.category_id,
            bank_id=payload.bank_id,
            account_id=payload.account_id,
            user_id=user.id,
        )
        self.transactions.add(transaction)
        await self.db.flush()
        await self.db.refresh(transaction)
        return transaction

    async def update(
        self, transaction_id: int, payload: TransactionUpdate, user: User
    ) -> Transaction:
        transaction = await self.get(transaction_id, user.id)
        changes = payload.model_dump(exclude_unset=True)

        if "category_id" in changes or "transaction_type" in changes:
            final_type = TransactionType(
                changes["transaction_type"].value
                if "transaction_type" in changes
                else transaction.transaction_type
            )
            await self._check_category(
                changes.get("category_id", transaction.category_id), user.id, final_type
            )
        if "bank_id" in changes:
            await self._check_bank(changes["bank_id"])
        if "account_id" in changes or "currency" in changes:
            account_id = changes.get("account_id", transaction.account_id)
            requested = changes.pop("currency", None)
            if account_id is None and requested is None:
                requested = transaction.currency_code
            changes["currency_code"] = await self._resolve_currency(user, account_id, requested)
        if "transaction_type" in changes:
            changes["transaction_type"] = TransactionType(changes["transaction_type"].value)

        for field, value in changes.items():
            setattr(transaction, field, value)
        await self.db.flush()
        await self.db.refresh(transaction)
        return transaction

    async def delete(self, transaction_id: int, user_id: int) -> None:
        transaction = await self.get(transaction_id, user_id)
        await self.transactions.delete(transaction)


def inclusive_end_to_exclusive(end: datetime | None) -> datetime | None:
    """API ``end_date`` filters are inclusive; the repository uses [start, end)."""

    return None if end is None else end + timedelta(microseconds=1)
