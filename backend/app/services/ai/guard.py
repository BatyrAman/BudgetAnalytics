"""Server-side checks of LLM output against the fact sheet.

The LLM is not trusted to follow its instructions. A structurally valid
answer is still REJECTED when:

* it cites a fact id that does not exist;
* an insight or risk cites no evidence at all;
* any free-text field contains a number that is not a value from the fact
  sheet (numbers in fact labels/periods count). Small integers 0–12 are
  allowed for plain counts like "3 месяца" — but NEVER for amounts or rates:
  a number next to %, ₸, a currency code or "тенге" must be an exact fact
  value. This blocks invented amounts, rates and calculations, including
  "helpful" arithmetic the model did itself.

Number matching is by value: "345 000", "345000.00" and "345 000,00" all
equal 345000; "57,5 %" equals 57.50. Separators that are ambiguous ("1,500")
are accepted if ANY reading matches a fact.
"""

import re
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation

from app.schemas.advisor import AdvisorAnswer, AdvisorReport
from app.services.ai.facts import FactSheet

SMALL_INTEGERS = {Decimal(n) for n in range(13)}

_NUMBER = re.compile(r"(?<![\w.,])-?(?:\d{1,3}(?:[   ]\d{3})+|\d+)(?:[.,]\d+)?")
_FACT_ID = re.compile(r"\bF\d+\b")
_TOKEN = re.compile(r"\[(?:CAT|BUDGET|GOAL)-\d+\]")


class GuardViolation(ValueError):
    pass


def _readings(raw: str) -> set[Decimal]:
    text = re.sub(r"[   ]", "", raw)
    candidates = {text.replace(",", ".")}
    if "," in text:
        candidates.add(text.replace(",", ""))  # thousands separator reading
    values = set()
    for candidate in candidates:
        try:
            values.add(Decimal(candidate).normalize())
        except InvalidOperation:
            continue
    return {abs(v) for v in values}


# A number followed by a percent/currency marker is a QUANTITY: the small-integer
# exemption for counts ("3 месяца") never applies to it ("12 %" must be a fact).
_QUANTITY_AFTER = re.compile(
    r"^\s*(?:%|‰|₸|\$|€|₽|kzt|usd|eur|rub|тенге|тг|руб|доллар|евро|процент|п\.\s?п)",
    re.IGNORECASE,
)
_QUANTITY_BEFORE = re.compile(r"(?:[$€₽₸]|kzt|usd|eur|rub)\s*$", re.IGNORECASE)


def _cleaned(text: str) -> str:
    return _TOKEN.sub(" ", _FACT_ID.sub(" ", text))


def numbers_in(text: str) -> list[tuple[str, set[Decimal]]]:
    return [(m.group(0), _readings(m.group(0))) for m in _NUMBER.finditer(_cleaned(text))]


def quantities_in(text: str) -> list[tuple[str, set[Decimal], bool]]:
    cleaned = _cleaned(text)
    result = []
    for m in _NUMBER.finditer(cleaned):
        is_quantity = bool(
            _QUANTITY_AFTER.match(cleaned[m.end() :])
            or _QUANTITY_BEFORE.search(cleaned[: m.start()])
        )
        result.append((m.group(0), _readings(m.group(0)), is_quantity))
    return result


def allowed_numbers(sheet: FactSheet) -> set[Decimal]:
    """Values present in the fact sheet (WITHOUT the small-integer exemption)."""

    allowed: set[Decimal] = set()
    for fact in sheet.facts:
        for text in (fact.value, fact.label, fact.period or ""):
            for _, readings in numbers_in(text):
                allowed |= readings
        # ISO dates/periods: also allow their parts ("2025-03" -> 2025, 3).
        for part in re.split(r"[-–]", f"{fact.value} {fact.period or ''}"):
            for _, readings in numbers_in(part):
                allowed |= readings
    return allowed


def _check_text(texts: Iterable[str], allowed: set[Decimal]) -> None:
    with_counts = allowed | SMALL_INTEGERS
    for text in texts:
        for raw, readings, is_quantity in quantities_in(text):
            permitted = allowed if is_quantity else with_counts
            if readings and not readings & permitted:
                raise GuardViolation(f"ungrounded number in output: {raw!r}")


def _check_evidence(evidence: list[str], known: set[str], required: bool) -> None:
    unknown = [e for e in evidence if e not in known]
    if unknown:
        raise GuardViolation(f"unknown fact ids cited: {unknown}")
    if required and not evidence:
        raise GuardViolation("statement without evidence")


def check_report(report: AdvisorReport, sheet: FactSheet) -> None:
    known = set(sheet.by_id())
    allowed = allowed_numbers(sheet)
    texts = [report.summary, *report.assumptions, *report.data_gaps]
    for insight in report.insights:
        _check_evidence(insight.evidence, known, required=True)
        texts += [insight.title, insight.explanation]
    for risk in report.risks:
        _check_evidence(risk.evidence, known, required=True)
        texts += [risk.title, risk.explanation]
    for rec in report.recommendations:
        _check_evidence(rec.evidence, known, required=False)
        texts += [rec.title, rec.action, rec.reasoning, *rec.assumptions]
    _check_text(texts, allowed)


def check_answer(answer: AdvisorAnswer, sheet: FactSheet) -> None:
    _check_evidence(answer.evidence, set(sheet.by_id()), required=False)
    _check_text(
        [answer.answer, *answer.assumptions, answer.follow_up_question or ""],
        allowed_numbers(sheet),
    )
