from pydantic import BaseModel, ConfigDict, Field


class BankResponse(BaseModel):
    id: int

    name: str = Field(max_length=100)

    logo: str | None = None

    model_config = ConfigDict(
        from_attributes=True
    )


class BankListResponse(BaseModel):
    items: list[BankResponse]

    total: int


class SupportedBank(BaseModel):
    name: str

    parser: str

    supported: bool
