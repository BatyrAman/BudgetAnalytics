"""Bank statement import: upload -> preview -> commit (or cancel).

Only exported statement FILES are accepted (CSV, XLSX). No bank APIs are
used and no bank credentials are ever requested or stored.
"""

from typing import Any

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import PaginationParams, get_current_active_user, get_db, limit_per_user
from app.core.config import settings
from app.core.errors import ErrorResponse
from app.core.rate_limit import IMPORT_PER_USER
from app.models.user import User
from app.schemas.imports import (
    CommitRequest,
    CommitResponse,
    ImportHistoryPage,
    ImportPreviewResponse,
    ImportRowOut,
    ImportRowsPage,
    ImportSummary,
    SupportedBankProfile,
)
from app.services.imports.parsers import PARSERS
from app.services.imports.service import ImportService

router = APIRouter(prefix="/imports", tags=["Statement import"])

PREVIEW_ROWS = 100
_ERRORS: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorResponse},
    401: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    413: {"model": ErrorResponse},
    415: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}


async def read_limited(file: UploadFile) -> bytes:
    """Reads at most IMPORT_MAX_FILE_BYTES + 1 bytes (so oversize is detected
    without loading an arbitrarily large upload into memory)."""

    return await file.read(settings.IMPORT_MAX_FILE_BYTES + 1)


@router.get("/banks", response_model=list[SupportedBankProfile])
async def supported_banks(
    _user: User = Depends(get_current_active_user),
) -> list[SupportedBankProfile]:
    return [
        SupportedBankProfile(
            code=code, name=cls.profile.name, formats=["csv", "xlsx"], verified=cls.profile.verified
        )
        for code, cls in PARSERS.items()
    ]


@router.post(
    "/{bank}/preview",
    response_model=ImportPreviewResponse,
    status_code=status.HTTP_201_CREATED,
    responses=_ERRORS,
    dependencies=[Depends(limit_per_user(IMPORT_PER_USER))],
)
async def preview_import(
    bank: str,
    file: UploadFile = File(description="Statement exported from the bank app (.csv or .xlsx)"),
    account_id: int | None = Form(default=None, description="Own account to link the rows to"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ImportPreviewResponse:
    """Validates and parses the file; nothing is added to transactions yet.
    Every row gets a status (valid, invalid with a reason, duplicate,
    possible_duplicate). Failed uploads appear in the import history."""

    service = ImportService(db, settings)
    record = await service.preview(
        current_user, bank, file.filename, await read_limited(file), account_id
    )
    await db.commit()
    rows, _ = await service.rows(record.id, current_user.id, None, PREVIEW_ROWS, 0)
    return ImportPreviewResponse(
        import_=ImportSummary.model_validate(record),
        rows=[ImportRowOut.model_validate(r) for r in rows],
        verified_parser=PARSERS[record.bank].profile.verified,
    )


@router.get("", response_model=ImportHistoryPage, responses={401: _ERRORS[401]})
async def import_history(
    pagination: PaginationParams = Depends(),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ImportHistoryPage:
    items, total = await ImportService(db, settings).history(
        current_user.id, pagination.limit, pagination.offset
    )
    await db.commit()
    return ImportHistoryPage(
        items=[ImportSummary.model_validate(i) for i in items],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.get("/{import_id}", response_model=ImportSummary, responses=_ERRORS)
async def get_import(
    import_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ImportSummary:
    return ImportSummary.model_validate(
        await ImportService(db, settings).get(import_id, current_user.id)
    )


@router.get("/{import_id}/rows", response_model=ImportRowsPage, responses=_ERRORS)
async def get_import_rows(
    import_id: int,
    row_status: str | None = Query(
        default=None,
        alias="status",
        pattern="^(valid|invalid|duplicate|possible_duplicate|imported|skipped)$",
    ),
    pagination: PaginationParams = Depends(),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ImportRowsPage:
    rows, total = await ImportService(db, settings).rows(
        import_id, current_user.id, row_status, pagination.limit, pagination.offset
    )
    return ImportRowsPage(
        items=[ImportRowOut.model_validate(r) for r in rows],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.post("/{import_id}/commit", response_model=CommitResponse, responses=_ERRORS)
async def commit_import(
    import_id: int,
    payload: CommitRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> CommitResponse:
    """Creates transactions from valid rows (minus ``exclude_rows``).
    Duplicates are never imported; possible duplicates only on request.
    A preview can be committed once (409 afterwards)."""

    service = ImportService(db, settings)
    result = await service.commit(
        import_id, current_user, set(payload.exclude_rows), payload.include_possible_duplicates
    )
    await db.commit()
    record = await service.get(import_id, current_user.id)
    return CommitResponse(
        import_=ImportSummary.model_validate(record),
        imported=result.imported,
        skipped=result.skipped,
    )


@router.delete("/{import_id}", status_code=status.HTTP_204_NO_CONTENT, responses=_ERRORS)
async def cancel_import(
    import_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Cancels a preview and deletes its stored rows."""

    await ImportService(db, settings).cancel(import_id, current_user.id)
    await db.commit()
