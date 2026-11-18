"""File validation and per-bank parsing on SYNTHETIC fixtures (see tests/import_fixtures.py)."""

from datetime import date
from decimal import Decimal

import pytest

from app.core.config import settings
from app.models.enums import TransactionType as T
from app.services.imports.files import FileRejected, read_csv, sanitize_filename, validate_upload
from app.services.imports.parsers import (
    PARSERS,
    FreedomParser,
    HalykParser,
    KaspiParser,
    get_parser,
)
from tests import import_fixtures as fx

TODAY = date(2025, 4, 15)


def rejected(name: str, content: bytes) -> FileRejected:
    with pytest.raises(FileRejected) as info:
        validate_upload(name, content, settings)
    return info.value


class TestValidation:
    def test_accepts_csv_and_xlsx(self) -> None:
        assert validate_upload("s.csv", fx.csv_bytes(), settings).format == "csv"
        upload = validate_upload("s.xlsx", fx.xlsx_bytes(), settings)
        assert upload.format == "xlsx" and len(upload.sha256) == 64

    @pytest.mark.parametrize(
        ("name", "content", "code", "status"),
        [
            ("s.txt", b"a;b", "unsupported_format", 415),
            ("s.xls", b"a;b", "unsupported_format", 415),
            ("s.exe", b"MZ\x90\x00", "unsupported_format", 415),
            ("s", b"a;b", "unsupported_format", 415),
            ("s.csv", b"   \n ", "empty_file", 422),
            ("s.csv", b"%PDF-1.7 ...", "format_mismatch", 415),  # PDF renamed to .csv
            ("s.csv", None, "format_mismatch", 415),  # XLSX renamed to .csv (filled below)
            ("s.xlsx", b"date;amount\n", "format_mismatch", 415),  # CSV renamed to .xlsx
            ("s.csv", b"MZ\x00\x00binary", "format_mismatch", 415),  # binary with NUL bytes
            ("s.pdf", b"%PDF-1.7 ...", "pdf_not_supported", 415),
        ],
    )
    def test_rejections(self, name: str, content: bytes | None, code: str, status: int) -> None:
        error = rejected(name, content if content is not None else fx.xlsx_bytes())
        assert (error.code, error.status_code) == (code, status)

    def test_size_limit(self) -> None:
        error = rejected("s.csv", b"a" * (settings.IMPORT_MAX_FILE_BYTES + 1))
        assert (error.code, error.status_code) == ("file_too_large", 413)

    @pytest.mark.parametrize(
        ("factory", "code"),
        [
            (fx.xlsx_with_macro, "malicious_file"),
            (fx.xlsx_with_external_link, "malicious_file"),
            (fx.zip_bomb, "malicious_file"),
            (fx.plain_zip, "unsupported_format"),
        ],
    )
    def test_dangerous_workbooks(self, factory, code: str) -> None:  # type: ignore[no-untyped-def]
        assert rejected("s.xlsx", factory()).code == code

    def test_damaged_zip(self) -> None:
        assert rejected("s.xlsx", b"PK\x03\x04garbage").code == "malformed_file"

    @pytest.mark.parametrize(
        ("raw", "clean"),
        [
            ("../../etc/passwd.csv", "passwd.csv"),
            ("C:\\Users\\me\\Выписка март.csv", "Выписка март.csv"),
            ("evil\x00name<>.csv", "evilname.csv"),
            ("", "statement"),
        ],
    )
    def test_filename_sanitization(self, raw: str, clean: str) -> None:
        assert sanitize_filename(raw) == clean

    def test_cp1251_and_delimiters(self) -> None:
        # Real CP1251 files cannot contain "₸"; they write "тг".
        rows = [[c.replace("₸", "тг") for c in row] for row in fx.ROWS]
        cp = fx.csv_bytes(rows, encoding="cp1251", delimiter=",")
        assert read_csv(cp, 100)[4][0] == "Дата"
        tab = fx.csv_bytes(delimiter="\t", preamble=False)
        assert read_csv(tab, 100)[0] == fx.HEADER

    def test_undecodable_csv(self) -> None:
        # Bytes invalid in UTF-8 and unmapped in CP1251 (0x98).
        with pytest.raises(FileRejected) as info:
            read_csv(b"\xff\xfe\x98\x98", 10)
        assert info.value.code == "unreadable_file"


