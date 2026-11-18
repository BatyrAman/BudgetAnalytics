"""Account use cases. Balances are always computed by the finance engine
(``account_balance``) from the opening balance and linked transactions."""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, DomainValidationError, NotFoundError
from app.models.account import Account
from app.models.bank import Bank
from app.models.types import SUPPORTED_MINOR_UNITS
from app.models.user import User
from app.repositories.account import AccountRepository
from app.repositories.currency import CurrencyRepository
from app.repositories.transaction import TransactionRepository
from app.schemas.account import AccountCreate, AccountUpdate
from app.services.finance import CurrencySpec, account_balance


@dataclass(frozen=True)
class AccountWithBalance:
    account: Account
    balance: Decimal


class AccountService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.accounts = AccountRepository(db)
        self.transactions = TransactionRepository(db)

    async def _balances(self, user_id: int, accounts: list[Account]) -> list[AccountWithBalance]:
        flows = await self.transactions.account_flows(user_id)
        return [
            AccountWithBalance(
                account=a,
                balance=account_balance(
                    a.opening_balance,
                    flows.get(a.id, {}),
                    CurrencySpec(a.currency_code, SUPPORTED_MINOR_UNITS),
                ),
            )
            for a in accounts
        ]

    async def list(self, user_id: int, include_archived: bool) -> list[AccountWithBalance]:
        accounts = await self.accounts.list_for_user(user_id, include_archived=include_archived)
        return await self._balances(user_id, accounts)

    async def get_owned(self, account_id: int, user_id: int) -> Account:
        account = await self.accounts.get_for_user(account_id, user_id)
        if account is None:
            raise NotFoundError("Account not found")
        return account

    async def get(self, account_id: int, user_id: int) -> AccountWithBalance:
        account = await self.get_owned(account_id, user_id)
        return (await self._balances(user_id, [account]))[0]

    async def _check_bank(self, bank_id: int | None) -> None:
        if bank_id is not None and await self.db.get(Bank, bank_id) is None:
            raise DomainValidationError("Bank not found")

    async def create(self, payload: AccountCreate, user: User) -> AccountWithBalance:
        currency = payload.currency or user.default_currency_code
        if await CurrencyRepository(self.db).get(currency) is None:
            raise DomainValidationError("Unknown currency")
        await self._check_bank(payload.bank_id)
        account = Account(
            user_id=user.id,
            name=payload.name,
            account_type=payload.account_type,
            currency_code=currency,
            bank_id=payload.bank_id,
            last4=payload.last4,
            opening_balance=payload.opening_balance,
            opening_balance_at=payload.opening_balance_at or datetime.now(UTC),
        )
        self.accounts.add(account)
        await self.db.flush()
        await self.db.refresh(account)
        return (await self._balances(user.id, [account]))[0]

    async def update(
        self, account_id: int, payload: AccountUpdate, user_id: int
    ) -> AccountWithBalance:
        account = await self.get_owned(account_id, user_id)
        changes = payload.model_dump(exclude_unset=True)
        if "bank_id" in changes:
            await self._check_bank(changes["bank_id"])
        for field, value in changes.items():
            setattr(account, field, value)
        await self.db.flush()
        await self.db.refresh(account)
        return (await self._balances(user_id, [account]))[0]

    async def delete(self, account_id: int, user_id: int) -> None:
        account = await self.get_owned(account_id, user_id)
        if await self.transactions.count_for_account(account.id, user_id):
            raise ConflictError("Account has transactions; archive it instead of deleting")
        await self.db.delete(account)
