from datetime import datetime

from pydantic import BaseModel

from app.models.enums import ProductType
from app.schemas.common import MoneyDecimal, PercentDecimal


class BankProductResponse(BaseModel):
    id: int
    bank_id: int
    bank_name: str
    product_type: ProductType
    name: str
    rate_min: PercentDecimal
    rate_max: PercentDecimal
    gesv: PercentDecimal | None
    term_min: int | None
    term_max: int | None
    amount_min: MoneyDecimal | None
    amount_max: MoneyDecimal | None
    currency: str
    conditions: dict
    source: str
    source_url: str
    # когда условия проверены у источника / когда запись обновлена у нас
    fetched_at: datetime
    updated_at: datetime
    is_stale: bool
