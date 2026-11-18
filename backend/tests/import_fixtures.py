"""SYNTHETIC, ANONYMIZED statement fixtures generated in code.

These files imitate the GENERAL shape of bank exports (a preamble, a header
row, data rows, a totals row) with invented people, merchants and amounts.
They are NOT copies of real Kaspi/Halyk/Freedom export formats — those must be
added from real anonymized samples supplied by the project owner before any
parser is marked ``verified``.
"""

import io
import zipfile
from datetime import datetime
from typing import Any

import openpyxl

PREAMBLE = [
    ["Выписка по счёту (СИНТЕТИЧЕСКИЕ ДАННЫЕ)"],
    ["Клиент:", "Тестовый Клиент"],
    ["Период:", "01.03.2025 - 31.03.2025"],
    [],
]
HEADER = ["Дата", "Сумма", "Валюта", "Операция", "Детали"]
ROWS = [
    ["01.03.2025", "+350 000,00 ₸", "KZT", "Пополнение", "Зарплата ТОО Ромашка"],
    ["02.03.2025 14:30", "-12 500,50 ₸", "KZT", "Покупка", "Покупка MAGNUM CASH&CARRY ALMATY"],
    ["03.03.2025", "-2 000,00 ₸", "KZT", "Покупка", "Покупка Coffee Boom карта 4400430012345678"],
    ["03.03.2025", "-2 000,00 ₸", "KZT", "Покупка", "Покупка Coffee Boom карта 4400430012345678"],
    ["05.03.2025", "+1 500,00 ₸", "KZT", "Возврат", "Возврат покупки MAGNUM"],
    ["06.03.2025", "-50 000,00 ₸", "KZT", "Перевод", "Перевод между своими счетами"],
]
TOTALS = ["Итого", "+285 000,00 ₸"]


def csv_bytes(
    rows: list[list[str]] | None = None,
    header: list[str] | None = None,
    preamble: bool = True,
    encoding: str = "utf-8-sig",
    delimiter: str = ";",
) -> bytes:
    lines: list[list[str]] = []
    if preamble:
        lines += PREAMBLE
    lines.append(header or HEADER)
    lines += rows if rows is not None else ROWS
    lines.append(TOTALS)
    text = "\n".join(
        delimiter.join(f'"{c}"' if delimiter in c else c for c in line) for line in lines
    )
    if encoding.lower() == "cp1251":
        text = text.replace("₸", "тг")  # CP1251 has no tenge sign; real files write "тг"
    return text.encode(encoding)


def xlsx_bytes(rows: list[list[Any]] | None = None, header: list[str] | None = None) -> bytes:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    for line in PREAMBLE:
        sheet.append(line)
    sheet.append(header or ["Дата", "Приход", "Расход", "Валюта", "Описание"])
    for line in (
        rows
        if rows is not None
        else [
            [datetime(2025, 3, 1, 9, 0), 350000.0, None, "KZT", "Зарплата ТОО Ромашка"],
            [datetime(2025, 3, 2, 14, 30), None, 12500.5, "KZT", "Покупка MAGNUM ALMATY"],
            [datetime(2025, 3, 4), None, 999.99, "KZT", "Оплата Yandex Go"],
        ]
    ):
        sheet.append(line)
    sheet.append(["Итого", 350000.0, 13500.49])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _rezip(content: bytes, extra: dict[str, bytes]) -> bytes:
    source = zipfile.ZipFile(io.BytesIO(content))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        for item in source.infolist():
            target.writestr(item, source.read(item.filename))
        for name, data in extra.items():
            target.writestr(name, data)
    return out.getvalue()


def xlsx_with_macro() -> bytes:
    return _rezip(xlsx_bytes(), {"xl/vbaProject.bin": b"\x00fake-vba"})


def xlsx_with_external_link() -> bytes:
    return _rezip(xlsx_bytes(), {"xl/externalLinks/externalLink1.xml": b"<x/>"})


def zip_bomb() -> bytes:
    """A small XLSX-looking archive that expands to ~60 MB."""

    return _rezip(xlsx_bytes(), {"xl/media/bomb.bin": b"\x00" * (60 * 1024 * 1024)})


def plain_zip() -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("notes.txt", "not a workbook")
    return out.getvalue()
