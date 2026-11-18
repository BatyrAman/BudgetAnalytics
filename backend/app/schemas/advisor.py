"""Advisor schemas.

``AdvisorReport`` / ``AdvisorAnswer`` are BOTH the structured output requested
from the LLM (strict JSON Schema) and the payload returned to clients. Every
field is required (strict mode); limits are enforced by Pydantic after the
model answers. ``evidence`` lists fact ids (``F1``...) the statement relies
on; ``assumptions`` lists what is NOT a verified fact.
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

_Text = Field(min_length=1, max_length=800)
_Title = Field(min_length=1, max_length=160)
_Evidence = Field(max_length=10, description="Fact ids, e.g. ['F3', 'F7']")
_Strings = Field(max_length=10)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Insight(_Strict):
    area: Literal[
        "income", "expenses", "cash_flow", "savings", "budget", "goal", "deposit", "balance"
    ]
    title: str = _Title
    explanation: str = _Text
    evidence: list[str] = _Evidence


class Recommendation(_Strict):
    title: str = _Title
    action: str = _Text
    reasoning: str = _Text
    evidence: list[str] = _Evidence
    assumptions: list[str] = _Strings
    priority: Literal["high", "medium", "low"]
    involves_investment: bool


class Risk(_Strict):
    title: str = _Title
    explanation: str = _Text
    severity: Literal["high", "medium", "low"]
    evidence: list[str] = _Evidence


class AdvisorReport(_Strict):
    summary: str = Field(min_length=1, max_length=1500)
    insights: list[Insight] = Field(max_length=8)
    recommendations: list[Recommendation] = Field(max_length=6)
    risks: list[Risk] = Field(max_length=5)
    assumptions: list[str] = _Strings
    data_gaps: list[str] = _Strings


class AdvisorAnswer(_Strict):
    answer: str = Field(min_length=1, max_length=2000)
    evidence: list[str] = _Evidence
    assumptions: list[str] = _Strings
    involves_investment: bool
    needs_more_data: bool
    follow_up_question: str | None = Field(max_length=300)


# ---------------------------------------------------------------- API
class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)


class FactOut(BaseModel):
    id: str
    topic: str
    label: str
    value: str
    unit: str
    period: str | None


class _AdvisorMeta(BaseModel):
    generated_by: Literal["llm", "rules"]
    fallback_reason: str | None = Field(
        description=(
            "Why rules were used: disabled | limit_reached | provider_error | invalid_output"
        )
    )
    provider: str
    model: str
    prompt_version: str
    currency_code: str
    as_of: date
    facts: list[FactOut] = Field(description="Verified data the advice is based on")
    disclaimers: list[str]


class AdvisorReportResponse(_AdvisorMeta):
    report: AdvisorReport


class AdvisorAnswerResponse(_AdvisorMeta):
    answer: AdvisorAnswer
