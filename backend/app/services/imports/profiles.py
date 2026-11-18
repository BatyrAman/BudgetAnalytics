"""Bank statement profiles.

!!! UNVERIFIED !!!
No real (anonymized) exports from Kaspi, Halyk or Freedom were available when
these profiles were written. Header aliases and date formats are ASSUMPTIONS
based on common Russian/Kazakh/English statement headers; they are NOT
confirmed bank formats. ``verified=False`` is exposed by the API. When real
anonymized samples are supplied, tune each profile, add the samples as test
fixtures and set ``verified=True``.

Headers are matched case-insensitively after collapsing whitespace; the
header row is searched in the first rows (statements often start with a
preamble: account holder, period, etc.).
"""

from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

ALMATY = ZoneInfo("Asia/Almaty")

COMMON_DATE_FORMATS = (
    "%d.%m.%Y",
    "%d.%m.%Y %H:%M",
    "%d.%m.%Y %H:%M:%S",
    "%d.%m.%y",
    "%d.%m.%y %H:%M",
    "%Y-%m-%d",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%d/%m/%Y",
)

_COMMON = {
    "date": (
        "дата",
        "дата операции",
        "дата транзакции",
        "дата проведения",
        "date",
        "transaction date",
        "күні",
        "операция күні",
    ),
    "amount": (
        "сумма",
        "сумма операции",
        "сумма в валюте счета",
        "сумма в валюте счёта",
        "amount",
        "сомасы",
    ),
    "credit": ("приход", "зачисление", "поступление", "кредит", "credit"),
    "debit": ("расход", "списание", "дебет", "debit"),
    "currency": ("валюта", "валюта операции", "currency"),
    "description": (
        "описание",
        "детали",
        "детали операции",
        "описание операции",
        "назначение платежа",
        "description",
        "details",
        "сипаттама",
    ),
    "operation": ("операция", "тип операции", "вид операции", "operation", "type"),
    "merchant": ("получатель", "контрагент", "место совершения", "merchant"),
    "category": ("категория", "category", "санат"),
}


@dataclass(frozen=True)
class BankProfile:
    code: str
    name: str
    verified: bool
    columns: dict[str, tuple[str, ...]]
    date_formats: tuple[str, ...] = COMMON_DATE_FORMATS
    default_currency: str = "KZT"
    timezone: ZoneInfo = ALMATY
    summary_markers: tuple[str, ...] = field(
        default=("итого", "всего", "total", "остаток", "баланс на", "сальдо")
    )

    @property
    def version(self) -> str:
        return f"{self.code}-{'v1' if self.verified else 'v1-unverified'}"


def _profile(code: str, name: str, extra: dict[str, tuple[str, ...]] | None = None) -> BankProfile:
    columns = {k: tuple(v) for k, v in _COMMON.items()}
    for key, aliases in (extra or {}).items():
        columns[key] = tuple(dict.fromkeys(aliases + columns.get(key, ())))
    return BankProfile(code=code, name=name, verified=False, columns=columns)


PROFILES: dict[str, BankProfile] = {
    "kaspi": _profile("kaspi", "Kaspi Bank"),
    "halyk": _profile(
        "halyk",
        "Halyk Bank",
        {"date": ("дата проведения операции",), "description": ("описание операции",)},
    ),
    "freedom": _profile("freedom", "Freedom Bank"),
}
