from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import ImportStatus
from app.schemas.common import MoneyDecimal


class ImportError_(BaseModel):
    row: int | None
    message: str


class StatementImportResponse(BaseModel):
    id: int
    bank_id: int
    card_id: int | None
    parser: str
    file_name: str
    status: ImportStatus
    rows_total: int
    rows_imported: int
    rows_skipped: int
    rows_failed: int
    errors: list[ImportError_]
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UploadResult(BaseModel):
    """Ответ POST /upload/{bank}. Поля imported/bank/total_* сохранены с v0.1."""

    import_id: int
    status: ImportStatus
    bank: str
    imported: int
    skipped_duplicates: int
    failed: int
    rows_total: int
    total_income: MoneyDecimal
    total_expense: MoneyDecimal
    errors: list[ImportError_]
    message: str | None = None
