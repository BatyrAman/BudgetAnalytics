from app.models.enums import CategoryKind, CategorySource, TransactionType
from app.services.categorization.pipeline import (
    CategorizationItem,
    CategoryDirectory,
    build_pipeline,
)

DIRECTORY = [
    (1, "Продукты", CategoryKind.EXPENSE, False),
    (2, "Такси", CategoryKind.EXPENSE, False),
    (3, "Без категории", CategoryKind.EXPENSE, False),
    (4, "Зарплата", CategoryKind.INCOME, False),
    (5, "Без категории", CategoryKind.INCOME, False),
    (6, "Продукты", CategoryKind.EXPENSE, True),  # своя категория с тем же именем
    (7, "Хобби", CategoryKind.EXPENSE, True),
]


def item(merchant=None, type_=TransactionType.EXPENSE, hint=None, operation=None):
    return CategorizationItem(type_, merchant, merchant, operation, hint)


def test_own_category_overrides_system_with_same_name():
    pipeline = build_pipeline(CategoryDirectory(DIRECTORY), {})
    match = pipeline.categorize(item("MAGNUM ALMATY"))
    assert (match.category_id, match.source) == (6, CategorySource.RULE)


def test_memory_first():
    pipeline = build_pipeline(CategoryDirectory(DIRECTORY), {"MAGNUM ALMATY": 7})
    match = pipeline.categorize(item("MAGNUM ALMATY"))
    assert (match.category_id, match.source) == (7, CategorySource.MEMORY)


def test_rules_are_type_aware():
    pipeline = build_pipeline(CategoryDirectory(DIRECTORY), {})
    assert pipeline.categorize(item("ЗАРПЛАТА ЗА МАРТ", TransactionType.INCOME)).category_id == 4


def test_statement_hint_then_default():
    pipeline = build_pipeline(CategoryDirectory(DIRECTORY), {})
    assert pipeline.categorize(item("SOMETHING", hint="хобби")).source is CategorySource.STATEMENT
    default = pipeline.categorize(item("SOMETHING"))
    assert (default.category_id, default.source) == (3, CategorySource.DEFAULT)
    assert pipeline.categorize(item("SOMETHING", TransactionType.INCOME)).category_id == 5


def test_empty_item():
    pipeline = build_pipeline(CategoryDirectory(DIRECTORY), {})
    assert pipeline.categorize(item(None)).source is CategorySource.DEFAULT
