"""
Источники ставок банковских продуктов.

Источник возвращает нормализованные ProductOffer. Сбор данных
(скрапинг сайтов банков, мониторинг КФГД, будущие Open Banking API)
выполняется ТОЛЬКО в фоновой задаче, никогда в API-запросе.

В репозитории нет захардкоженных ставок: JsonFileProductSource
читает файл, который готовит оператор/скрапер, а сетевые источники
добавляются реализацией протокола ProductSource.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Protocol

from app.models.enums import ProductType
from app.services.finance.money import to_decimal


@dataclass(frozen=True, slots=True)
class ProductOffer:
    bank_name: str
    product_type: ProductType
    external_key: str
    name: str
    rate_min: Decimal
    rate_max: Decimal
    source_url: str
    gesv: Decimal | None = None
    term_min: int | None = None
    term_max: int | None = None
    amount_min: Decimal | None = None
    amount_max: Decimal | None = None
    currency: str = "KZT"
    conditions: dict = field(default_factory=dict)
    fetched_at: datetime | None = None


class ProductSource(Protocol):
    name: str

    async def fetch(self) -> list[ProductOffer]: ...


def _dec(value) -> Decimal | None:
    return None if value is None else to_decimal(str(value))


class JsonFileProductSource:
    """
    [{"bank": "...", "product_type": "deposit", "external_key": "...",
      "name": "...", "rate_min": "14.5", "rate_max": "16.0", "gesv": "16.8",
      "term_min": 3, "term_max": 24, "amount_min": "10000", "amount_max": null,
      "conditions": {...}, "source_url": "https://...", "fetched_at": "2026-09-01T00:00:00Z"}]
    """

    def __init__(self, path: str | Path, name: str = "curated-file") -> None:
        self.path = Path(path)
        self.name = name

    async def fetch(self) -> list[ProductOffer]:
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        offers = []
        for item in raw:
            fetched = item.get("fetched_at")
            offers.append(
                ProductOffer(
                    bank_name=item["bank"],
                    product_type=ProductType(item["product_type"]),
                    external_key=str(item["external_key"]),
                    name=item["name"],
                    rate_min=_dec(item["rate_min"]),
                    rate_max=_dec(item["rate_max"]),
                    gesv=_dec(item.get("gesv")),
                    term_min=item.get("term_min"),
                    term_max=item.get("term_max"),
                    amount_min=_dec(item.get("amount_min")),
                    amount_max=_dec(item.get("amount_max")),
                    currency=item.get("currency", "KZT"),
                    conditions=item.get("conditions") or {},
                    source_url=item["source_url"],
                    fetched_at=datetime.fromisoformat(fetched) if fetched else datetime.now(timezone.utc),
                )
            )
        return offers
