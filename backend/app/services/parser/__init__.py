from app.services.parser.base import (
    BaseStatementParser,
    CsvStatementParser,
    ParsedRow,
    ParsedStatement,
    RowError,
    StatementParseError,
)
from app.services.parser.freedom import FreedomParser
from app.services.parser.halyk import HalykParser
from app.services.parser.kaspi import KaspiParser

PARSERS: dict[str, type[BaseStatementParser]] = {
    parser.slug: parser for parser in (KaspiParser, HalykParser, FreedomParser)
}


def get_parser(slug: str) -> BaseStatementParser | None:
    parser_cls = PARSERS.get(slug.lower())
    return parser_cls() if parser_cls else None


__all__ = [
    "BaseStatementParser",
    "CsvStatementParser",
    "ParsedRow",
    "ParsedStatement",
    "RowError",
    "StatementParseError",
    "KaspiParser",
    "HalykParser",
    "FreedomParser",
    "PARSERS",
    "get_parser",
]
