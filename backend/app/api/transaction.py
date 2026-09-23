from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import PaginationParams, get_current_active_user, get_db
from app.models.bank import Bank
from app.models.category import Category
from app.models.enums import TransactionType as TransactionTypeModel
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.category import CategoryCreate, CategoryResponse
from app.schemas.transaction import (
    TransactionChartItem,
    TransactionCreate,
    TransactionDetail,
    TransactionFilter,
    TransactionListResponse,
    TransactionResponse,
    TransactionStatistics,
)
from app.schemas.transaction import TransactionType as TransactionTypeSchema
from app.schemas.transaction import TransactionUpdate

router = APIRouter(prefix="/transactions", tags=["Transactions"])


async def _get_owned_transaction(
    db: AsyncSession,
    transaction_id: int,
    user_id: int,
) -> Transaction:

    transaction = await db.scalar(
        select(Transaction).where(
            Transaction.id == transaction_id,
            Transaction.user_id == user_id,
        )
    )

    if transaction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found",
        )

    return transaction


async def _to_detail(db: AsyncSession, transaction: Transaction) -> TransactionDetail:

    category = await db.get(Category, transaction.category_id)
    bank = await db.get(Bank, transaction.bank_id)

    return TransactionDetail(
        **TransactionResponse.model_validate(transaction).model_dump(),
        category_name=category.name if category else "—",
        bank_name=bank.name if bank else "—",
    )


@router.post(
    "",
    response_model=TransactionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_transaction(
    payload: TransactionCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Transaction:

    category = await db.get(Category, payload.category_id)
    if category is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Category not found",
        )

    bank = await db.get(Bank, payload.bank_id)
    if bank is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bank not found",
        )

    transaction = Transaction(
        amount=payload.amount,
        description=payload.description,
        transaction_type=TransactionTypeModel(payload.transaction_type.value),
        transaction_date=payload.transaction_date,
        category_id=payload.category_id,
        bank_id=payload.bank_id,
        user_id=current_user.id,
    )

    db.add(transaction)
    await db.commit()
    await db.refresh(transaction)

    return transaction


@router.get(
    "",
    response_model=TransactionListResponse,
)
async def list_transactions(
    pagination: PaginationParams = Depends(),
    start_date: datetime | None = Query(default=None),
    end_date: datetime | None = Query(default=None),
    category_id: int | None = Query(default=None),
    bank_id: int | None = Query(default=None),
    transaction_type: TransactionTypeSchema | None = Query(default=None),
    min_amount: Decimal | None = Query(default=None),
    max_amount: Decimal | None = Query(default=None),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> TransactionListResponse:

    filters = TransactionFilter(
        start_date=start_date,
        end_date=end_date,
        category_id=category_id,
        bank_id=bank_id,
        transaction_type=transaction_type,
        min_amount=min_amount,
        max_amount=max_amount,
    )

    conditions = [Transaction.user_id == current_user.id]

    if filters.start_date is not None:
        conditions.append(Transaction.transaction_date >= filters.start_date)

    if filters.end_date is not None:
        conditions.append(Transaction.transaction_date <= filters.end_date)

    if filters.category_id is not None:
        conditions.append(Transaction.category_id == filters.category_id)

    if filters.bank_id is not None:
        conditions.append(Transaction.bank_id == filters.bank_id)

    if filters.transaction_type is not None:
        conditions.append(
            Transaction.transaction_type
            == TransactionTypeModel(filters.transaction_type.value)
        )

    if filters.min_amount is not None:
        conditions.append(Transaction.amount >= filters.min_amount)

    if filters.max_amount is not None:
        conditions.append(Transaction.amount <= filters.max_amount)

    total = await db.scalar(
        select(func.count(Transaction.id)).where(*conditions)
    )

    result = await db.execute(
        select(Transaction)
        .where(*conditions)
        .order_by(Transaction.transaction_date.desc())
        .limit(pagination.limit)
        .offset(pagination.offset)
    )

    items = result.scalars().all()

    return TransactionListResponse(items=items, total=total or 0)


@router.get(
    "/statistics",
    response_model=TransactionStatistics,
)
async def get_statistics(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> TransactionStatistics:

    income = await db.scalar(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.user_id == current_user.id,
            Transaction.transaction_type == TransactionTypeModel.INCOME,
        )
    )

    expense = await db.scalar(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.user_id == current_user.id,
            Transaction.transaction_type == TransactionTypeModel.EXPENSE,
        )
    )

    avg_income = await db.scalar(
        select(func.coalesce(func.avg(Transaction.amount), 0)).where(
            Transaction.user_id == current_user.id,
            Transaction.transaction_type == TransactionTypeModel.INCOME,
        )
    )

    avg_expense = await db.scalar(
        select(func.coalesce(func.avg(Transaction.amount), 0)).where(
            Transaction.user_id == current_user.id,
            Transaction.transaction_type == TransactionTypeModel.EXPENSE,
        )
    )

    total_count = await db.scalar(
        select(func.count(Transaction.id)).where(
            Transaction.user_id == current_user.id,
        )
    )

    income = Decimal(income or 0)
    expense = Decimal(expense or 0)

    return TransactionStatistics(
        total_transactions=total_count or 0,
        total_income=income,
        total_expense=expense,
        current_balance=income - expense,
        average_expense=Decimal(avg_expense or 0),
        average_income=Decimal(avg_income or 0),
    )


