from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.currency import Currency
from app.services.finance.money import CurrencySpec


class CurrencyRepository:
    """Global reference data (not user-scoped)."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, code: str) -> Currency | None:
        return await self.db.get(Currency, code)

    async def list_active(self) -> list[Currency]:
        result = await self.db.scalars(
            select(Currency).where(Currency.is_active.is_(True)).order_by(Currency.code)
        )
        return list(result)

    async def get_spec(self, code: str) -> CurrencySpec | None:
        currency = await self.get(code)
        if currency is None:
            return None
        return CurrencySpec(currency.code, currency.minor_units)
