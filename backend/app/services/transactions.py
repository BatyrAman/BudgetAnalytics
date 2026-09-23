from __future__ import annotations

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError, NotFoundError
from app.models.enums import CategoryKind, CategorySource, TransactionType
from app.models.transaction import Transaction
from app.repositories.analytics import AnalyticsRepository, Scope
from app.repositories.banks import BankRepository
from app.repositories.cards import CardRepository
from app.repositories.categories import CategoryRepository
from app.repositories.transactions import TransactionFilters, TransactionRepository
from app.schemas.transaction import (
    TransactionChartItem,
    TransactionCreate,
    TransactionDetail,
    TransactionResponse,
    TransactionStatistics,
    TransactionUpdate,
)
from app.services.imports.normalize import normalize_merchant


class TransactionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = TransactionRepository(session)
        self.categories = CategoryRepository(session)
        self.banks = BankRepository(session)
        self.cards = CardRepository(session)
        self.analytics = AnalyticsRepository(session)

    async def _get_owned(self, transaction_id: int, user_id: int) -> Transaction:
        transaction = await self.repo.get_owned(transaction_id, user_id)
        if transaction is None:
            raise NotFoundError("Transaction not found", code="TRANSACTION_NOT_FOUND")
        return transaction

    async def _validate_refs(
        self,
        user_id: int,
        transaction_type: TransactionType,
        category_id: int | None,
        bank_id: int | None,
        card_id: int | None,
    ) -> None:
        # Ссылки из тела запроса: чужая/несуществующая сущность — 400,
        # без раскрытия, существует ли она у другого пользователя.
        if category_id is not None:
            category = await self.categories.get_visible(category_id, user_id)
            if category is None:
                raise AppError("Category not found", code="CATEGORY_NOT_FOUND")
            expected = CategoryKind.INCOME if transaction_type == TransactionType.INCOME else CategoryKind.EXPENSE
            if category.kind != expected:
                raise AppError(
                    "Category kind does not match transaction type",
                    code="CATEGORY_KIND_MISMATCH",
                )
        if bank_id is not None and await self.banks.get(bank_id) is None:
            raise AppError("Bank not found", code="BANK_NOT_FOUND")
        if card_id is not None and await self.cards.get_owned(card_id, user_id) is None:
            raise AppError("Card not found", code="CARD_NOT_FOUND")

    async def create(self, user_id: int, payload: TransactionCreate) -> Transaction:
        await self._validate_refs(
            user_id, payload.transaction_type, payload.category_id, payload.bank_id, payload.card_id
        )
        transaction = self.repo.add(
            Transaction(
                amount=payload.amount,
                description=payload.description,
                merchant=normalize_merchant(payload.merchant or payload.description),
                transaction_type=payload.transaction_type,
                transaction_date=payload.transaction_date,
                category_id=payload.category_id,
                category_source=CategorySource.USER,
                bank_id=payload.bank_id,
                card_id=payload.card_id,
                is_recurring=payload.is_recurring,
                currency=settings.DEFAULT_CURRENCY,
                user_id=user_id,
            )
        )
        await self.session.commit()
        await self.session.refresh(transaction)
        return transaction

    async def search(self, user_id: int, filters: TransactionFilters, limit: int, offset: int):
        return await self.repo.search(user_id, filters, limit, offset)

    async def get_detail(self, transaction_id: int, user_id: int) -> TransactionDetail:
        transaction = await self.repo.get_detailed(transaction_id, user_id)
        if transaction is None:
            raise NotFoundError("Transaction not found", code="TRANSACTION_NOT_FOUND")
        return TransactionDetail(
            **TransactionResponse.model_validate(transaction).model_dump(),
            category_name=transaction.category.name if transaction.category else "—",
            bank_name=transaction.bank.name if transaction.bank else "—",
        )

    async def update(self, transaction_id: int, user_id: int, payload: TransactionUpdate) -> Transaction:
        transaction = await self._get_owned(transaction_id, user_id)
        updates = payload.model_dump(exclude_unset=True)

        # NULL для обязательных полей не принимаем.
        for required in ("amount", "transaction_type", "transaction_date", "bank_id", "category_id"):
            if required in updates and updates[required] is None:
                raise AppError(f"{required} cannot be null", code="VALIDATION_ERROR", status_code=422)

        new_type = updates.get("transaction_type", transaction.transaction_type)
        category_id = updates.get("category_id", transaction.category_id)
        category_changed = "category_id" in updates or "transaction_type" in updates
        await self._validate_refs(
            user_id,
            new_type,
            category_id if category_changed else None,
            updates.get("bank_id"),
            updates.get("card_id"),
        )

        for field, value in updates.items():
            setattr(transaction, field, value)
        if "merchant" in updates:
            transaction.merchant = normalize_merchant(updates["merchant"])
        if "category_id" in updates:
            # Ручная правка — основа «памяти» категоризации.
            transaction.category_source = CategorySource.USER

        await self.session.commit()
        await self.session.refresh(transaction)
        return transaction

    async def delete(self, transaction_id: int, user_id: int) -> None:
        transaction = await self._get_owned(transaction_id, user_id)
        await self.repo.delete(transaction)
        await self.session.commit()

    async def statistics(self, user_id: int) -> TransactionStatistics:
        row = await self.repo.statistics(user_id, settings.DEFAULT_CURRENCY)
        income, expense = Decimal(row.income), Decimal(row.expense)
        return TransactionStatistics(
            total_transactions=row.count,
            total_income=income,
            total_expense=expense,
            current_balance=income - expense,
            average_expense=Decimal(row.avg_expense),
            average_income=Decimal(row.avg_income),
        )

    async def chart(self, user_id: int, months: int) -> list[TransactionChartItem]:
        rows = await self.analytics.monthly_totals(Scope(user_id=user_id, currency=settings.DEFAULT_CURRENCY))
        return [
            TransactionChartItem(label=f"{bucket.year}-{bucket.month:02d}", income=income, expense=expense)
            for bucket, income, expense in rows[-months:]
        ]
