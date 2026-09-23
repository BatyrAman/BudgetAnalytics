from __future__ import annotations

import tempfile
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_db
from app.models.bank import Bank
from app.models.category import Category
from app.models.enums import TransactionType
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.bank import (
    BankListResponse,
    BankResponse,
    SupportedBank,
)
from app.schemas.transaction import ImportTransaction
from app.services.parser.freedom import FreedomParser
from app.services.parser.halyk import HalykParser
from app.services.parser.kaspi import KaspiParser

router = APIRouter(prefix="/upload", tags=["Upload"])


_PARSERS = {
    "kaspi": KaspiParser,
    "halyk": HalykParser,
    "freedom": FreedomParser,
}


@router.get(
    "/banks/supported",
    response_model=list[SupportedBank],
)
async def get_supported_banks() -> list[SupportedBank]:
    """
    Список банков, для которых реализован парсер CSV-выписок.
    """

    return [
        SupportedBank(name=parser_cls.BANK_NAME, parser=slug, supported=True)
        for slug, parser_cls in _PARSERS.items()
    ]


@router.get(
    "/banks",
    response_model=BankListResponse,
)
async def list_banks(
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
) -> BankListResponse:
    """
    Справочник банков (общий для всех пользователей).
    """

    total = await db.scalar(select(func.count(Bank.id)))
    result = await db.execute(select(Bank).order_by(Bank.name))

    return BankListResponse(items=result.scalars().all(), total=total or 0)


async def _get_or_create_bank(db: AsyncSession, name: str) -> Bank:

    bank = await db.scalar(select(Bank).where(Bank.name == name))

    if bank is not None:
        return bank

    bank = Bank(name=name)
    db.add(bank)
    await db.flush()

    return bank


async def _get_or_create_category(db: AsyncSession, name: str) -> Category:

    category = await db.scalar(select(Category).where(Category.name == name))

    if category is not None:
        return category

    category = Category(name=name)
    db.add(category)
    await db.flush()

    return category


@router.post(
    "/{bank_slug}",
    status_code=status.HTTP_201_CREATED,
)
async def upload_statement(
    bank_slug: str,
    file: UploadFile,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Загружает CSV-выписку выбранного банка и импортирует транзакции
    текущего пользователя.

    `bank_slug` — один из поддерживаемых парсеров: kaspi, halyk, freedom.
    """

    parser_cls = _PARSERS.get(bank_slug.lower())

    if parser_cls is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unsupported bank '{bank_slug}'. "
                f"Supported: {', '.join(_PARSERS)}"
            ),
        )

    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .csv files are supported",
        )

    parser = parser_cls()

    with tempfile.NamedTemporaryFile(
        suffix=".csv", delete=False
    ) as tmp_file:
        content = await file.read()
        tmp_file.write(content)
        tmp_path = Path(tmp_file.name)

    try:
        try:
            parsed_rows: list[ImportTransaction] = await parser.parse(tmp_path)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            )
    finally:
        tmp_path.unlink(missing_ok=True)

    if not parsed_rows:
        return {
            "imported": 0,
            "total_income": "0",
            "total_expense": "0",
            "message": "No transactions found in the file",
        }

    bank = await _get_or_create_bank(db, parser_cls.BANK_NAME)

    total_income = Decimal("0")
    total_expense = Decimal("0")
    imported = 0

    for row in parsed_rows:
        category = await _get_or_create_category(
            db, row.category_name or "Без категории"
        )

        transaction_type = TransactionType(row.transaction_type.value)

        transaction = Transaction(
            amount=row.amount,
            description=row.description,
            transaction_type=transaction_type,
            transaction_date=row.transaction_date,
            category_id=category.id,
            bank_id=bank.id,
            user_id=current_user.id,
        )

        db.add(transaction)
        imported += 1

        if transaction_type == TransactionType.INCOME:
            total_income += row.amount
        else:
            total_expense += row.amount

    await db.commit()

    return {
        "imported": imported,
        "bank": bank.name,
        "total_income": str(total_income),
        "total_expense": str(total_expense),
    }
