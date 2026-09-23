from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.core.errors import ERROR_RESPONSES
from app.models.enums import ProductType
from app.schemas.products import BankProductResponse
from app.services.products.service import BankProductService

router = APIRouter(prefix="/products", tags=["Bank products"], responses=ERROR_RESPONSES)


@router.get("", response_model=list[BankProductResponse])
async def search_products(
    _: CurrentUser,
    db: DbSession,
    type: ProductType | None = Query(default=None),
    amount: Decimal | None = Query(default=None, gt=0),
    term: int | None = Query(default=None, ge=1, le=600, description="Срок, месяцев"),
    limit: int = Query(default=50, ge=1, le=200),
):
    """
    Предложения банков из базы ставок. У каждой записи — источник,
    ссылка и дата актуальности; is_stale=true, если данные старше 7 дней.
    """

    service = BankProductService(db)
    products = await service.search(type, amount, term, limit)
    return [
        BankProductResponse(
            id=p.id,
            bank_id=p.bank_id,
            bank_name=p.bank.name,
            product_type=p.product_type,
            name=p.name,
            rate_min=p.rate_min,
            rate_max=p.rate_max,
            gesv=p.gesv,
            term_min=p.term_min,
            term_max=p.term_max,
            amount_min=p.amount_min,
            amount_max=p.amount_max,
            currency=p.currency,
            conditions=p.conditions,
            source=p.source,
            source_url=p.source_url,
            fetched_at=p.fetched_at,
            updated_at=p.updated_at,
            is_stale=service.is_stale(p),
        )
        for p in products
    ]
