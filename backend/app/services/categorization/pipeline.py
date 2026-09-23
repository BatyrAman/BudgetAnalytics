"""
Конвейер категоризации импортируемых операций.

    user memory → rules → statement hint → (LLM fallback, позже) → default

Память пользователя стоит первой сознательно: это явная ручная
правка («Магнум — это не Продукты, а Хозтовары»), и она не должна
перебиваться общим словарём. Словарь применяется к тем merchant,
которые пользователь ещё не правил.

Все категоризаторы синхронные и работают по заранее загруженным
данным (память и справочник категорий грузятся одним запросом на
импорт), поэтому пайплайн не делает запросов на каждую строку.
LLM-категоризатор в будущем будет батчевым и асинхронным и
получит только merchant/описание без персональных данных.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.models.enums import CategoryKind, CategorySource, TransactionType
from app.services.categorization.rules import rules_for

DEFAULT_CATEGORY_NAME = "Без категории"


@dataclass(frozen=True, slots=True)
class CategorizationItem:
    transaction_type: TransactionType
    merchant: str | None
    description: str | None
    operation: str | None
    category_hint: str | None


@dataclass(frozen=True, slots=True)
class CategoryMatch:
    category_id: int
    source: CategorySource


def kind_for(transaction_type: TransactionType) -> CategoryKind:
    return CategoryKind.INCOME if transaction_type == TransactionType.INCOME else CategoryKind.EXPENSE


class CategoryDirectory:
    """Категории, видимые пользователю: (lower(name), kind) → id; свои важнее системных."""

    def __init__(self, entries: list[tuple[int, str, CategoryKind, bool]]) -> None:
        self._by_key: dict[tuple[str, CategoryKind], int] = {}
        # сначала системные, затем пользовательские — последние перезапишут
        for category_id, name, kind, is_user in sorted(entries, key=lambda e: e[3]):
            self._by_key[(name.strip().lower(), CategoryKind(kind))] = category_id

    def find(self, name: str, kind: CategoryKind) -> int | None:
        return self._by_key.get((name.strip().lower(), kind))

    def register(self, category_id: int, name: str, kind: CategoryKind) -> None:
        self._by_key[(name.strip().lower(), kind)] = category_id


class Categorizer(Protocol):
    def categorize(self, item: CategorizationItem) -> CategoryMatch | None: ...


class UserMemoryCategorizer:
    def __init__(self, memory: dict[str, int]) -> None:
        self.memory = memory

    def categorize(self, item: CategorizationItem) -> CategoryMatch | None:
        if item.merchant and item.merchant in self.memory:
            return CategoryMatch(self.memory[item.merchant], CategorySource.MEMORY)
        return None


class KeywordRuleCategorizer:
    def __init__(self, directory: CategoryDirectory) -> None:
        self.directory = directory

    def categorize(self, item: CategorizationItem) -> CategoryMatch | None:
        haystack = " ".join(
            part for part in (item.merchant, item.description, item.operation) if part
        ).casefold()
        if not haystack:
            return None
        kind = kind_for(item.transaction_type)
        for category_name, keywords in rules_for(item.transaction_type):
            if any(keyword in haystack for keyword in keywords):
                category_id = self.directory.find(category_name, kind)
                if category_id is not None:
                    return CategoryMatch(category_id, CategorySource.RULE)
        return None


class StatementHintCategorizer:
    def __init__(self, directory: CategoryDirectory) -> None:
        self.directory = directory

    def categorize(self, item: CategorizationItem) -> CategoryMatch | None:
        if not item.category_hint:
            return None
        category_id = self.directory.find(item.category_hint, kind_for(item.transaction_type))
        if category_id is None:
            return None
        return CategoryMatch(category_id, CategorySource.STATEMENT)


class CategorizationPipeline:
    def __init__(self, steps: list[Categorizer], directory: CategoryDirectory) -> None:
        self.steps = steps
        self.directory = directory

    def categorize(self, item: CategorizationItem) -> CategoryMatch | None:
        for step in self.steps:
            match = step.categorize(item)
            if match is not None:
                return match
        default_id = self.directory.find(DEFAULT_CATEGORY_NAME, kind_for(item.transaction_type))
        if default_id is None:
            return None
        return CategoryMatch(default_id, CategorySource.DEFAULT)


def build_pipeline(directory: CategoryDirectory, memory: dict[str, int]) -> CategorizationPipeline:
    return CategorizationPipeline(
        steps=[
            UserMemoryCategorizer(memory),
            KeywordRuleCategorizer(directory),
            StatementHintCategorizer(directory),
        ],
        directory=directory,
    )
