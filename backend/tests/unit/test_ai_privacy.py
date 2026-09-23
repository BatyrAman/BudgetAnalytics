from decimal import Decimal

import pytest

from app.services.ai.privacy import PIIRedactor


@pytest.mark.parametrize(
    "raw, leaked",
    [
        ("ИИН 900101300123", "900101300123"),
        ("карта 4400 4301 2345 6781", "4400 4301 2345 6781"),
        ("карта 4400-4301-2345-6781", "4400-4301-2345-6781"),
        ("IBAN KZ86125KZT5004100100", "KZ86125KZT5004100100"),
        ("звонить +7 701 123 45 67", "701 123 45 67"),
        ("пишите на a.b@mail.kz", "a.b@mail.kz"),
    ],
)
def test_patterns_are_redacted(raw, leaked):
    assert leaked not in PIIRedactor().redact_text(raw)


def test_numeric_values_are_not_touched():
    redactor = PIIRedactor()
    # деньги-строки из tool-ответов (даже 12+ цифр) остаются как есть
    assert redactor.redact_text("100000000000.00") == "100000000000.00"
    assert redactor.redact_text("-1500.50") == "-1500.50"
    assert redactor.redact_text("платёж 52871.10 ₸") == "платёж 52871.10 ₸"


def test_known_names_and_transfers():
    redactor = PIIRedactor(known_names=["Иван Петров"])
    assert "Петров" not in redactor.redact_text("Кредит Петров Иван")
    assert redactor.redact_text("Перевод Серику К.") == "Перевод [получатель скрыт]"


def test_sanitize_drops_forbidden_keys_recursively_and_keeps_numbers():
    payload = {
        "email": "x@y.kz",
        "user_id": 7,
        "income": Decimal("420000"),
        "items": [{"full_name": "Иван", "amount": "100.00", "iin": "900101300123", "note": "ok"}],
    }
    clean = PIIRedactor().sanitize(payload)
    assert clean == {"income": Decimal("420000"), "items": [{"amount": "100.00", "note": "ok"}]}
