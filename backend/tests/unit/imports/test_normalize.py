from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.models.enums import TransactionType as T
from app.services.imports.normalize import (
    RowError,
    classify,
    extract_merchant,
    mask_sensitive,
    parse_amount,
    parse_date,
)
from app.services.imports.profiles import ALMATY, COMMON_DATE_FORMATS

TODAY = date(2025, 4, 15)


class TestAmount:
    @pytest.mark.parametrize(
        ("raw", "amount", "currency"),
        [
            ("12 500,50", "12500.50", None),
            ("-12 500,50 ₸", "-12500.50", "KZT"),
            ("+350 000,00 ₸", "350000.00", "KZT"),
            ("− 5 000,00 тг", "-5000.00", "KZT"),  # unicode minus, nbsp
            ("1.234.567,89", "1234567.89", None),
            ("1,234,567.89", "1234567.89", None),
            ("1 234 567", "1234567.00", None),
            ("1500,5", "1500.50", None),
            ("(2 000,00)", "-2000.00", None),
            ("$ 25.99", "25.99", "USD"),
            ("€10,00", "10.00", "EUR"),
            ("150 руб.", "150.00", "RUB"),
            (Decimal("-3.10"), "-3.10", None),
            (1500, "1500.00", None),
            (1234.56, "1234.56", None),  # XLSX float -> exact decimal via repr
            (1234.5599999999999, "1234.56", None),  # as Excel may store it
        ],
    )
    def test_valid(self, raw: object, amount: str, currency: str | None) -> None:
        assert parse_amount(raw) == (Decimal(amount), currency)

    @pytest.mark.parametrize(
        ("raw", "code"),
        [
            ("1,500", "ambiguous_amount"),  # 1.5 or 1500? never guessed
            ("12.345", "ambiguous_amount"),
            ("0,00", "zero_amount"),
            ("0", "zero_amount"),
            ("", "missing_amount"),
            (None, "missing_amount"),
            ("abc", "invalid_amount"),
            ("12-50", "invalid_amount"),
            ("1,2,3", "invalid_amount"),
            ("10.123", "ambiguous_amount"),
            ("10,1234", "invalid_amount"),
            (0.001, "invalid_amount"),  # > 2 decimals
            (True, "invalid_amount"),
            ("99999999999999999", "invalid_amount"),
        ],
    )
    def test_invalid(self, raw: object, code: str) -> None:
        with pytest.raises(RowError) as info:
            parse_amount(raw)
        assert info.value.code == code


class TestDate:
    def p(self, value: object) -> datetime:
        return parse_date(value, COMMON_DATE_FORMATS, ALMATY, TODAY)

    @pytest.mark.parametrize(
        ("raw", "utc"),
        [
            ("03.03.2025", datetime(2025, 3, 2, 19, tzinfo=UTC)),  # 00:00 Almaty (+5)
            ("03.03.2025 14:30", datetime(2025, 3, 3, 9, 30, tzinfo=UTC)),
            ("03.03.25", datetime(2025, 3, 2, 19, tzinfo=UTC)),
            ("2025-03-03", datetime(2025, 3, 2, 19, tzinfo=UTC)),
            ("2025-03-03T10:00:00", datetime(2025, 3, 3, 5, tzinfo=UTC)),
            (datetime(2025, 3, 3, 10), datetime(2025, 3, 3, 5, tzinfo=UTC)),
            (date(2025, 3, 3), datetime(2025, 3, 2, 19, tzinfo=UTC)),
            (45719, datetime(2025, 3, 2, 19, tzinfo=UTC)),  # Excel serial for 2025-03-03
            ("15.01.2024", datetime(2024, 1, 14, 18, tzinfo=UTC)),  # Almaty was +6 then
        ],
    )
    def test_valid(self, raw: object, utc: datetime) -> None:
        assert self.p(raw) == utc

    @pytest.mark.parametrize(
        ("raw", "code"),
        [
            ("31.02.2025", "invalid_date"),
            ("2025/13/01", "invalid_date"),
            ("вчера", "invalid_date"),
            ("", "missing_date"),
            ("01.01.1999", "date_out_of_range"),
            ("17.04.2025", "date_out_of_range"),  # more than a day in the future
            (123, "invalid_date"),
        ],
    )
    def test_invalid(self, raw: object, code: str) -> None:
        with pytest.raises(RowError) as info:
            self.p(raw)
        assert info.value.code == code


class TestClassification:
    @pytest.mark.parametrize(
        ("amount", "texts", "expected", "source"),
        [
            ("100", ("Пополнение", "Зарплата"), T.INCOME, "sign"),
            ("-100", ("Покупка", "Magnum"), T.EXPENSE, "sign"),
            ("100", ("Возврат", "Возврат покупки"), T.REFUND, "keyword"),
            (
                "-100",
                ("Возврат", "Возврат долга другу"),
                T.EXPENSE,
                "sign",
            ),  # refund only on credit
            ("-100", ("Перевод", "Перевод между своими счетами"), T.TRANSFER_OUT, "keyword"),
            ("100", ("Перевод", "Перевод на депозит"), T.TRANSFER_IN, "keyword"),
            ("100", ("Перевод", "Перевод от Айгерим К."), T.INCOME, "sign"),
        ],
    )
    def test_rules(self, amount: str, texts: tuple[str, str], expected: T, source: str) -> None:
        assert classify(Decimal(amount), *texts) == (expected, source)


class TestText:
    def test_full_card_numbers_and_iin_are_masked(self) -> None:
        masked = mask_sensitive("Оплата картой 4400 4300 1234 5678, ИИН 900101300123")
        assert "4400" not in masked and "900101300123" not in masked
        assert "•••• 5678" in masked and "[ИИН]" in masked

    @pytest.mark.parametrize(
        ("description", "merchant"),
        [
            ("Покупка MAGNUM CASH&CARRY ALMATY", "MAGNUM CASH&CARRY ALMATY"),
            ("Оплата: Yandex Go", "Yandex Go"),
            ("Покупка Coffee Boom •••• 5678", "Coffee Boom"),
            ("Покупка", None),
            (None, None),
        ],
    )
    def test_merchant(self, description: str | None, merchant: str | None) -> None:
        assert extract_merchant(description, "Покупка") == merchant
