from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, NotFoundError
from app.models.card import Card
from app.models.enums import CardType
from app.repositories.banks import BankRepository
from app.repositories.cards import CardRepository
from app.schemas.card import CardCreate, CardResponse, CardUpdate


def to_response(card: Card) -> CardResponse:
    return CardResponse(
        id=card.id,
        bank_id=card.bank_id,
        bank_name=card.bank.name,
        last4=card.last4,
        card_type=card.card_type,
        credit_limit=card.credit_limit,
        currency=card.currency,
        nickname=card.nickname,
        is_active=card.is_active,
        created_at=card.created_at,
    )


class CardService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = CardRepository(session)
        self.banks = BankRepository(session)

    async def list(self, user_id: int) -> list[CardResponse]:
        return [to_response(c) for c in await self.repo.list_for_user(user_id)]

    async def get(self, card_id: int, user_id: int) -> CardResponse:
        card = await self.repo.get_with_bank(card_id, user_id)
        if card is None:
            raise NotFoundError("Card not found", code="CARD_NOT_FOUND")
        return to_response(card)

    async def create(self, user_id: int, payload: CardCreate) -> CardResponse:
        if await self.banks.get(payload.bank_id) is None:
            raise AppError("Bank not found", code="BANK_NOT_FOUND")
        if payload.credit_limit is not None and payload.card_type is not CardType.CREDIT:
            raise AppError("credit_limit is only allowed for credit cards", code="VALIDATION_ERROR", status_code=422)
        card = self.repo.add(Card(user_id=user_id, **payload.model_dump()))
        await self.session.commit()
        return await self.get(card.id, user_id)

    async def update(self, card_id: int, user_id: int, payload: CardUpdate) -> CardResponse:
        card = await self.repo.get_owned(card_id, user_id)
        if card is None:
            raise NotFoundError("Card not found", code="CARD_NOT_FOUND")
        for field, value in payload.model_dump(exclude_unset=True).items():
            if field in ("card_type", "is_active") and value is None:
                continue
            setattr(card, field, value)
        await self.session.commit()
        self.session.expire(card)
        return await self.get(card_id, user_id)

    async def delete(self, card_id: int, user_id: int) -> None:
        card = await self.repo.get_owned(card_id, user_id)
        if card is None:
            raise NotFoundError("Card not found", code="CARD_NOT_FOUND")
        await self.repo.delete(card)
        await self.session.commit()
