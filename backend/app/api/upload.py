from __future__ import annotations

from fastapi import APIRouter, Depends, File, Query, UploadFile, status

from app.api.deps import CurrentUser, DbSession, Pagination
from app.core.config import settings
from app.core.errors import ERROR_RESPONSES, AppError
from app.core.rate_limit import rate_limit
from app.schemas.bank import BankListResponse, SupportedBank
from app.schemas.imports import StatementImportResponse, UploadResult
from app.services.imports.service import StatementImportService
from app.services.parser import PARSERS

router = APIRouter(tags=["Upload"], responses=ERROR_RESPONSES)

_CHUNK = 64 * 1024


async def _read_limited(file: UploadFile) -> bytes:
    limit = settings.max_upload_size_bytes
    data = bytearray()
    while chunk := await file.read(_CHUNK):
        data.extend(chunk)
        if len(data) > limit:
            raise AppError(
                f"File is larger than {settings.MAX_UPLOAD_SIZE_MB} MB",
                code="FILE_TOO_LARGE",
                status_code=413,
            )
    return bytes(data)


@router.get("/upload/banks/supported", response_model=list[SupportedBank])
async def get_supported_banks() -> list[SupportedBank]:
    """Банки, для которых реализован парсер выписок."""

    return [
        SupportedBank(name=parser.bank_name, parser=slug, supported=True)
        for slug, parser in PARSERS.items()
    ]


@router.get("/upload/banks", response_model=BankListResponse)
async def list_banks(_: CurrentUser, db: DbSession) -> BankListResponse:
    """Справочник банков (общий для всех пользователей)."""

    items = await StatementImportService(db).list_banks()
    return BankListResponse(items=items, total=len(items))


@router.post(
    "/upload/{bank_slug}",
    response_model=UploadResult,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("upload", "UPLOAD_RATE_LIMIT_PER_MINUTE"))],
)
async def upload_statement(
    bank_slug: str,
    user: CurrentUser,
    db: DbSession,
    file: UploadFile = File(...),
    card_id: int | None = Query(default=None, description="Карта, к которой относится выписка"),
) -> UploadResult:
    """
    Импорт CSV-выписки банка: kaspi, halyk, freedom.

    Повторная загрузка той же выписки не создаёт дублей
    (`skipped_duplicates`). Строки, которые не удалось разобрать,
    перечислены в `errors`; статус тогда `partial`.
    """

    content = await _read_limited(file)
    outcome = await StatementImportService(db).import_statement(
        user, bank_slug, file.filename or "", content, card_id
    )
    record = outcome.record
    message = "No transactions found in the file" if record.rows_total == 0 else None
    return UploadResult(
        import_id=record.id,
        status=record.status,
        bank=outcome.bank_name,
        imported=record.rows_imported,
        skipped_duplicates=record.rows_skipped,
        failed=record.rows_failed,
        rows_total=record.rows_total,
        total_income=outcome.total_income,
        total_expense=outcome.total_expense,
        errors=record.errors,
        message=message,
    )


@router.get("/imports", response_model=list[StatementImportResponse], tags=["Imports"])
async def list_imports(user: CurrentUser, db: DbSession, pagination: Pagination):
    return await StatementImportService(db).list_imports(user.id, pagination.limit, pagination.offset)


@router.get("/imports/{import_id}", response_model=StatementImportResponse, tags=["Imports"])
async def get_import(import_id: int, user: CurrentUser, db: DbSession):
    return await StatementImportService(db).get_import(import_id, user.id)
