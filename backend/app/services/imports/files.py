"""Upload validation and safe table reading.

The declared extension/MIME type is never trusted: the format is decided by
the file's CONTENT and must agree with the extension.

* CSV  — text only (no NUL bytes), UTF-8 (with or without BOM) or CP1251,
         delimiter sniffed among ``;``, ``,``, tab.
* XLSX — a ZIP with the OOXML workbook parts; rejected when it contains
         macros (``vbaProject.bin``), external links, too many entries, or when
         the uncompressed size / compression ratio indicates a zip bomb. Parsed
         with openpyxl in read-only mode (XML hardened by defusedxml), in a
         worker thread so the event loop is never blocked.
* PDF  — recognized and rejected as "not supported yet": no verified parser
         exists (see ``profiles``).

Everything is read from memory; nothing is written to disk.
"""

import csv
import hashlib
import io
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from typing import Any

from app.core.config import Settings

ALLOWED_EXTENSIONS = {".csv": "csv", ".xlsx": "xlsx", ".pdf": "pdf"}
MAX_ZIP_ENTRIES = 2000
MAX_CELL_CHARS = 2000


class FileRejected(ValueError):
    """Safe, user-readable reason + machine code + HTTP status."""

    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class UploadedFile:
    name: str  # sanitized
    format: str  # csv | xlsx | pdf
    content: bytes
    sha256: str

    @property
    def size(self) -> int:
        return len(self.content)


def sanitize_filename(name: str | None) -> str:
    """Basename only, no control/path characters, at most 120 characters."""

    base = re.split(r"[\\/]", name or "")[-1]
    base = unicodedata.normalize("NFKC", base)
    base = "".join(ch for ch in base if ch.isprintable() and ch not in '<>:"|?*')
    base = base.strip(" .") or "statement"
    return base[-120:]


def _extension(name: str) -> str:
    match = re.search(r"(\.[A-Za-z0-9]+)$", name)
    return match.group(1).lower() if match else ""


def _check_xlsx_container(content: bytes, settings: Settings) -> None:
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile:
        raise FileRejected(
            "malformed_file", "The XLSX file is damaged or not an XLSX file"
        ) from None
    with archive:
        entries = archive.infolist()
        if len(entries) > MAX_ZIP_ENTRIES:
            raise FileRejected("malicious_file", "The XLSX file has too many parts")
        names = {e.filename for e in entries}
        if "[Content_Types].xml" not in names or "xl/workbook.xml" not in names:
            raise FileRejected("unsupported_format", "The file is not an Excel workbook (.xlsx)")
        lowered = {n.lower() for n in names}
        if any(n.endswith("vbaproject.bin") for n in lowered):
            raise FileRejected("malicious_file", "Workbooks with macros are not accepted")
        if any(n.startswith("xl/externallinks/") for n in lowered):
            raise FileRejected("malicious_file", "Workbooks with external links are not accepted")
        total = sum(e.file_size for e in entries)
        compressed = sum(e.compress_size for e in entries) or 1
        if (
            total > settings.IMPORT_XLSX_MAX_UNCOMPRESSED_BYTES
            or total / compressed > settings.IMPORT_XLSX_MAX_RATIO
        ):
            raise FileRejected("malicious_file", "The XLSX file expands to an unsafe size")


def validate_upload(name: str | None, content: bytes, settings: Settings) -> UploadedFile:
    clean_name = sanitize_filename(name)
    extension = _extension(clean_name)
    if extension not in ALLOWED_EXTENSIONS:
        raise FileRejected(
            "unsupported_format", "Only .csv and .xlsx statements are supported", status_code=415
        )
    if len(content) > settings.IMPORT_MAX_FILE_BYTES:
        raise FileRejected(
            "file_too_large",
            f"The file is larger than {settings.IMPORT_MAX_FILE_BYTES // 1024} KB",
            status_code=413,
        )
    if not content.strip():
        raise FileRejected("empty_file", "The file is empty")

    declared = ALLOWED_EXTENSIONS[extension]
    if content.startswith(b"%PDF-"):
        detected = "pdf"
    elif content.startswith(b"PK\x03\x04"):
        detected = "xlsx"
    elif b"\x00" in content:
        detected = "binary"
    else:
        detected = "csv"
    if detected != declared:
        raise FileRejected(
            "format_mismatch",
            "The file content does not match its extension",
            status_code=415,
        )
    if detected == "pdf":
        raise FileRejected(
            "pdf_not_supported",
            "PDF statements are not supported yet: please export the statement as CSV or XLSX",
            status_code=415,
        )
    if detected == "xlsx":
        _check_xlsx_container(content, settings)
    return UploadedFile(clean_name, detected, content, hashlib.sha256(content).hexdigest())


# ---------------------------------------------------------------- readers
def _decode(content: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1251"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise FileRejected("unreadable_file", "The CSV file is not UTF-8 or Windows-1251 text")


def detect_delimiter(text: str) -> str:
    """The delimiter giving the most rows with the same (most common) number of
    columns > 1 in the first lines. ``csv.Sniffer`` is not used: it picks ","
    for ";"-separated statements whose amounts contain decimal commas."""

    sample = text.splitlines()[:60]
    best, best_score = ";", -1
    for delimiter in (";", "\t", ","):
        try:
            widths = [len(r) for r in csv.reader(sample, delimiter=delimiter) if len(r) > 1]
        except csv.Error:
            continue
        if not widths:
            continue
        modal = max(set(widths), key=widths.count)
        score = widths.count(modal) * modal
        if score > best_score:
            best, best_score = delimiter, score
    return best


def read_csv(content: bytes, max_rows: int) -> list[list[str]]:
    text = _decode(content)
    delimiter = detect_delimiter(text)
    rows: list[list[str]] = []
    try:
        for row in csv.reader(io.StringIO(text), delimiter=delimiter):
            if len(rows) >= max_rows + 50:  # header/preamble allowance
                raise FileRejected("too_many_rows", f"The statement has more than {max_rows} rows")
            rows.append([cell[:MAX_CELL_CHARS] for cell in row])
    except csv.Error:
        raise FileRejected("malformed_file", "The CSV file is malformed") from None
    return rows


def read_xlsx(content: bytes, max_rows: int) -> list[list[Any]]:
    """First worksheet as a list of rows (values only). Run in a thread."""

    import openpyxl  # imported lazily: heavy and only needed here

    try:
        workbook = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception:  # openpyxl raises many types for damaged files
        raise FileRejected(
            "malformed_file", "The XLSX file is damaged and cannot be read"
        ) from None
    try:
        if not workbook.worksheets:
            raise FileRejected("malformed_file", "The workbook has no sheets")
        rows: list[list[Any]] = []
        for row in workbook.worksheets[0].iter_rows(values_only=True):
            if len(rows) >= max_rows + 50:
                raise FileRejected("too_many_rows", f"The statement has more than {max_rows} rows")
            rows.append([c[:MAX_CELL_CHARS] if isinstance(c, str) else c for c in row])
        return rows
    finally:
        workbook.close()
