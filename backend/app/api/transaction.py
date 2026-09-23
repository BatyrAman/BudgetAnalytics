from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, DbSession, Pagination
from app.core.errors import ERROR_RESPONSES
from app.models.enums import CategoryKind, TransactionType
from app.repositories.transactions import TransactionFilters
from app.schemas.category import CategoryCreate, CategoryResponse, CategoryUpdate
from app.schemas.transaction import (
    TransactionChartItem,
    TransactionCreate,
    TransactionDetail,
    TransactionListResponse,
    TransactionResponse,
    TransactionStatistics,
    TransactionUpdate,
)
from app.services.categories import CategoryService
from app.services.transactions import TransactionService

router = APIRouter(prefix="/transactions", tags=["Transactions"], responses=ERROR_RESPONSES)


@router.post("", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED)
async def create_transaction(payload: TransactionCreate, user: CurrentUser, db: DbSession):
    return await TransactionService(db).create(user.id, payload)


@router.get("", response_model=TransactionListResponse)
async def list_transactions(
    user: CurrentUser,
    db: DbSession,
    pagination: Pagination,
    start_date: datetime | None = Query(default=None),
    end_date: datetime | None = Query(default=None),
    category_id: int | None = Query(default=None),
    bank_id: int | None = Query(default=None),
    card_id: int | None = Query(default=None),
    transaction_type: TransactionType | None = Query(default=None),
    min_amount: Decimal | None = Query(default=None),
    max_amount: Decimal | None = Query(default=None),
) -> TransactionListResponse:
    filters = TransactionFilters(
        start_date=start_date,
        end_date=end_date,
        category_id=category_id,
        bank_id=bank_id,
        card_id=card_id,
        transaction_type=transaction_type,
        min_amount=min_amount,
        max_amount=max_amount,
    )
    items, total = await TransactionService(db).search(user.id, filters, pagination.limit, pagination.offset)
    return TransactionListResponse(items=items, total=total)


@router.get("/statistics", response_model=TransactionStatistics)
async def get_statistics(user: CurrentUser, db: DbSession):
    return await TransactionService(db).statistics(user.id)


@router.get("/chart", response_model=list[TransactionChartItem])
async def get_chart(user: CurrentUser, db: DbSession, months: int = Query(default=6, ge=1, le=24)):
    """Доходы/расходы по месяцам за последние `months` месяцев с операциями."""

    return await TransactionService(db).chart(user.id, months)


@router.get("/categories", response_model=list[CategoryResponse])
async def list_categories(user: CurrentUser, db: DbSession, kind: CategoryKind | None = None):
    """Системные категории + собственные категории пользователя."""

    return await CategoryService(db).list(user.id, kind)


@router.post("/categories", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_category(payload: CategoryCreate, user: CurrentUser, db: DbSession):
    """Создаёт пользовательскую категорию (видна только владельцу)."""

    return await CategoryService(db).create(user.id, payload)


@router.put("/categories/{category_id}", response_model=CategoryResponse)
async def update_category(category_id: int, payload: CategoryUpdate, user: CurrentUser, db: DbSession):
    return await CategoryService(db).update(category_id, user.id, payload)


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(category_id: int, user: CurrentUser, db: DbSession) -> None:
    await CategoryService(db).delete(category_id, user.id)


@router.get("/{transaction_id}", response_model=TransactionDetail)
async def get_transaction(transaction_id: int, user: CurrentUser, db: DbSession):
    return await TransactionService(db).get_detail(transaction_id, user.id)


@router.put("/{transaction_id}", response_model=TransactionResponse)
async def update_transaction(transaction_id: int, payload: TransactionUpdate, user: CurrentUser, db: DbSession):
    return await TransactionService(db).update(transaction_id, user.id, payload)


@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transaction(transaction_id: int, user: CurrentUser, db: DbSession) -> None:
    await TransactionService(db).delete(transaction_id, user.id)
