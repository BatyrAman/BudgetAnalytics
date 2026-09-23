"""
Минимизация и редакция персональных данных перед LLM.

Правило: в LLM уходят агрегаты и результаты расчётов, а не сырые
данные. Перед отправкой любой полезной нагрузки:

1. удаляются запрещённые ключи (email, ФИО, ИИН, PAN, CVV, номера
   счетов, пароли, токены) — на любой глубине вложенности;
2. строки прогоняются через регулярные маскировки (ИИН, номера
   карт, IBAN KZ, телефоны, e-mail) и через список
   известных имён пользователя;
3. описания операций вида «Перевод Иванову И.» сводятся к
   категории/типу контрагента.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

FORBIDDEN_KEYS = frozenset(
    {
        "email",
        "full_name",
        "name_on_card",
        "iin",
        "pan",
        "card_number",
        "cvv",
        "cvc",
        "pin",
        "account_number",
        "iban",
        "password",
        "hashed_password",
        "token",
        "access_token",
        "refresh_token",
        "phone",
        "address",
        "external_hash",
        "user_id",
    }
)

_IIN = re.compile(r"\b\d{12}\b")
_PAN_CANDIDATE = re.compile(r"\b(?:\d[ -]?){12,18}\d\b")
_IBAN = re.compile(r"(?i)\bKZ\d{2}[0-9A-Z]{13,16}\b")
_PHONE = re.compile(r"(?:\+7|\b8)[\s(-]*7\d{2}[\s)-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}\b")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_TRANSFER = re.compile(r"(?i)^(перевод|transfer)\b.*")
# Числовые значения-строки (деньги сериализуются как "1234.50") не редактируются.
_NUMERIC = re.compile(r"-?\d+(\.\d+)?")


@dataclass
class PIIRedactor:
    known_names: Iterable[str] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        parts = {p for name in self.known_names for p in re.split(r"\s+", name or "") if len(p) >= 3}
        self._names = re.compile("|".join(re.escape(p) for p in sorted(parts, key=len, reverse=True)), re.I) if parts else None

    def redact_text(self, text: str) -> str:
        if _NUMERIC.fullmatch(text):
            return text
        if _TRANSFER.match(text.strip()):
            return "Перевод [получатель скрыт]"
        # Любая последовательность из 13–19 цифр в тексте считается
        # номером карты: лучше скрыть номер договора, чем пропустить PAN.
        text = _PAN_CANDIDATE.sub("[PAN]", text)
        text = _IBAN.sub("[IBAN]", text)
        text = _IIN.sub("[IIN]", text)
        text = _PHONE.sub("[PHONE]", text)
        text = _EMAIL.sub("[EMAIL]", text)
        if self._names is not None:
            text = self._names.sub("[NAME]", text)
        return text

    def sanitize(self, payload: Any) -> Any:
        """Рекурсивно чистит dict/list/str. Числа (Decimal/int) не трогает."""

        if isinstance(payload, dict):
            return {
                key: self.sanitize(value)
                for key, value in payload.items()
                if str(key).lower() not in FORBIDDEN_KEYS
            }
        if isinstance(payload, (list, tuple)):
            return [self.sanitize(item) for item in payload]
        if isinstance(payload, str):
            return self.redact_text(payload)
        if isinstance(payload, (int, float, Decimal, bool)) or payload is None:
            return payload
        return self.redact_text(str(payload))
