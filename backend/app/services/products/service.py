from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.bank_product import BankProduct
from app.models.enums import ProductType
from app.repositories.banks import BankRepository
from app.services.products.sources import ProductSource

logger = logging.getLogger(__name__)

STALE_AFTER = timedelta(days=7)


@dataclass(frozen=True, slots=True)
class UpdateStats:
    source: str
    upserted: int
    deactivated: int


class BankProductService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.banks = BankRepository(session)

    async def search(
        self,
        product_type: ProductType | None = None,
        amount: Decimal | None = None,
        term_months: int | None = None,
        limit: int = 50,
    ) -> list[BankProduct]:
        stmt = select(BankProduct).options(joinedload(BankProduct.bank)).where(BankProduct.is_active.is_(True))
        if product_type is not None:
            stmt = stmt.where(BankProduct.product_type == product_type)
        if amount is not None:
            stmt = stmt.where(
                or_(BankProduct.amount_min.is_(None), BankProduct.amount_min <= amount),
                or_(BankProduct.amount_max.is_(None), BankProduct.amount_max >= amount),
            )
        if term_months is not None:
            stmt = stmt.where(
                or_(BankProduct.term_min.is_(None), BankProduct.term_min <= term_months),
                or_(BankProduct.term_max.is_(None), BankProduct.term_max >= term_months),
            )
        # Для депозитов выгоднее высокая ставка, для кредитов — низкая ГЭСВ.
        if product_type is ProductType.DEPOSIT:
            stmt = stmt.order_by(BankProduct.rate_max.desc(), BankProduct.id)
        else:
            stmt = stmt.order_by(BankProduct.gesv.asc().nulls_last(), BankProduct.rate_min, BankProduct.id)
        return list((await self.session.scalars(stmt.limit(limit))).all())

    @staticmethod
    def is_stale(product: BankProduct, now: datetime | None = None) -> bool:
        return (now or datetime.now(timezone.utc)) - product.fetched_at > STALE_AFTER

    async def update_from_source(self, source: ProductSource) -> UpdateStats:
        """
        Идемпотентное обновление: UPSERT по (bank_id, product_type,
        external_key). Продукты этого источника, которых нет в новой
        выгрузке, деактивируются (не удаляются — история остаётся).
        Если источник упал, ничего не меняется.
        """

        offers = await source.fetch()
        seen: dict[int, set[tuple[str, str]]] = {}
        for offer in offers:
            bank = await self.banks.get_or_create(offer.bank_name)
            seen.setdefault(bank.id, set()).add((offer.product_type.value, offer.external_key))
            values = {
                "bank_id": bank.id,
                "product_type": offer.product_type,
                "external_key": offer.external_key,
                "name": offer.name,
                "rate_min": offer.rate_min,
                "rate_max": offer.rate_max,
                "gesv": offer.gesv,
                "term_min": offer.term_min,
                "term_max": offer.term_max,
                "amount_min": offer.amount_min,
                "amount_max": offer.amount_max,
                "currency": offer.currency,
                "conditions": offer.conditions,
                "source": source.name,
                "source_url": offer.source_url,
                "fetched_at": offer.fetched_at or datetime.now(timezone.utc),
                "is_active": True,
            }
            stmt = insert(BankProduct).values(**values)
            await self.session.execute(
                stmt.on_conflict_do_update(
                    constraint="uq_bank_products_key",
                    set_={**{k: stmt.excluded[k] for k in values if k not in ("bank_id", "product_type", "external_key")},
                          "updated_at": datetime.now(timezone.utc)},
                )
            )

        active = select(BankProduct.id, BankProduct.bank_id, BankProduct.product_type, BankProduct.external_key).where(
            BankProduct.source == source.name, BankProduct.is_active.is_(True)
        )
        stale_ids = [
            row.id
            for row in (await self.session.execute(active)).all()
            if (row.product_type.value, row.external_key) not in seen.get(row.bank_id, set())
        ]
        if stale_ids:
            await self.session.execute(
                update(BankProduct).where(BankProduct.id.in_(stale_ids)).values(is_active=False)
            )
        await self.session.commit()
        logger.info("Bank products from %s: upserted=%s deactivated=%s", source.name, len(offers), len(stale_ids))
        return UpdateStats(source.name, len(offers), len(stale_ids))