class TestParsers:
    @pytest.mark.parametrize("parser_cls", [KaspiParser, HalykParser, FreedomParser])
    async def test_csv_with_preamble_and_totals(self, parser_cls) -> None:  # type: ignore[no-untyped-def]
        result = await parser_cls().parse(
            validate_upload("s.csv", fx.csv_bytes(), settings), 100, TODAY
        )
        assert result.errors == []
        rows = result.rows
        assert [r.row_number for r in rows] == [6, 7, 8, 9, 10, 11]  # file line numbers
        assert [r.transaction_type for r in rows] == [
            T.INCOME,
            T.EXPENSE,
            T.EXPENSE,
            T.EXPENSE,
            T.REFUND,
            T.TRANSFER_OUT,
        ]
        assert [r.amount for r in rows] == [
            Decimal(v)
            for v in ("350000.00", "12500.50", "2000.00", "2000.00", "1500.00", "50000.00")
        ]
        assert rows[1].merchant == "MAGNUM CASH&CARRY ALMATY"
        assert "4400430012345678" not in (rows[2].description or "") and "•••• 5678" in (
            rows[2].description or ""
        )
        assert rows[0].merchant is None  # income: no merchant
        assert {r.currency_code for r in rows} == {"KZT"}

    async def test_xlsx_with_credit_and_debit_columns(self) -> None:
        result = await KaspiParser().parse(
            validate_upload("s.xlsx", fx.xlsx_bytes(), settings), 100, TODAY
        )
        assert result.errors == []
        assert [(r.transaction_type, r.amount) for r in result.rows] == [
            (T.INCOME, Decimal("350000.00")),
            (T.EXPENSE, Decimal("12500.50")),
            (T.EXPENSE, Decimal("999.99")),
        ]
        assert result.rows[2].merchant == "Yandex Go"

    async def test_row_errors_do_not_fail_the_file(self) -> None:
        rows = [
            ["01.03.2025", "-100,00", "KZT", "Покупка", "ok"],
            ["31.02.2025", "-100,00", "KZT", "Покупка", "bad date"],
            ["02.03.2025", "1,500", "KZT", "Покупка", "ambiguous"],
            ["02.03.2025", "0", "KZT", "Покупка", "zero"],
            ["02.03.2025", "-5", "XX1", "Покупка", "bad currency"],
            ["02.03.2025", "-5 $", "KZT", "Покупка", "currency clash"],
        ]
        result = await KaspiParser().parse(
            validate_upload("s.csv", fx.csv_bytes(rows), settings), 100, TODAY
        )
        assert len(result.rows) == 1
        assert [(e.row_number, e.code) for e in result.errors] == [
            (7, "invalid_date"),
            (8, "ambiguous_amount"),
            (9, "zero_amount"),
            (10, "invalid_currency"),
            (11, "invalid_currency"),
        ]

    @pytest.mark.parametrize(
        "header",
        [
            ["Дата", "Описание"],
            ["Сумма", "Описание"],
            ["Колонка1", "Колонка2"],
            ["Дата", "Приход", "Описание"],
        ],
    )
    async def test_missing_columns(self, header: list[str]) -> None:
        content = fx.csv_bytes([["01.03.2025", "x", "y"]], header=header)
        with pytest.raises(FileRejected) as info:
            await KaspiParser().parse(validate_upload("s.csv", content, settings), 100, TODAY)
        assert info.value.code == "missing_columns"

    async def test_too_many_rows(self) -> None:
        rows = [["01.03.2025", "-1,00", "KZT", "Покупка", "x"]] * 30
        upload = validate_upload("s.csv", fx.csv_bytes(rows), settings)
        with pytest.raises(FileRejected) as info:
            await KaspiParser().parse(upload, 20, TODAY)
        assert info.value.code == "too_many_rows"

    async def test_no_transactions(self) -> None:
        with pytest.raises(FileRejected) as info:
            await KaspiParser().parse(
                validate_upload("s.csv", fx.csv_bytes([]), settings), 100, TODAY
            )
        assert info.value.code == "no_transactions"

    def test_profiles_are_explicitly_unverified(self) -> None:
        assert all(cls.profile.verified is False for cls in PARSERS.values())
        assert all(cls.profile.version.endswith("unverified") for cls in PARSERS.values())

    def test_unknown_bank(self) -> None:
        with pytest.raises(FileRejected) as info:
            get_parser("monobank")
        assert (info.value.code, info.value.status_code) == ("unsupported_bank", 400)