@router.get(
    "/chart",
    response_model=list[TransactionChartItem],
)
async def get_chart(
    months: int = Query(default=6, ge=1, le=24),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> list[TransactionChartItem]:
    """
    Доходы/расходы по месяцам за последние `months` месяцев.
    """

    year_expr = func.extract("year", Transaction.transaction_date)
    month_expr = func.extract("month", Transaction.transaction_date)

    stmt = (
        select(
            year_expr.label("year"),
            month_expr.label("month"),
            Transaction.transaction_type,
            func.sum(Transaction.amount).label("total"),
        )
        .where(Transaction.user_id == current_user.id)
        .group_by(year_expr, month_expr, Transaction.transaction_type)
        .order_by(year_expr, month_expr)
    )

    result = await db.execute(stmt)
    rows = result.all()

    buckets: dict[tuple[int, int], dict[str, Decimal]] = {}

    for row in rows:
        key = (int(row.year), int(row.month))
        bucket = buckets.setdefault(
            key, {"income": Decimal("0"), "expense": Decimal("0")}
        )

        if row.transaction_type == TransactionTypeModel.INCOME:
            bucket["income"] = Decimal(row.total)
        else:
            bucket["expense"] = Decimal(row.total)

    ordered_keys = sorted(buckets.keys())[-months:]

    return [
        TransactionChartItem(
            label=f"{year}-{month:02d}",
            income=buckets[(year, month)]["income"],
            expense=buckets[(year, month)]["expense"],
        )
        for year, month in ordered_keys
    ]


@router.get(
    "/categories",
    response_model=list[CategoryResponse],
)
async def list_categories(
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
) -> list[Category]:
    """
    Справочник категорий транзакций (общий для всех пользователей).
    """

    result = await db.execute(select(Category).order_by(Category.name))
    return result.scalars().all()


@router.post(
    "/categories",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_category(
    payload: CategoryCreate,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
) -> Category:

    existing = await db.scalar(
        select(Category).where(Category.name == payload.name)
    )

    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Category already exists",
        )

    category = Category(**payload.model_dump())

    db.add(category)
    await db.commit()
    await db.refresh(category)

    return category


@router.get(
    "/{transaction_id}",
    response_model=TransactionDetail,
)
async def get_transaction(
    transaction_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> TransactionDetail:

    transaction = await _get_owned_transaction(db, transaction_id, current_user.id)
    return await _to_detail(db, transaction)


@router.put(
    "/{transaction_id}",
    response_model=TransactionResponse,
)
async def update_transaction(
    transaction_id: int,
    payload: TransactionUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Transaction:

    transaction = await _get_owned_transaction(db, transaction_id, current_user.id)

    updates = payload.model_dump(exclude_unset=True)

    if "transaction_type" in updates and updates["transaction_type"] is not None:
        updates["transaction_type"] = TransactionTypeModel(
            updates["transaction_type"].value
            if hasattr(updates["transaction_type"], "value")
            else updates["transaction_type"]
        )

    for field, value in updates.items():
        setattr(transaction, field, value)

    db.add(transaction)
    await db.commit()
    await db.refresh(transaction)

    return transaction


@router.delete(
    "/{transaction_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_transaction(
    transaction_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> None:

    transaction = await _get_owned_transaction(db, transaction_id, current_user.id)

    await db.delete(transaction)
    await db.commit()
