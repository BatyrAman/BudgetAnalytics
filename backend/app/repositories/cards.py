from __future__ import annotations

from sqlalchemy.orm import joinedload

from app.models.card import Card
from app.repositories.base import OwnedRepository


class CardRepository(OwnedRepository[Card]):
    model = Card

    async def list_for_user(self, user_id: int) -> list[Card]:
        return await self.list_owned(
            user_id, order_by=(Card.created_at.desc(), Card.id.desc()), options=(joinedload(Card.bank),)
        )

    async def get_with_bank(self, card_id: int, user_id: int) -> Card | None:
        return await self.get_owned(card_id, user_id, joinedload(Card.bank))
