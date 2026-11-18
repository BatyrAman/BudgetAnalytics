from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import PaginationParams, get_current_active_user, get_db
from app.core.errors import ErrorResponse
from app.models.bank import Bank
from app.models.category import Category
from app.models.enums import TransactionType as TransactionTypeModel
from app.models.transaction import Transaction
from app.models.user import User
from app.repositories.transaction import TransactionFilters
from app.schemas.category import CategoryCreate, CategoryResponse
from app.schemas.common import to_utc
from app.schemas.transaction import (
    TransactionChartItem,
    TransactionCreate,
    TransactionDetail,
    TransactionListResponse,
    TransactionResponse,
    TransactionStatistics,
    TransactionType,
    TransactionUpdate,
)
from app.services.categories import CategoryService
from app.services.transactions import TransactionService, inclusive_end_to_exclusive

router = APIRouter(prefix="/transactions", tags=["Transactions"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorResponse},
    401: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}
_LEGACY = (
    "DEPRECATED: all-time income/expense of the user's default currency only; "
    "refunds and transfers are ignored. Use /analytics/* instead."
)


async def _to_detail(db: AsyncSession, transaction: Transaction) -> TransactionDetail:
    category = await db.get(Category, transaction.category_id)
    bank = await db.get(Bank, transaction.bank_id) if transaction.bank_id else None
    return TransactionDetail(
        **TransactionResponse.model_validate(transaction).model_dump(),
        category_name=category.name if category else "—",
        bank_name=bank.name if bank else "—",
    )


