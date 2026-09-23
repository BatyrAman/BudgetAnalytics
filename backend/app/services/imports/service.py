"""
Импорт выписки:

    file → parser → normalized DTO → deduplication → categorization → database

Состояния записи statement_imports:
    PENDING → PROCESSING → COMPLETED | PARTIAL | FAILED

* COMPLETED — все строки разобраны (новые вставлены, дубликаты пропущены);
* PARTIAL   — часть строк не разобрана, остальные импортированы;
* FAILED    — файл не разобран или не разобрана ни одна строка.

Повторный импорт той же выписки не создаёт дублей: у каждой операции
стабильный external_hash и UNIQUE(user_id, external_hash) в БД.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError, NotFoundError
from app.models.category import Category
from app.models.enums import CategorySource, ImportStatus, TransactionType
from app.models.statement_import import StatementImport
from app.models.user import User
from app.repositories.banks import BankRepository
from app.repositories.cards import CardRepository
from app.repositories.categories import CategoryRepository
from app.repositories.imports import StatementImportRepository
from app.repositories.transactions import TransactionRepository
from app.services.categorization.pipeline import (
    CategorizationItem,
    CategoryDirectory,
    CategoryMatch,
    build_pipeline,
    kind_for,
)
from app.services.imports.normalize import NormalizedTransaction, normalize_rows
from app.services.parser import PARSERS, BaseStatementParser, StatementParseError, get_parser

logger = logging.getLogger(__name__)

MAX_STORED_ERRORS = 100


class UnsupportedBankError(AppError):
    code = "UNSUPPORTED_BANK"


class StatementInvalidError(AppError):
    code = "STATEMENT_INVALID"


@dataclass(frozen=True, slots=True)
class ImportOutcome:
    record: StatementImport
    bank_name: str
    total_income: Decimal
    total_expense: Decimal


class StatementImportService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.imports = StatementImportRepository(session)
        self.transactions = TransactionRepository(session)
        self.categories = CategoryRepository(session)
        self.banks = BankRepository(session)
        self.cards = CardRepository(session)

    async def list_imports(self, user_id: int, limit: int, offset: int) -> list[StatementImport]:
        return await self.imports.list_owned(
            user_id,
            order_by=(StatementImport.created_at.desc(), StatementImport.id.desc()),
            limit=limit,
            offset=offset,
        )

    async def get_import(self, import_id: int, user_id: int) -> StatementImport:
        record = await self.imports.get_owned(import_id, user_id)
        if record is None:
            raise NotFoundError("Import not found", code="IMPORT_NOT_FOUND")
        return record

    async def list_banks(self):
        return await self.banks.list()

    @staticmethod
    def supported_parsers() -> dict[str, type[BaseStatementParser]]:
        return PARSERS

    async def import_statement(
        self,
        user: User,
        bank_slug: str,
        filename: str,
        content: bytes,
        card_id: int | None = None,
    ) -> ImportOutcome:
        parser = get_parser(bank_slug)
        if parser is None:
            raise UnsupportedBankError(
                f"Unsupported bank '{bank_slug}'. Supported: {', '.join(PARSERS)}",
                details={"supported": list(PARSERS)},
            )
        if not parser.supports(filename):
            raise StatementInvalidError(
                f"Only {', '.join(parser.extensions)} files are supported",
                code="UNSUPPORTED_FILE_TYPE",
            )

        bank = await self.banks.get_or_create(parser.bank_name)

        currency = settings.DEFAULT_CURRENCY
        if card_id is not None:
            card = await self.cards.get_owned(card_id, user.id)
            if card is None:
                raise NotFoundError("Card not found", code="CARD_NOT_FOUND")
            if card.bank_id != bank.id:
                raise StatementInvalidError(
                    "Card belongs to a different bank",
                    code="CARD_BANK_MISMATCH",
                )
            currency = card.currency

        record = self.imports.add(
            StatementImport(
                user_id=user.id,
                bank_id=bank.id,
                card_id=card_id,
                parser=parser.slug,
                file_name=(filename or "statement")[:255],
                file_sha256=hashlib.sha256(content).hexdigest(),
                status=ImportStatus.PENDING,
                rows_total=0,
                rows_imported=0,
                rows_skipped=0,
                rows_failed=0,
                errors=[],
            )
        )
        await self.session.commit()

        return await self.process(record, parser, content, currency=currency)

    async def process(
        self,
        record: StatementImport,
        parser: BaseStatementParser,
        content: bytes,
        *,
        currency: str,
    ) -> ImportOutcome:
        """
        Обработка записи импорта. Идемпотентна: запись в терминальном
        статусе повторно не обрабатывается.
        """

        bank = await self.banks.get(record.bank_id)
        if ImportStatus(record.status).is_terminal:
            return ImportOutcome(record, bank.name, Decimal("0"), Decimal("0"))

        record_id = record.id
        try:
            return await self._run(record, bank.name, parser, content, currency)
        except StatementInvalidError:
            raise
        except Exception:
            # Не оставляем запись «висеть» в PROCESSING.
            await self.session.rollback()
            failed = await self.imports.get_for_update(record_id)
            if failed is not None and not ImportStatus(failed.status).is_terminal:
                failed.status = ImportStatus.FAILED
                failed.errors = [{"row": None, "message": "Internal error while importing"}]
                failed.finished_at = datetime.now(timezone.utc)
                await self.session.commit()
            logger.exception("Statement import %s crashed", record_id)
            raise

    async def _run(
        self,
        record: StatementImport,
        bank_name: str,
        parser: BaseStatementParser,
        content: bytes,
        currency: str,
    ) -> ImportOutcome:
        record.transition(ImportStatus.PROCESSING)
        record.started_at = datetime.now(timezone.utc)
        await self.session.flush()

        try:
            parsed = parser.parse(content, record.file_name)
        except StatementParseError as exc:
            record.transition(ImportStatus.FAILED)
            record.errors = [{"row": None, "message": str(exc)}]
            record.finished_at = datetime.now(timezone.utc)
            await self.session.commit()
            logger.info("Statement import %s failed: unreadable file", record.id)
            raise StatementInvalidError(str(exc), details={"import_id": record.id}) from exc

        normalized = normalize_rows(
            parsed.rows,
            user_id=record.user_id,
            bank_id=record.bank_id,
            card_id=record.card_id,
            default_currency=currency,
        )

        # Быстрый путь: уже импортированные операции не категоризируем.
        existing = await self.transactions.existing_hashes(
            record.user_id, [n.external_hash for n in normalized]
        )
        fresh = [n for n in normalized if n.external_hash not in existing]

        matches = await self._categorize(record.user_id, fresh)

        rows = [
            {
                "user_id": record.user_id,
                "bank_id": record.bank_id,
                "card_id": record.card_id,
                "import_id": record.id,
                "amount": n.amount,
                "currency": n.currency,
                "description": n.description,
                "merchant": n.merchant,
                "transaction_type": n.transaction_type,
                "transaction_date": n.transaction_date,
                "category_id": matches[n.external_hash].category_id if matches.get(n.external_hash) else None,
                "category_source": matches[n.external_hash].source if matches.get(n.external_hash) else None,
                "external_hash": n.external_hash,
            }
            for n in fresh
        ]
        inserted = await self.transactions.insert_ignoring_duplicates(rows)

        total_income = sum(
            (Decimal(r["amount"]) for r in inserted if r["transaction_type"] == TransactionType.INCOME),
            Decimal("0"),
        )
        total_expense = sum(
            (Decimal(r["amount"]) for r in inserted if r["transaction_type"] == TransactionType.EXPENSE),
            Decimal("0"),
        )

        record.rows_total = parsed.rows_total
        record.rows_imported = len(inserted)
        record.rows_skipped = len(normalized) - len(inserted)
        record.rows_failed = len(parsed.errors)
        record.errors = [
            {"row": e.row_number, "message": e.message} for e in parsed.errors[:MAX_STORED_ERRORS]
        ]

        if parsed.errors and not normalized:
            record.transition(ImportStatus.FAILED)
        elif parsed.errors:
            record.transition(ImportStatus.PARTIAL)
        else:
            record.transition(ImportStatus.COMPLETED)
        record.finished_at = datetime.now(timezone.utc)

        await self.session.commit()

        logger.info(
            "Statement import %s: status=%s imported=%s skipped=%s failed=%s",
            record.id,
            record.status.value if hasattr(record.status, "value") else record.status,
            record.rows_imported,
            record.rows_skipped,
            record.rows_failed,
        )
        return ImportOutcome(record, bank_name, total_income, total_expense)

    async def _categorize(
        self, user_id: int, items: list[NormalizedTransaction]
    ) -> dict[str, CategoryMatch]:
        if not items:
            return {}

        visible = await self.categories.list_visible(user_id)
        directory = CategoryDirectory(
            [(c.id, c.name, c.kind, c.user_id is not None) for c in visible]
        )
        memory = await self.transactions.category_memory(
            user_id, sorted({i.merchant for i in items if i.merchant})
        )
        pipeline = build_pipeline(directory, memory)

        matches: dict[str, CategoryMatch] = {}
        unresolved_hints: dict[tuple[str, str], list[NormalizedTransaction]] = {}

        for item in items:
            match = pipeline.categorize(
                CategorizationItem(
                    transaction_type=item.transaction_type,
                    merchant=item.merchant,
                    description=item.description,
                    operation=item.operation,
                    category_hint=item.category_hint,
                )
            )
            if match is not None and match.source is not CategorySource.DEFAULT:
                matches[item.external_hash] = match
                continue
            if item.category_hint:
                kind = kind_for(item.transaction_type)
                unresolved_hints.setdefault((item.category_hint.lower(), kind.value), []).append(item)
            if match is not None:
                matches[item.external_hash] = match

        # Категории из выписки, которых ещё нет, создаём как
        # пользовательские (не глобальные!) — по одной на имя.
        for group in unresolved_hints.values():
            name = group[0].category_hint[:100]
            kind = kind_for(group[0].transaction_type)
            category = self.categories.add(Category(user_id=user_id, name=name, kind=kind))
            await self.session.flush()
            directory.register(category.id, name, kind)
            for item in group:
                matches[item.external_hash] = CategoryMatch(category.id, CategorySource.STATEMENT)

        return matches
