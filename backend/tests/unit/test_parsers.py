from datetime import datetime
from decimal import Decimal

import pytest

from app.models.enums import TransactionType
from app.services.imports.normalize import normalize_rows, transaction_hash
from app.services.parser import FreedomParser, HalykParser, KaspiParser, StatementParseError, get_parser
from app.services.parser.base import RowParseError, parse_amount


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("-12 500", "-12500"),
        ("- 1 500,00 ₸", "-1500.00"),
        ("+10 000.50", "10000.50"),
        ("(250,00)", "-250.00"),
        ("1,234.56", "1234.56"),
        ("1.234,56", "1234.56"),
        ("−1 000", "-1000"),
        ("500 KZT", "500"),
        ("999999999999.99", "999999999999.99"),
    ],
)
def test_parse_amount(raw, expected):
    assert parse_amount(raw) == Decimal(expected)


@pytest.mark.parametrize("raw", ["", "abc", "1.2.3", "12,345,67", "1.001", "--5"])
def test_parse_amount_rejects_garbage(raw):
    with pytest.raises(RowParseError):
        parse_amount(raw)


def test_registry():
    assert isinstance(get_parser("KASPI"), KaspiParser)
    assert isinstance(get_parser("halyk"), HalykParser)
    assert isinstance(get_parser("freedom"), FreedomParser)
    assert get_parser("unknown") is None


def test_missing_required_columns():
    with pytest.raises(StatementParseError):
        KaspiParser().parse(b"description,category\nx,y\n")


def test_empty_file():
    assert KaspiParser().parse(b"").rows == []


def test_bad_encoding():
    with pytest.raises(StatementParseError):
        # невалидный UTF-8, но cp1251 декодирует любые байты кроме 0x98
        KaspiParser().parse(b"\x98\x98\x98")


def test_rows_and_errors_are_separated():
    statement = KaspiParser().parse(
        "date,description,amount\n"
        "2025-01-31 23:59:59,Night,-10\n"
        ",,\n"                       # пустая строка пропускается
        "31.02.2025,Bad date,-1\n"   # несуществующая дата
        "2024-02-29,Leap,+5\n".encode()
    )
    assert [r.row_number for r in statement.rows] == [2, 5]
    assert statement.errors[0].row_number == 4
    assert statement.rows[0].transaction_type is TransactionType.EXPENSE
    assert statement.rows[1].transaction_type is TransactionType.INCOME
    assert statement.rows[1].transaction_date == datetime(2024, 2, 29)
    assert statement.rows_total == 3


def test_error_messages_do_not_leak_row_content():
    statement = KaspiParser().parse("date,description,amount\n2025-01-01,Secret Person,notanumber\n".encode())
    assert "Secret" not in statement.errors[0].message


def _row(**kw):
    from app.services.parser.base import ParsedRow

    base = dict(
        row_number=2,
        transaction_date=datetime(2025, 3, 1, 12, 0),
        amount=Decimal("100"),
        transaction_type=TransactionType.EXPENSE,
        description="  Magnum   Almaty ",
    )
    base.update(kw)
    return ParsedRow(**base)


def test_hash_is_stable_and_normalized():
    a = normalize_rows([_row()], user_id=1, bank_id=1, card_id=None, default_currency="KZT")[0]
    b = normalize_rows([_row(description="magnum almaty")], user_id=1, bank_id=1, card_id=None, default_currency="KZT")[0]
    assert a.external_hash == b.external_hash
    assert a.merchant == "MAGNUM ALMATY"
    assert len(a.external_hash) == 64


@pytest.mark.parametrize(
    "change",
    [
        {"user_id": 2},
        {"card_id": 7},
        {"bank_id": 2},
    ],
)
def test_hash_depends_on_owner_and_account(change):
    params = {"user_id": 1, "bank_id": 1, "card_id": None}
    base = normalize_rows([_row()], default_currency="KZT", **params)[0]
    params.update(change)
    other = normalize_rows([_row()], default_currency="KZT", **params)[0]
    assert base.external_hash != other.external_hash


@pytest.mark.parametrize(
    "change",
    [
        {"amount": Decimal("100.01")},
        {"transaction_date": datetime(2025, 3, 1, 12, 1)},
        {"transaction_type": TransactionType.INCOME},
        {"description": "Small"},
    ],
)
def test_hash_depends_on_transaction_fields(change):
    base = normalize_rows([_row()], user_id=1, bank_id=1, card_id=None, default_currency="KZT")[0]
    other = normalize_rows([_row(**change)], user_id=1, bank_id=1, card_id=None, default_currency="KZT")[0]
    assert base.external_hash != other.external_hash


def test_duplicate_rows_in_same_file_get_distinct_hashes():
    rows = normalize_rows([_row(), _row(row_number=3)], user_id=1, bank_id=1, card_id=None, default_currency="KZT")
    assert rows[0].external_hash != rows[1].external_hash
    again = normalize_rows([_row(), _row(row_number=3)], user_id=1, bank_id=1, card_id=None, default_currency="KZT")
    assert [r.external_hash for r in rows] == [r.external_hash for r in again]


def test_hash_function_amount_formatting():
    kwargs = dict(
        user_id=1,
        account="bank:1",
        transaction_date=datetime(2025, 1, 1),
        transaction_type=TransactionType.EXPENSE,
        description="x",
        occurrence=1,
    )
    assert transaction_hash(amount=Decimal("100"), **kwargs) == transaction_hash(amount=Decimal("100.00"), **kwargs)
