from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DbSession
from app.core.errors import ERROR_RESPONSES
from app.schemas.card import CardCreate, CardResponse, CardUpdate
from app.services.cards import CardService

router = APIRouter(prefix="/cards", tags=["Cards"], responses=ERROR_RESPONSES)


@router.get("", response_model=list[CardResponse])
async def list_cards(user: CurrentUser, db: DbSession):
    return await CardService(db).list(user.id)


@router.post("", response_model=CardResponse, status_code=status.HTTP_201_CREATED)
async def create_card(payload: CardCreate, user: CurrentUser, db: DbSession):
    """
    «Подключение карты» на MVP: банк + последние 4 цифры + тип.
    Полный номер, CVV и срок действия не принимаются и не хранятся.
    """

    return await CardService(db).create(user.id, payload)


@router.get("/{card_id}", response_model=CardResponse)
async def get_card(card_id: int, user: CurrentUser, db: DbSession):
    return await CardService(db).get(card_id, user.id)


@router.put("/{card_id}", response_model=CardResponse)
async def update_card(card_id: int, payload: CardUpdate, user: CurrentUser, db: DbSession):
    return await CardService(db).update(card_id, user.id, payload)


@router.delete("/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_card(card_id: int, user: CurrentUser, db: DbSession) -> None:
    await CardService(db).delete(card_id, user.id)
