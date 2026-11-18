from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import Page


class SupportedBankProfile(BaseModel):
    code: str
    name: str
    formats: list[str]
    verified: bool = Field(
        description="false = column layout assumed, not yet confirmed with real bank exports"
    )


class ImportSummary(BaseModel):
    id: int
    bank: str
    parser_version: str
    file_name: str
    file_format: str
    file_size: int
    status: str = Field(description="preview | committed | failed | cancelled | expired")
    account_id: int | None
    total_rows: int
    valid_rows: int
    invalid_rows: int
    duplicate_rows: int
    imported_rows: int
    period_start: date | None
    period_end: date | None
    error_code: str | None
    error_message: str | None
    created_at: datetime
    committed_at: datetime | None
    expires_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class ImportRowOut(BaseModel):
    row_number: int = Field(description="Line/row number in the uploaded file")
    status: str = Field(
        description="valid | invalid | duplicate | possible_duplicate | imported | skipped"
    )
    transaction_date: datetime | None
    amount: Decimal | None
    currency_code: str | None
    transaction_type: str | None
    type_source: str | None = Field(description="keyword | sign — how the type was detected")
    description: str | None
    merchant: str | None
    category_hint: str | None
    error_code: str | None
    error_message: str | None
    transaction_id: int | None

    model_config = ConfigDict(from_attributes=True)


class ImportPreviewResponse(BaseModel):
    import_: ImportSummary = Field(alias="import")
    rows: list[ImportRowOut] = Field(description="First rows; page with GET /imports/{id}/rows")
    verified_parser: bool

    model_config = ConfigDict(populate_by_name=True)


class ImportRowsPage(Page[ImportRowOut]):
    pass


class ImportHistoryPage(Page[ImportSummary]):
    pass


class CommitRequest(BaseModel):
    exclude_rows: list[int] = Field(default_factory=list, max_length=100_000)
    include_possible_duplicates: bool = False


class CommitResponse(BaseModel):
    import_: ImportSummary = Field(alias="import")
    imported: int
    skipped: int

    model_config = ConfigDict(populate_by_name=True)
