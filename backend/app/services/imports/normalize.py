"""Normalization of statement cells into the common transaction schema.

Rules (documented because they decide money):

AMOUNT
* Spaces (incl. non-breaking/thin) are thousands separators; ``−`` and
  ``(123)`` mean negative; currency symbols/codes are removed (and remembered).
* With both ``,`` and ``.`` the LAST one is the decimal separator.
* With a single kind of separator: one separator followed by 1–2 digits at the
  end is decimal ("1500,5", "1 500,50"); groups of exactly 3 digits are
  thousands ("1.500.000"). A lone separator followed by exactly 3 digits
  ("1,500") is AMBIGUOUS and the row is rejected — it is never guessed.
* More than 2 decimals is rejected (KZT/USD/EUR/RUB have 2 minor units).
* XLSX numeric cells are binary doubles in the file format itself; they are
  converted via the shortest round-trip ``repr`` and must equal a 2-decimal
  value to within 1e-9, otherwise the row is rejected.
* Zero amounts are rejected (they carry no money movement).

DATE
* ``datetime``/``date`` cells and strings in the profile's formats are local
  times in the profile's time zone (Asia/Almaty); a date without time means
  00:00 local. Excel serial day numbers are supported.
* Dates before 2000-01-01 or more than one day in the future are rejected
  (almost always a wrong day/month order).

TYPE (amount sign + keywords in operation/description, case-insensitive)
* refund keywords on a credit  -> refund
* own-transfer keywords        -> transfer_in / transfer_out by sign
* otherwise credit -> income, debit -> expense  (``type_source`` says which rule)
Received person-to-person transfers are classified as income; users can
change the type after import.

PRIVACY: full card numbers (13–19 digits) in descriptions become ``•••• 1234``;
12-digit IINs become ``[ИИН]``.
"""

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from app.models.enums import TransactionType

TWO_PLACES = Decimal("0.01")
MIN_DATE = date(2000, 1, 1)
EXCEL_EPOCH = date(1899, 12, 30)

CURRENCY_MARKERS = [
    (re.compile(r"₸|\bKZT\b|\bтг\b|тенге", re.IGNORECASE), "KZT"),
    (re.compile(r"\$|\bUSD\b", re.IGNORECASE), "USD"),
    (re.compile(r"€|\bEUR\b", re.IGNORECASE), "EUR"),
    (re.compile(r"₽|\bRUB\b|\bруб", re.IGNORECASE), "RUB"),
]
REFUND_WORDS = re.compile(r"возврат|refund|отмена покупки|chargeback|қайтару", re.IGNORECASE)
OWN_TRANSFER_WORDS = re.compile(
    r"между своими|между счетами|на свой|со своего|own account|own transfer|"
    r"пополнение депозита|перевод на депозит|с депозита",
    re.IGNORECASE,
)
MERCHANT_PREFIXES = re.compile(
    r"^(?:покупка|оплата|платеж|платёж|purchase|payment|pos|сатып алу)\s*[:\-–]?\s*",
    re.IGNORECASE,
)
_CARD = re.compile(r"\b(?:\d[ -]?){12,18}(\d{4})\b")
_IIN = re.compile(r"\b\d{12}\b")
_MASKED_CARD = re.compile(r"(?:\*{2,}|•{2,}|x{4,})\s?\d{4}", re.IGNORECASE)


class RowError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# ---------------------------------------------------------------- amount
def detect_currency(text: str) -> str | None:
    for pattern, code in CURRENCY_MARKERS:
        if pattern.search(text):
            return code
    return None


def _from_float(value: float) -> Decimal:
    exact = Decimal(repr(value))
    rounded = exact.quantize(TWO_PLACES)
    if abs(exact - rounded) > Decimal("1e-9"):
        raise RowError("invalid_amount", "amount has more than 2 decimal places")
    return rounded


