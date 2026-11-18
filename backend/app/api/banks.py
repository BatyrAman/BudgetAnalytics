"""Bank reference list (global, read-only).

Needed to create deposits and accounts (``bank_id``). Seeded by migration
``a1c3e5f7b9d2``; banks found in imported statements are added automatically.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_db
from app.models.bank import Bank
from app.models.user import User
from app.schemas.bank import BankResponse

router = APIRouter(prefix="/banks", tags=["Banks"])


@router.get("", response_model=list[BankResponse])
async def list_banks(
    _current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> list[Bank]:
    """All banks, alphabetically; "Другой банк" covers banks not in the list."""

    return list(await db.scalars(select(Bank).order_by(Bank.name)))