@router.post(
    "", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED, responses=_ERRORS
)
async def create_transaction(
    payload: TransactionCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Transaction:
    transaction = await TransactionService(db).create(payload, current_user)
    await db.commit()
    return transaction


@router.get("", response_model=TransactionListResponse, responses=_ERRORS)
async def list_transactions(
    pagination: PaginationParams = Depends(),
    start_date: datetime | None = Query(default=None, description="Inclusive; no offset = UTC"),
    end_date: datetime | None = Query(default=None, description="Inclusive; no offset = UTC"),
    category_id: int | None = Query(default=None),
    account_id: int | None = Query(default=None),
    bank_id: int | None = Query(default=None),
    transaction_type: TransactionType | None = Query(default=None),
    currency: str | None = Query(default=None, pattern=r"^[A-Z]{3}$"),
    min_amount: Decimal | None = Query(default=None, ge=0, max_digits=18, decimal_places=2),
    max_amount: Decimal | None = Query(default=None, ge=0, max_digits=18, decimal_places=2),
    search: str | None = Query(default=None, min_length=1, max_length=100),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> TransactionListResponse:
    """The user's transactions, newest first, filtered and paginated."""

    start = to_utc(start_date) if start_date else None
    end = to_utc(end_date) if end_date else None
    if start and end and end < start:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="end_date must not be before start_date",
        )
    if min_amount is not None and max_amount is not None and max_amount < min_amount:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="max_amount must not be less than min_amount",
        )
    filters = TransactionFilters(
        start=start,
        end=inclusive_end_to_exclusive(end),
        category_id=category_id,
        account_id=account_id,
        bank_id=bank_id,
        transaction_type=TransactionTypeModel(transaction_type.value) if transaction_type else None,
        currency_code=currency,
        min_amount=min_amount,
        max_amount=max_amount,
        search=search,
    )
    items, total = await TransactionService(db).list(
        current_user.id, filters, pagination.limit, pagination.offset
    )
    return TransactionListResponse(
        items=[TransactionResponse.model_validate(t) for t in items],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


# ---------------------------------------------------------------- legacy (deprecated)
def _legacy_scope(user: User):
    return (
        Transaction.user_id == user.id,
        Transaction.currency_code == user.default_currency_code,
    )


@router.get(
    "/statistics", response_model=TransactionStatistics, deprecated=True, description=_LEGACY
)
async def get_statistics(
    current_user: User = Depends(get_current_active_user), db: AsyncSession = Depends(get_db)
) -> TransactionStatistics:
    rows = await db.execute(
        select(
            Transaction.transaction_type,
            func.coalesce(func.sum(Transaction.amount), 0),
            func.coalesce(func.avg(Transaction.amount), 0),
        )
        .where(*_legacy_scope(current_user))
        .group_by(Transaction.transaction_type)
    )
    sums = {kind: (Decimal(total), Decimal(avg)) for kind, total, avg in rows}
    total_count = await db.scalar(
        select(func.count(Transaction.id)).where(*_legacy_scope(current_user))
    )
    zero = (Decimal("0"), Decimal("0"))
    income, avg_income = sums.get(TransactionTypeModel.INCOME, zero)
    expense, avg_expense = sums.get(TransactionTypeModel.EXPENSE, zero)
    return TransactionStatistics(
        total_transactions=total_count or 0,
        total_income=income,
        total_expense=expense,
        current_balance=income - expense,
        average_expense=avg_expense,
        average_income=avg_income,
    )


@router.get(
    "/chart", response_model=list[TransactionChartItem], deprecated=True, description=_LEGACY
)
async def get_chart(
    months: int = Query(default=6, ge=1, le=24),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> list[TransactionChartItem]:
    year_expr = func.extract("year", Transaction.transaction_date)
    month_expr = func.extract("month", Transaction.transaction_date)
    rows = await db.execute(
        select(
            year_expr.label("year"),
            month_expr.label("month"),
            Transaction.transaction_type,
            func.sum(Transaction.amount).label("total"),
        )
        .where(
            *_legacy_scope(current_user),
            Transaction.transaction_type.in_(
                [TransactionTypeModel.INCOME, TransactionTypeModel.EXPENSE]
            ),
        )
        .group_by(year_expr, month_expr, Transaction.transaction_type)
    )
    buckets: dict[tuple[int, int], dict[str, Decimal]] = {}
    for row in rows:
        bucket = buckets.setdefault(
            (int(row.year), int(row.month)), {"income": Decimal("0"), "expense": Decimal("0")}
        )
        key = "income" if row.transaction_type == TransactionTypeModel.INCOME else "expense"
        bucket[key] = Decimal(row.total)
    return [
        TransactionChartItem(label=f"{y}-{m:02d}", **buckets[(y, m)])
        for y, m in sorted(buckets)[-months:]
    ]


@router.get(
    "/categories",
    response_model=list[CategoryResponse],
    deprecated=True,
    description="DEPRECATED alias of GET /categories.",
)
async def list_categories_legacy(
    current_user: User = Depends(get_current_active_user), db: AsyncSession = Depends(get_db)
) -> list[CategoryResponse]:
    return [CategoryResponse.from_model(c) for c in await CategoryService(db).list(current_user.id)]


@router.post(
    "/categories",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
    deprecated=True,
    description="DEPRECATED alias of POST /categories.",
)
async def create_category_legacy(
    payload: CategoryCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> CategoryResponse:
    category = await CategoryService(db).create(payload, current_user.id)
    await db.commit()
    return CategoryResponse.from_model(category)


# ---------------------------------------------------------------- single transaction
@router.get("/{transaction_id}", response_model=TransactionDetail, responses=_ERRORS)
async def get_transaction(
    transaction_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> TransactionDetail:
    transaction = await TransactionService(db).get(transaction_id, current_user.id)
    return await _to_detail(db, transaction)


async def _update(
    transaction_id: int, payload: TransactionUpdate, user: User, db: AsyncSession
) -> Transaction:
    transaction = await TransactionService(db).update(transaction_id, payload, user)
    await db.commit()
    return transaction


@router.patch("/{transaction_id}", response_model=TransactionResponse, responses=_ERRORS)
async def patch_transaction(
    transaction_id: int,
    payload: TransactionUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Transaction:
    """Partial update: omitted fields stay unchanged."""

    return await _update(transaction_id, payload, current_user, db)


@router.put(
    "/{transaction_id}",
    response_model=TransactionResponse,
    responses=_ERRORS,
    description="Same partial-update semantics as PATCH (kept for existing clients).",
)
async def update_transaction(
    transaction_id: int,
    payload: TransactionUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Transaction:
    return await _update(transaction_id, payload, current_user, db)


@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT, responses=_ERRORS)
async def delete_transaction(
    transaction_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await TransactionService(db).delete(transaction_id, current_user.id)
    await db.commit()