def parse_amount(value: object) -> tuple[Decimal, str | None]:
    """Signed amount and the currency found in the cell (if any)."""

    if value is None or (isinstance(value, str) and not value.strip()):
        raise RowError("missing_amount", "amount is empty")
    if isinstance(value, bool):
        raise RowError("invalid_amount", "amount is not a number")
    if isinstance(value, Decimal | int):
        amount, currency = Decimal(value), None
    elif isinstance(value, float):
        amount, currency = _from_float(value), None
    else:
        text = str(value).strip()
        currency = detect_currency(text)
        negative = text.startswith("(") and text.endswith(")")
        cleaned = text.replace("−", "-").replace("–", "-")
        cleaned = re.sub(r"[^\d,.\-+]", "", cleaned.replace(" ", " ").replace(" ", " "))
        cleaned = cleaned.replace(" ", "")
        if cleaned.count("-") > 1 or (("-" in cleaned) and not cleaned.startswith("-")):
            raise RowError("invalid_amount", "amount is not a number")
        sign = -1 if cleaned.startswith("-") or negative else 1
        digits = cleaned.lstrip("+-").strip(".,")
        if not digits or not re.fullmatch(r"[\d.,]+", digits):
            raise RowError("invalid_amount", "amount is not a number")
        if "," in digits and "." in digits:
            decimal_sep = "," if digits.rfind(",") > digits.rfind(".") else "."
            thousands_sep = "." if decimal_sep == "," else ","
            digits = digits.replace(thousands_sep, "").replace(decimal_sep, ".")
        else:
            sep = "," if "," in digits else "." if "." in digits else None
            if sep is not None:
                parts = digits.split(sep)
                if len(parts) == 2 and 1 <= len(parts[1]) <= 2:
                    digits = parts[0] + "." + parts[1]
                elif len(parts) == 2 and len(parts[1]) == 3:
                    raise RowError(
                        "ambiguous_amount",
                        "amount is ambiguous (thousands or decimal separator?)",
                    )
                elif all(len(p) == 3 for p in parts[1:]) and 1 <= len(parts[0]) <= 3:
                    digits = "".join(parts)
                else:
                    raise RowError("invalid_amount", "amount is not a number")
        try:
            amount = Decimal(digits) * sign
        except InvalidOperation:
            raise RowError("invalid_amount", "amount is not a number") from None
    if not amount.is_finite():
        raise RowError("invalid_amount", "amount is not a number")
    if amount != amount.quantize(TWO_PLACES):
        raise RowError("invalid_amount", "amount has more than 2 decimal places")
    if amount == 0:
        raise RowError("zero_amount", "amount must not be zero")
    if abs(amount) >= Decimal("1e16"):
        raise RowError("invalid_amount", "amount is too large")
    return amount.quantize(TWO_PLACES), currency


# ---------------------------------------------------------------- date
def parse_date(value: object, formats: tuple[str, ...], tz: ZoneInfo, today: date) -> datetime:
    if value is None or (isinstance(value, str) and not value.strip()):
        raise RowError("missing_date", "date is empty")
    local: datetime
    if isinstance(value, datetime):
        local = value.replace(tzinfo=tz) if value.tzinfo is None else value
    elif isinstance(value, date):
        local = datetime.combine(value, time.min, tzinfo=tz)
    elif isinstance(value, int | float) and not isinstance(value, bool):
        if not 20000 <= value <= 80000:
            raise RowError("invalid_date", "date is not recognized")
        local = datetime.combine(EXCEL_EPOCH, time.min, tzinfo=tz) + timedelta(days=float(value))
    else:
        text = re.sub(r"\s+", " ", str(value).strip())
        for fmt in formats:
            try:
                local = datetime.strptime(text, fmt).replace(tzinfo=tz)
                break
            except ValueError:
                continue
        else:
            raise RowError("invalid_date", "date is not recognized")
    day = local.astimezone(tz).date()
    if day < MIN_DATE or day > today + timedelta(days=1):
        raise RowError("date_out_of_range", "date is outside the plausible range")
    return local.astimezone(UTC)


# ---------------------------------------------------------------- text
def mask_sensitive(text: str) -> str:
    text = _CARD.sub(lambda m: f"•••• {m.group(1)}", text)
    return _IIN.sub("[ИИН]", text)


def clean_text(value: object, limit: int) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    if not text:
        return None
    return mask_sensitive(text)[:limit]


def extract_merchant(description: str | None, operation: str | None) -> str | None:
    """Heuristic: purchase-like descriptions minus the operation prefix and
    masked card numbers. ``None`` when nothing merchant-like remains."""

    if not description:
        return None
    text = MERCHANT_PREFIXES.sub("", description)
    text = _MASKED_CARD.sub("", text)
    text = re.sub(r"•••• \d{4}", "", text)
    text = re.sub(r"\s+", " ", text).strip(" ,.;:-–")
    if not text or text.lower() == (operation or "").strip().lower() or text.isdigit():
        return None
    return text[:200]


# ---------------------------------------------------------------- type
def classify(signed_amount: Decimal, *texts: str | None) -> tuple[TransactionType, str]:
    joined = " ".join(t for t in texts if t)
    credit = signed_amount > 0
    if credit and REFUND_WORDS.search(joined):
        return TransactionType.REFUND, "keyword"
    if OWN_TRANSFER_WORDS.search(joined):
        return (TransactionType.TRANSFER_IN if credit else TransactionType.TRANSFER_OUT), "keyword"
    return (TransactionType.INCOME if credit else TransactionType.EXPENSE), "sign"


@dataclass(frozen=True)
class NormalizedRow:
    row_number: int
    transaction_date: datetime
    amount: Decimal  # always > 0
    currency_code: str
    transaction_type: TransactionType
    type_source: str
    description: str | None
    merchant: str | None
    category_hint: str | None


@dataclass(frozen=True)
class InvalidRow:
    row_number: int
    code: str
    message: str
