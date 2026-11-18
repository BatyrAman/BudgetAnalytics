"""Statement import use cases: preview -> (review) -> commit, plus history.

DEDUPLICATION
* Fingerprint = SHA-256 of bank | instant (UTC) | amount | currency | type |
  normalized description | occurrence. ``occurrence`` numbers identical rows
  within one file (1, 2, ...), so two genuine identical purchases in one
  statement stay two transactions, while re-importing the same file — or an
  overlapping period containing the same rows — yields the same fingerprints
  and is detected. A partial unique index (user_id, import_hash) enforces this
  in the database as well.
* ``possible_duplicate``: a MANUALLY entered transaction (no fingerprint) with
  the same local day, amount, type and currency exists. Such rows are skipped
  unless the commit request includes them.

FAILURES are recorded in the import history with a safe message and code;
the file itself is never stored.
"""

import hashlib
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import ConflictError, NotFoundError
from app.models.bank import Bank
from app.models.category import Category
from app.models.currency import Currency
from app.models.enums import TransactionType, category_allows
from app.models.statement_import import StatementImport, StatementImportRow
from app.models.transaction import Transaction
from app.models.user import User
from app.repositories.account import AccountRepository
from app.repositories.category import CategoryRepository
from app.services.imports.files import FileRejected, UploadedFile, validate_upload
from app.services.imports.normalize import NormalizedRow
from app.services.imports.parsers import BankStatementParser, get_parser

DEFAULT_CATEGORY = "Без категории"
IMPORTABLE = {"valid", "possible_duplicate"}


def fingerprint(bank: str, row: NormalizedRow, occurrence: int) -> str:
    description = re.sub(r"\s+", " ", (row.description or "").lower()).strip()
    key = "|".join(
        [
            bank,
            row.transaction_date.astimezone(UTC).isoformat(),
            f"{row.amount:.2f}",
            row.currency_code,
            row.transaction_type.value,
            description,
            str(occurrence),
        ]
    )
    return hashlib.sha256(key.encode()).hexdigest()


@dataclass(frozen=True)
class CommitResult:
    imported: int
    skipped: int
    total_income: Decimal
    total_expense: Decimal


