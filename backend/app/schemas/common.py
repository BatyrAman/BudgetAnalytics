"""Shared Pydantic types."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any, ClassVar

from pydantic import AfterValidator, BaseModel, Field, StringConstraints, model_validator


def to_utc(value: datetime) -> datetime:
    """Naive datetimes are interpreted as UTC (backward compatible with clients
    that never sent an offset); aware datetimes are converted to UTC."""

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


UtcDatetime = Annotated[datetime, AfterValidator(to_utc)]

# Money in API payloads: exact decimal, max NUMERIC(18, 2). Serialized as a
# JSON string by Pydantic, so no precision is lost in transit.
PositiveMoney = Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=2)]
SignedMoney = Annotated[Decimal, Field(max_digits=18, decimal_places=2)]
CurrencyCodeStr = Annotated[str, Field(pattern=r"^[A-Z]{3}$", examples=["KZT"])]
Name100 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
HexColor = Annotated[str, Field(pattern=r"^#[0-9A-Fa-f]{6}$", examples=["#3B82F6"])]


class Page[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int


class PatchModel(BaseModel):
    """Base for partial updates: omitted fields are left unchanged, and an
    explicit ``null`` is rejected unless the field is listed in ``nullable``
    (e.g. unlinking an optional account). Prevents NOT NULL violations from
    reaching the database."""

    nullable: ClassVar[frozenset[str]] = frozenset()

    @model_validator(mode="before")
    @classmethod
    def _reject_nulls(cls, data: Any) -> Any:
        if isinstance(data, dict):
            for key, value in data.items():
                if value is None and key in cls.model_fields and key not in cls.nullable:
                    raise ValueError(f"{key} must not be null")
        return data
