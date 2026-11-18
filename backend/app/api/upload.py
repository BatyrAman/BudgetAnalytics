"""DEPRECATED one-step upload, kept for existing clients.

Now implemented on the import pipeline (``/imports``): the file is previewed
and, if every row is valid, committed immediately. Any invalid row rejects the
whole upload with "Row N: reason" (previous behaviour). Duplicates are
skipped. Prefer POST /imports/{bank}/preview + /commit.
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_db, limit_per_user
from app.api.imports import read_limited
from app.core.config import settings
from app.core.rate_limit import IMPORT_PER_USER
from app.models.bank import Bank
from app.models.statement_import import StatementImportRow
from app.models.user import User
from app.schemas.bank import BankListResponse, SupportedBank
from app.services.imports.files import FileRejected
from app.services.imports.parsers import PARSERS
from app.services.imports.service import ImportService

router = APIRouter(prefix="/upload", tags=["Upload (deprecated)"], deprecated=True)


@router.get("/banks/supported", response_model=list[SupportedBank])
async def get_supported_banks() -> list[SupportedBank]:
    return [
        SupportedBank(name=cls.profile.name, parser=slug, supported=True)
        for slug, cls in PARSERS.items()
    ]


@router.get("/banks", response_model=BankListResponse)
async def list_banks(
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
) -> BankListResponse:
    """Banks reference list (shared by all users)."""

    total = await db.scalar(select(func.count(Bank.id)))
    result = await db.execute(select(Bank).order_by(Bank.name))
    return BankListResponse(items=result.scalars().all(), total=total or 0)


@router.post(
    "/{bank_slug}",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(limit_per_user(IMPORT_PER_USER))],
)
async def upload_statement(
    bank_slug: str,
    file: UploadFile,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Only .csv files are supported"
        )

    service = ImportService(db, settings)
    try:
        record = await service.preview(
            current_user, bank_slug, file.filename, await read_limited(file)
        )
    except FileRejected as exc:  # legacy contract: generic HTTP error codes
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from None
    if record.invalid_rows:
        first = await db.scalar(
            select(StatementImportRow)
            .where(
                StatementImportRow.import_id == record.id, StatementImportRow.status == "invalid"
            )
            .order_by(StatementImportRow.row_number)
            .limit(1)
        )
        await service.cancel(record.id, current_user.id)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Row {first.row_number}: {first.error_message}",  # type: ignore[union-attr]
        )
    result = await service.commit(record.id, current_user)
    await db.commit()
    return {
        "imported": result.imported,
        "bank": PARSERS[record.bank].profile.name,
        "total_income": str(result.total_income),
        "total_expense": str(result.total_expense),
    }