class ImportService:
    def __init__(self, db: AsyncSession, settings: Settings) -> None:
        self.db = db
        self.settings = settings

    # ------------------------------------------------------------ history
    async def get(self, import_id: int, user_id: int) -> StatementImport:
        record = await self.db.scalar(
            select(StatementImport).where(
                StatementImport.id == import_id, StatementImport.user_id == user_id
            )
        )
        if record is None:
            raise NotFoundError("Import not found")
        return record

    async def history(
        self, user_id: int, limit: int, offset: int
    ) -> tuple[list[StatementImport], int]:
        await self.expire_previews(user_id)
        base = select(StatementImport).where(StatementImport.user_id == user_id)
        total = await self.db.scalar(select(func.count()).select_from(base.subquery()))
        rows = await self.db.scalars(
            base.order_by(StatementImport.created_at.desc(), StatementImport.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(rows), int(total or 0)

    async def rows(
        self, import_id: int, user_id: int, status: str | None, limit: int, offset: int
    ) -> tuple[list[StatementImportRow], int]:
        await self.get(import_id, user_id)
        base = select(StatementImportRow).where(StatementImportRow.import_id == import_id)
        if status:
            base = base.where(StatementImportRow.status == status)
        total = await self.db.scalar(select(func.count()).select_from(base.subquery()))
        rows = await self.db.scalars(
            base.order_by(StatementImportRow.row_number).limit(limit).offset(offset)
        )
        return list(rows), int(total or 0)

    async def expire_previews(self, user_id: int) -> None:
        """Previews past their TTL become ``expired`` and lose their rows
        (descriptions are not kept longer than needed)."""

        now = datetime.now(UTC)
        expired_ids = list(
            await self.db.scalars(
                select(StatementImport.id).where(
                    StatementImport.user_id == user_id,
                    StatementImport.status == "preview",
                    StatementImport.expires_at < now,
                )
            )
        )
        if expired_ids:
            await self.db.execute(
                delete(StatementImportRow).where(StatementImportRow.import_id.in_(expired_ids))
            )
            await self.db.execute(
                update(StatementImport)
                .where(StatementImport.id.in_(expired_ids))
                .values(status="expired")
            )

    # ------------------------------------------------------------ preview
    async def _record_failure(
        self, user: User, bank: str, name: str | None, content: bytes, error: FileRejected
    ) -> StatementImport:
        failed = StatementImport(
            user_id=user.id,
            bank=bank[:32],
            parser_version="-",
            file_name=(name or "statement")[-120:],
            file_format="?",
            file_size=len(content),
            file_sha256=hashlib.sha256(content).hexdigest(),
            status="failed",
            error_code=error.code,
            error_message=error.message[:500],
        )
        self.db.add(failed)
        await self.db.flush()
        return failed

    async def preview(
        self,
        user: User,
        bank: str,
        file_name: str | None,
        content: bytes,
        account_id: int | None = None,
        today: date | None = None,
    ) -> StatementImport:
        """Validates and parses the file and stores a reviewable preview.
        Raises ``FileRejected`` after recording a failed import."""

        try:
            parser = get_parser(bank)
            upload = validate_upload(file_name, content, self.settings)
            account = None
            if account_id is not None:
                account = await AccountRepository(self.db).get_for_user(account_id, user.id)
                if account is None:
                    raise FileRejected("account_not_found", "Account not found", 400)
            local_today = today or datetime.now(parser.profile.timezone).date()
            result = await parser.parse(upload, self.settings.IMPORT_MAX_ROWS, local_today)
        except FileRejected as error:
            if error.code != "unsupported_bank":
                await self._record_failure(user, bank, file_name, content, error)
                await self.db.commit()
            raise

        await self.expire_previews(user.id)
        record = StatementImport(
            user_id=user.id,
            bank=parser.profile.code,
            parser_version=parser.profile.version,
            file_name=upload.name,
            file_format=upload.format,
            file_size=upload.size,
            file_sha256=upload.sha256,
            status="preview",
            account_id=account.id if account else None,
            expires_at=datetime.now(UTC) + timedelta(hours=self.settings.IMPORT_PREVIEW_TTL_HOURS),
        )
        self.db.add(record)
        await self.db.flush()
        await self._store_rows(record, parser, upload, result, account, user.id)
        await self.db.flush()
        return record

    async def _store_rows(
        self,
        record,
        parser: BankStatementParser,
        upload: UploadedFile,
        result,
        account,
        user_id: int,
    ) -> None:  # noqa: E501
        known_currencies = set(await self.db.scalars(select(Currency.code)))
        occurrences: Counter[str] = Counter()
        prints: dict[int, str] = {}
        for row in result.rows:
            base = fingerprint(parser.profile.code, row, 0)
            occurrences[base] += 1
            prints[row.row_number] = fingerprint(parser.profile.code, row, occurrences[base])

        existing = set()
        if prints:
            existing = set(
                await self.db.scalars(
                    select(Transaction.import_hash).where(
                        Transaction.user_id == user_id,
                        Transaction.import_hash.in_(list(prints.values())),
                    )
                )
            )

        manual: set[tuple] = set()
        tz = parser.profile.timezone
        if result.rows:
            start = min(r.transaction_date for r in result.rows) - timedelta(days=1)
            end = max(r.transaction_date for r in result.rows) + timedelta(days=1)
            for when, amount, kind, currency in await self.db.execute(
                select(
                    Transaction.transaction_date,
                    Transaction.amount,
                    Transaction.transaction_type,
                    Transaction.currency_code,
                ).where(
                    Transaction.user_id == user_id,
                    Transaction.import_hash.is_(None),
                    Transaction.transaction_date >= start,
                    Transaction.transaction_date <= end,
                )
            ):
                manual.add((when.astimezone(tz).date(), amount, kind, currency))

        counts: dict[str, int] = defaultdict(int)
        dates = []
        for row in result.rows:
            status, code, message = "valid", None, None
            if row.currency_code not in known_currencies:
                status, code, message = "invalid", "unknown_currency", "currency is not supported"
            elif account is not None and row.currency_code != account.currency_code:
                status, code, message = (
                    "invalid",
                    "currency_mismatch",
                    "currency differs from the account",
                )
            elif prints[row.row_number] in existing:
                status, code, message = "duplicate", "already_imported", "already imported earlier"
            elif (
                row.transaction_date.astimezone(tz).date(),
                row.amount,
                row.transaction_type,
                row.currency_code,
            ) in manual:
                status, code, message = (
                    "possible_duplicate",
                    "matches_manual_transaction",
                    "a manually entered transaction looks the same",
                )
            counts[status] += 1
            dates.append(row.transaction_date.astimezone(tz).date())
            self.db.add(
                StatementImportRow(
                    import_id=record.id,
                    row_number=row.row_number,
                    status=status,
                    transaction_date=row.transaction_date,
                    amount=row.amount,
                    currency_code=row.currency_code,
                    transaction_type=row.transaction_type.value,
                    type_source=row.type_source,
                    description=row.description,
                    merchant=row.merchant,
                    category_hint=row.category_hint,
                    fingerprint=prints[row.row_number],
                    error_code=code,
                    error_message=message,
                )
            )
        for error in result.errors:
            counts["invalid"] += 1
            self.db.add(
                StatementImportRow(
                    import_id=record.id,
                    row_number=error.row_number,
                    status="invalid",
                    error_code=error.code,
                    error_message=error.message,
                )
            )
        record.total_rows = result.total
        record.valid_rows = counts["valid"] + counts["possible_duplicate"]
        record.invalid_rows = counts["invalid"]
        record.duplicate_rows = counts["duplicate"] + counts["possible_duplicate"]
        record.period_start = min(dates) if dates else None
        record.period_end = max(dates) if dates else None

    # ------------------------------------------------------------ commit / cancel
    async def commit(
        self,
        import_id: int,
        user: User,
        exclude_rows: set[int] | None = None,
        include_possible_duplicates: bool = False,
    ) -> CommitResult:
        record = await self.get(import_id, user.id)
        if (
            record.status == "preview"
            and record.expires_at
            and record.expires_at < datetime.now(UTC)
        ):
            await self.expire_previews(user.id)
            await self.db.commit()  # persist the expiry; the 409 below rolls back the request
            raise ConflictError("The preview has expired; upload the file again")
        if record.status != "preview":
            raise ConflictError(f"The import cannot be committed (status: {record.status})")

        rows = list(
            await self.db.scalars(
                select(StatementImportRow)
                .where(StatementImportRow.import_id == record.id)
                .order_by(StatementImportRow.row_number)
                .with_for_update()
            )
        )
        exclude = exclude_rows or set()
        selected = [
            r
            for r in rows
            if r.row_number not in exclude
            and (
                r.status == "valid"
                or (r.status == "possible_duplicate" and include_possible_duplicates)
            )
        ]
        # Re-check against transactions committed since the preview was made.
        if selected:
            taken = set(
                await self.db.scalars(
                    select(Transaction.import_hash).where(
                        Transaction.user_id == user.id,
                        Transaction.import_hash.in_([r.fingerprint for r in selected]),
                    )
                )
            )
            for r in selected:
                if r.fingerprint in taken:
                    r.status, r.error_code = "duplicate", "already_imported"
            selected = [r for r in selected if r.status != "duplicate"]

        parser = get_parser(record.bank)
        bank = await self.db.scalar(select(Bank).where(Bank.name == parser.profile.name))
        if bank is None:
            bank = Bank(name=parser.profile.name)
            self.db.add(bank)
            await self.db.flush()

        categories = CategoryRepository(self.db)
        category_ids: dict[str, Category] = {}
        income, expense = Decimal("0"), Decimal("0")
        for r in selected:
            if r.amount is None or r.transaction_date is None or r.transaction_type is None:
                continue  # only parsed (valid) rows can be selected; defensive
            row_type = TransactionType(r.transaction_type)
            name = r.category_hint or DEFAULT_CATEGORY
            if name not in category_ids:
                category_ids[name] = await categories.get_or_create_own(name, user.id)
            if not category_allows(category_ids[name].kind, row_type):
                # e.g. a refund row hinted to an income category: keep the row,
                # file it under the unrestricted default instead.
                name = DEFAULT_CATEGORY
                if name not in category_ids:
                    category_ids[name] = await categories.get_or_create_own(name, user.id)
            transaction = Transaction(
                user_id=user.id,
                amount=r.amount,
                currency_code=r.currency_code,
                transaction_type=TransactionType(r.transaction_type),
                transaction_date=r.transaction_date,
                description=r.description,
                merchant=r.merchant,
                category_id=category_ids[name].id,
                bank_id=bank.id,
                account_id=record.account_id,
                import_hash=r.fingerprint,
                import_id=record.id,
            )
            self.db.add(transaction)
            await self.db.flush()
            r.status, r.transaction_id = "imported", transaction.id
            if transaction.transaction_type is TransactionType.INCOME:
                income += r.amount
            elif transaction.transaction_type is TransactionType.EXPENSE:
                expense += r.amount
        for r in rows:
            if r.status in IMPORTABLE:
                r.status = "skipped"

        record.status = "committed"
        record.committed_at = datetime.now(UTC)
        record.imported_rows = len(selected)
        record.expires_at = None
        await self.db.flush()
        return CommitResult(len(selected), len(rows) - len(selected), income, expense)

    async def cancel(self, import_id: int, user_id: int) -> None:
        record = await self.get(import_id, user_id)
        if record.status != "preview":
            raise ConflictError(f"Only previews can be cancelled (status: {record.status})")
        await self.db.execute(
            delete(StatementImportRow).where(StatementImportRow.import_id == record.id)
        )
        record.status = "cancelled"
        record.expires_at = None


__all__ = ["CommitResult", "ImportService", "fingerprint"]
